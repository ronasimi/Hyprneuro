import { Workspace, exactEdits, MAX_WRITE } from './workspace.mjs';
import { Outcomes, sidecar, checkBroker } from './policy.mjs';
import { control, admit, guardedStream, releaseOwnedLease, watchHandoff } from './residency.mjs';
import { open } from 'node:fs/promises';

const FILE_TOOLS = ['read', 'write', 'edit', 'bash'];
const props = {read:['path','offset','limit'], write:['path','content'], edit:['path','edits'], bash:['command','timeout']};

// Factory injected with Pi's public exports: no separate model client or loop.
export function harnessExtension(sdk, { rpc = sidecar, providers, initial, confirm, native, getLeaseCapability = () => undefined } = {}) {
  return function(pi) {
    let active, outcomes, previous, handoff, originalModel, handoffFailure;
    let nativeCalls = new Map(), nativeFinish, rawInvalid = false, validatedIds = new Set();
    const approve = async (ctx, title, detail, signal) => {
      signal?.throwIfAborted();
      const ok = confirm ? await confirm({title, detail, signal}) : ctx.hasUI && await ctx.ui.confirm(title, detail, {signal, timeout:120000});
      signal?.throwIfAborted();
      if (ok !== true) throw new Error('Trusted human approval required');
    };
    async function activate(ctx, workspace, taskId, appId) {
      if (!/^[\w.-]{1,128}$/.test(taskId) || typeof appId !== 'string' || !appId || appId.length > 120)
        throw new Error('Explicit task ID and application ID required');
      if (!ctx.sessionManager.getSessionFile()) throw new Error('Persistent Pi session required');
      const root = await Workspace.create(workspace);
      try {
        await approve(ctx, 'Enable Hyprneuro tools?', `Task ${taskId}; app ${appId}; workspace ${workspace}. Each call still requires approval. Bash is UNSANDBOXED host execution.`);
        await rpc({action:'auth_create', task_id:taskId, app_id:appId, file_prefix:workspace, ops:['read','write','execute']});
        await active?.workspace.close();
        previous ??= pi.getActiveTools();
        active = {workspace:root, taskId, appId};
        outcomes = new Outcomes(pi, ctx);
        pi.setActiveTools([...FILE_TOOLS, ...(providers?.names ?? [])]);
      } catch (e) { await root.close(); throw e; }
    }
    pi.on('session_start', async (_e, ctx) => {
      await active?.workspace.close(); active = undefined; outcomes = undefined;
      // Resuming never restores consent. Tests/embedded hosts may supply explicit activation.
      if (initial) await activate(ctx, initial.workspace, initial.taskId, initial.appId);
    });
    const syncSession = async ctx => {
      const file = await open(ctx.sessionManager.getSessionFile(),'r+');
      try {await file.sync();} finally {await file.close();}
    };
    async function observedState() {
      const owner=control('status');
      try {const state=await owner.next();await owner.closed;return handoffFailure?{...state,state:'failed',visual_paused:true,error:handoffFailure}:state;}
      catch(e){await owner.stop().catch(()=>{});throw e;}
    }
    async function finishHandoff(ctx) {
      if (!handoff) {
        const state=await observedState();
        if(!['off','uninitialized'].includes(state.state))throw new Error('No owned transaction; use the live owner UI/RPC or manual recovery');
        return;
      }
      const owner = handoff;
      await syncSession(ctx);
      owner.expectedClose=true;
      owner.send({finish:true});
      const result = await owner.next();
      if (result.restored !== true) throw new Error('Prior model subset restoration unverified; admission remains blocked');
      await owner.closed;
      handoff = undefined;
      if (originalModel) await pi.setModel(originalModel);
      pi.appendEntry('hyprneuro.handoff/1',{phase:'restored'});
    }
    pi.on('session_shutdown', async (_e,ctx) => {
      try {if(handoff)await finishHandoff(ctx);} finally {await active?.workspace.close();active=undefined;}
    });
    pi.registerCommand('hn-residency', {description:'Initialize cooperating admission only after ALL clients share HYPRNEURO_RESIDENCY_DIR',
      handler:async (_args,ctx)=>{
        await ctx.waitForIdle();
        const owner=control('initialize');
        try {
          const request=await owner.next();
          if(request.type!=='cooperation_approval')throw new Error('Unexpected residency handshake');
          await approve(ctx,'Confirm ALL inference clients cooperate?',
            'Every Pi and sidecar process must already use the SAME HYPRNEURO_RESIDENCY_DIR with this admission adapter. Unmodified clients and external lfm/systemctl do NOT lock. Do not proceed while an existing Hermes serves another session. No config is changed.');
          owner.send({ok:true});
          if((await owner.next()).initialized!==true)throw new Error('Initialization not verified');
          await owner.closed;
        } catch(e){await owner.stop().catch(()=>{});throw e;}
      }});
    if(native)pi.registerProvider('hyprneuro-local', {streamSimple:(model,context,options)=>guardedStream(native,model,context,options,handoff?.token),api:'openai-completions',apiKey:'local-no-credential',
      models:[['lfm-text',8081,131072],['lfm-omni',8082,32768],['lfm-moe',8080,65536]].map(([id,port,contextWindow])=>({
        id,name:id,baseUrl:`http://127.0.0.1:${port}/v1`,contextWindow,maxTokens:2048,reasoning:false,
        input:id==='lfm-omni'?['text','image']:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
        compat:{supportsDeveloperRole:false,supportsStore:false,supportsFinishReason:true,maxTokensField:'max_tokens'}
      }))});
    pi.registerCommand('hn-model',{description:'Select already-running local text or omni (never starts services)',handler:async(args,ctx)=>{
      await ctx.waitForIdle();
      if(handoff || !['text','omni'].includes(args))throw new Error('Use text or omni outside a handoff');
      if(!native)throw new Error('Native local transport adapter unavailable');
      const release=await admit(args);await release();
      const model=ctx.modelRegistry.find('hyprneuro-local','lfm-'+args);
      if(!model || !await pi.setModel(model))throw new Error('Local Pi provider unavailable');
    }});
    const hermesCommand={description:'Trusted exclusive Hermes handoff: start or finish; Pi retains the same session',handler:async(args,ctx)=>{
      await ctx.waitForIdle();
      if(args==='finish')return finishHandoff(ctx);
      if(handoffFailure)throw new Error(handoffFailure);
      if(!native || args!=='start' || handoff || !active)throw new Error('Enable guarded tools; use start or finish');
      const owner=control('handoff');owner.send({task_id:active.taskId});
      try {
        while(true) {
          const request=await owner.next();
          if(request.type==='handoff_approval') {
            await approve(ctx,'Exclusive Hermes handoff?',JSON.stringify(request.detail));owner.send({ok:true});
          } else if(request.type==='checkpoint') {
            pi.appendEntry('hyprneuro.handoff/1',{phase:'checkpoint',task:active.taskId});
            await syncSession(ctx);owner.send({ok:true});
          } else if(request.type==='release_lease') {
            await releaseOwnedLease(rpc,active.taskId,getLeaseCapability());
            owner.send({ok:true});
          } else if(request.type==='hermes_ready') {
            if(typeof request.token!=='string')throw new Error('Missing handoff token');
            owner.token=request.token;handoff=owner;originalModel=ctx.model;
            watchHandoff(owner,async error=>{
              if(handoff!==owner)return;
              handoff=undefined;handoffFailure=error.message;
              if(originalModel)await pi.setModel(originalModel);
              ctx.ui.notify(handoffFailure,'error');
            });
            const model=ctx.modelRegistry.find('hyprneuro-local','lfm-moe');
            if(!model || !await pi.setModel(model))throw new Error('Hermes Pi provider unavailable');
            pi.appendEntry('hyprneuro.handoff/1',{phase:'hermes',task:active.taskId});
            break;
          } else throw new Error('Unexpected residency handshake');
        }
      } catch(e){await owner.stop().catch(()=>{});handoff=undefined;throw e;}
    }};
    pi.registerCommand('hn-hermes',hermesCommand);
    pi.registerCommand('moe',{description:'Trusted manual on/off/status; no startup preference or D1 permission grant',handler:async(args,ctx)=>{
      if(args==='status') {const state=await observedState();ctx.ui.notify(JSON.stringify(state),'info');return state;}
      if(!['on','off'].includes(args))throw new Error('Use /moe on, /moe off or /moe status');
      await hermesCommand.handler(args==='on'?'start':'finish',ctx);
      const state=await observedState();ctx.ui.notify(JSON.stringify(state),state.state==='failed'?'error':'info');return state;
    }});
    pi.on('before_provider_request',()=>{
      nativeCalls=new Map();nativeFinish=undefined;rawInvalid=false;validatedIds=new Set();
    });
    // Safety validation of complete native tool JSON; Pi owns aggregation/execution.
    pi.on('provider_stream_event',event=>{
      if(event.api!=='openai-completions' || rawInvalid)return;
      const choices=event.data?.choices;
      if(!choices?.length)return;
      if(choices.length!==1 || choices[0].index!==0){rawInvalid=true;return;}
      const choice=choices[0];
      if(choice.finish_reason!=null)nativeFinish=choice.finish_reason;
      for(const c of choice.delta?.tool_calls??[]) {
        if(!Number.isInteger(c.index) || c.index<0 || c.index>=8){rawInvalid=true;continue;}
        const prior=nativeCalls.get(c.index)??{id:'',name:'',arguments:''};
        for(const [key,value] of [['id',c.id],['name',c.function?.name],['arguments',c.function?.arguments]]) {
          if(value!==undefined && typeof value!=='string'){rawInvalid=true;continue;}
          if(prior[key].length+(value?.length??0)>(key==='arguments'?131072:128)){rawInvalid=true;break;}
          prior[key]+=value??'';
        }
        nativeCalls.set(c.index,prior);
      }
    });
    pi.on('message_end',async(event)=>{
      if(event.message.role!=='assistant')return;
      const calls=event.message.content.filter(c=>c.type==='toolCall');
      if(event.message.api!=='openai-completions') {validatedIds=new Set(calls.map(c=>c.id));return;}
      if(rawInvalid || nativeFinish!=='tool_calls' || event.message.stopReason!=='toolUse' || calls.length!==nativeCalls.size)return;
      try {
        const ids=new Set();
        for(const [index,c] of nativeCalls) {
          if(!nativeCalls.has(index-1) && index!==0)throw new Error('Tool index gap');
          const actual=calls.find(a=>a.id===c.id);
          if(!actual || ids.has(c.id) || !/^[\w-]{1,128}$/.test(c.id) || actual.name!==c.name ||
            JSON.stringify(actual.arguments)!==JSON.stringify(JSON.parse(c.arguments)))throw new Error('Incomplete tool JSON');
          ids.add(c.id);
        }
        validatedIds=ids;
      } catch {validatedIds=new Set();}
    });
    pi.registerCommand('hn-tools', {
      description:'Enable guarded Pi tools: /hn-tools /absolute/workspace task-id app-id; or off; or network',
      handler: async (args, ctx) => {
        await ctx.waitForIdle();
        if (args === 'off') {
          if (active) await rpc({action:'auth_revoke', task_id:active.taskId});
          await active?.workspace.close(); active = undefined;
          pi.setActiveTools(previous ?? []); previous = undefined;
        } else if (args === 'network') {
          if (!active) throw new Error('Enable a workspace first');
          await approve(ctx, 'Enable provider network scope?', 'Allow network + submit_external scope; every exact provider query will still require separate approval. No ambient credentials are discovered.');
          await rpc({action:'auth_expand', task_id:active.taskId, ops:['read','write','execute','network','submit_external'], approved:true});
        } else {
          const parts = args.trim().split(/\s+/);
          if (parts.length !== 3) throw new Error('Expected workspace task-id app-id (workspace cannot contain spaces)');
          await activate(ctx, ...parts);
        }
      }
    });
    // No model-facing approval, scope expansion or subprocess-delegation APIs.
    pi.on('tool_call', async event => {
      if (active && !validatedIds.has(event.toolCallId))
        return {block:true,reason:'Incomplete/unvalidated native tool call',terminate:true};
      if (active && ![...FILE_TOOLS, ...(providers?.names ?? [])].includes(event.toolName))
        return {block:true, reason:'Tool outside guarded loadout', terminate:true};
    });
    async function run(name, id, input, signal, onUpdate, ctx, execute) {
      if (!active || !outcomes) throw new Error('Tools disabled; use trusted /hn-tools command');
      signal?.throwIfAborted();
      const args = structuredClone(input);
      if (JSON.stringify(args).length > MAX_WRITE + 8192 || Object.keys(args).some(k => !(props[name] ?? providers?.properties(name) ?? []).includes(k)))
        throw new Error('Oversized or unknown arguments (approval fields are not accepted)');
      const path = name === 'bash' || !FILE_TOOLS.includes(name) ? active.workspace.root : active.workspace.target(args.path);
      const op = name === 'read' ? 'read' : ['write','edit'].includes(name) ? 'write' : name === 'bash' ? 'execute' : 'network';
      const check = async () => {
        await checkBroker(rpc, active.taskId, active.appId, op, path, signal);
        if (op === 'network') await checkBroker(rpc, active.taskId, active.appId, 'submit_external', path, signal);
      };
      if (op === 'network') providers.available(name);
      if (name === 'bash') {
        args.timeout ??= 30;
        if (!Number.isFinite(args.timeout) || args.timeout <= 0 || args.timeout > 120) throw new Error('Bash timeout must be >0 and <=120s');
      }
      if (name === 'read' && ['offset','limit'].some(k => args[k] !== undefined && (!Number.isInteger(args[k]) || args[k] < 1)))
        throw new Error('Read offset/limit must be positive integers');
      await check();
      const key = outcomes.key(name, args), sideEffect = op !== 'read';
      const old = outcomes.existing(id, key, sideEffect);
      if (old) return old;
      await approve(ctx, `Allow ${name}?`, JSON.stringify({task:active.taskId, workspace:active.workspace.root,
        ...(name === 'bash' ? {warning:'UNSANDBOXED: can access host files, secrets, network and services'} : {}),
        ...(op === 'network' ? {destination:providers.destination(name), warning:'Query submitted externally; result is untrusted'} : {}), args}), signal);
      await check();
      await outcomes.record({id,key,status:'executing'});
      try {
        const result = await execute(args, active.workspace);
        signal?.throwIfAborted();
        await outcomes.record({id,key,status:'completed',result});
        return result;
      } catch (e) {
        await outcomes.record({id,key,status:'unknown'});
        throw e;
      }
    }
    const read = sdk.createReadToolDefinition(process.cwd());
    const write = sdk.createWriteToolDefinition(process.cwd());
    const edit = sdk.createEditToolDefinition(process.cwd());
    const shell = sdk.createBashToolDefinition(process.cwd());
    for (const definition of [read,write,edit,shell]) {
      const name = definition.name;
      pi.registerTool({...definition, executionMode:'sequential',
        async execute(id,args,signal,onUpdate,ctx) {
          return run(name,id,args,signal,onUpdate,ctx, async (input,workspace) => {
            const operations = {access:p => workspace.access(p), mkdir:p => workspace.mkdir(p),
              detectImageMimeType:async p => {
                const b=await workspace.read(p);
                if(b.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))return 'image/png';
                if(b[0]===255 && b[1]===216 && b[2]===255)return 'image/jpeg';
                if(b.subarray(0,3).toString()==='GIF')return 'image/gif';
                if(b.subarray(0,2).toString()==='BM')return 'image/bmp';
                if(b.subarray(0,4).toString()==='RIFF' && b.subarray(8,12).toString()==='WEBP')return 'image/webp';
              },
              writeFile:(p,text) => workspace.write(p,text),
              readFile:async p => {
                const data = await workspace.read(p);
                return name === 'edit' ? exactEdits(data,input.edits) : data;
              }};
            if (name === 'bash') {
              const local = sdk.createLocalBashOperations({shellPath:'/bin/bash'});
              const abort = new AbortController();
              const combined = AbortSignal.any([abort.signal, ...(signal ? [signal] : [])]);
              let bytes = 0;
              const bash = sdk.createBashToolDefinition(workspace.root, {exposeSessionEnvironment:false,
                operations:{exec:(command,cwd,opts) => local.exec(command,cwd,{...opts,signal:combined,
                  env:{PATH:'/usr/local/bin:/usr/bin:/bin',HOME:workspace.root,LANG:'C.UTF-8'},
                  onData:data => {bytes += data.length; if (bytes > MAX_WRITE) abort.abort(); else opts.onData(data);}})}});
              return bash.execute(id,input,signal,onUpdate,{...ctx,cwd:workspace.root});
            }
            const factory = name === 'read' ? sdk.createReadToolDefinition : name === 'write' ? sdk.createWriteToolDefinition : sdk.createEditToolDefinition;
            return factory(workspace.root,{operations}).execute(id,input,signal,onUpdate,{...ctx,cwd:workspace.root});
          });
        }
      });
    }
    for (const definition of providers?.tools ?? []) pi.registerTool({...definition, executionMode:'sequential',
      execute:(id,args,signal,onUpdate,ctx) => run(definition.name,id,args,signal,onUpdate,ctx,
        input => providers.execute(definition.name,input,signal))});
  };
}
