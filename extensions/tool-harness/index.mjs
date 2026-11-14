import { Workspace, exactEdits, MAX_WRITE } from './workspace.mjs';
import { Outcomes, sidecar, checkBroker } from './policy.mjs';
import { control, admit, guardedStream, releaseOwnedLease, watchHandoff } from './residency.mjs';
import { nativeCalls } from './native-calls.mjs';
import { open } from 'node:fs/promises';

const FILE_TOOLS = ['read', 'write', 'edit', 'bash'];
const props = {read:['path','offset','limit'], write:['path','content'], edit:['path','edits'], bash:['command','timeout']};

// Factory injected with Pi's public exports: no separate model client or loop.
export function harnessExtension(sdk, { rpc = sidecar, providers, initial, confirm, native, getLeaseCapability = () => undefined, durableGuard, ownerControl, exposeCommands, inferenceGate = admit, toolAdmission, readOnly = false, normalOnly = false, parentOnly = false, readPaths = [], textBaseUrl = 'http://127.0.0.1:8081/v1', binding } = {}) {
  if(parentOnly&&(!readOnly||!normalOnly))throw new Error('Parent-only requires normal-only READ-ONLY');
  if(normalOnly&&!readOnly)throw new Error('Normal-only mode requires READ-ONLY profile');
  if(readOnly)providers=undefined;
  return function(pi) {
    let active, outcomes, previous, handoff, originalModel, handoffFailure, pendingHandoff;
    const validated=nativeCalls(pi);
    let readDefinition;
    const fileTools=readOnly?['read']:FILE_TOOLS;
    const approve = async (ctx, title, detail, signal) => {
      signal?.throwIfAborted();
      const ok = confirm ? await confirm({title, detail, signal}) : ctx.hasUI && await ctx.ui.confirm(title, detail, {signal, timeout:120000});
      signal?.throwIfAborted();
      if (ok !== true) throw Object.assign(new Error('Trusted human approval required'),{code:'HUMAN_DENIED'});
    };
    async function activate(ctx, workspace, taskId, appId) {
      if(readOnly&&(!binding||workspace!==binding.workspace||taskId!==binding.taskId||appId!==binding.appId))throw new Error('READ-ONLY owner scope is fixed; cannot rebind');
      if (!/^[\w.-]{1,128}$/.test(taskId) || typeof appId !== 'string' || !appId || appId.length > 120)
        throw new Error('Explicit task ID and application ID required');
      if (!ctx.sessionManager.getSessionFile()) throw new Error('Persistent Pi session required');
      const root = await Workspace.create(workspace);
      try {
        if(readOnly && (!Array.isArray(readPaths)||!readPaths.length||readPaths.length>32))throw new Error('Explicit bounded read allowlist required');
        const allowed=readOnly?new Set(readPaths.map(p=>root.target(p))):undefined;
        await approve(ctx, readOnly?'Enable READ-ONLY Hyprneuro tools?':'Enable Hyprneuro tools?', readOnly?JSON.stringify({task:taskId,app:appId,workspace,operations:['read'],paths:[...allowed],note:'No write, execute, network or lifecycle permission. Every read requires fresh approval.'}): `Task ${taskId}; app ${appId}; workspace ${workspace}. Each call still requires approval. Bash is UNSANDBOXED host execution.`);
        await rpc({action:'auth_create', task_id:taskId, app_id:appId, file_prefix:workspace, ops:readOnly?['read']:['read','write','execute']});
        await active?.workspace.close();
        previous ??= pi.getActiveTools();
        active = {workspace:root, taskId, appId, allowed};
        outcomes = new Outcomes(pi, ctx);
        pi.setActiveTools([...fileTools, ...(providers?.names ?? []), ...(!parentOnly&&durableGuard&&pi.getAllTools().some(t=>t.name==='subagents')?['subagents']:[])]);
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
    if(!normalOnly)pi.registerCommand('hn-residency', {description:'Initialize cooperating admission only after ALL clients share HYPRNEURO_RESIDENCY_DIR',
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
    if(native)pi.registerProvider('hyprneuro-local', {streamSimple:(model,context,options)=>guardedStream(native,model,context,options,handoff?.token,inferenceGate),api:'openai-completions',apiKey:'local-no-credential',
      models:(normalOnly?[['lfm-text',8081,131072]]:[['lfm-text',8081,131072],['lfm-omni',8082,32768],['lfm-moe',8080,65536]]).map(([id,port,contextWindow])=>({
        id,name:id,baseUrl:id==='lfm-text'?textBaseUrl:`http://127.0.0.1:${port}/v1`,contextWindow,maxTokens:2048,reasoning:false,
        input:id==='lfm-omni'?['text','image']:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
        compat:{supportsDeveloperRole:false,supportsStore:false,supportsFinishReason:true,maxTokensField:'max_tokens'}
      }))});
    pi.registerCommand('hn-model',{description:'Select already-running local text or omni (never starts services)',handler:async(args,ctx)=>{
      await ctx.waitForIdle();
      if(handoff || !(normalOnly?['text']:['text','omni']).includes(args))throw new Error('Use text or omni outside a handoff');
      if(!native)throw new Error('Native local transport adapter unavailable');
      const release=await inferenceGate(args);await release();
      const model=ctx.modelRegistry.find('hyprneuro-local','lfm-'+args);
      if(!model || !await pi.setModel(model))throw new Error('Local Pi provider unavailable');
    }});
    const hermesCommand={description:'Trusted exclusive Hermes handoff: start or finish; Pi retains the same session',handler:async(args,ctx)=>{
      if(normalOnly)throw new Error('Lifecycle unavailable: normal-only owner; all-client cooperation unverified');
      await ctx.waitForIdle();
      if(args==='finish')return finishHandoff(ctx);
      if(handoffFailure)throw new Error(handoffFailure);
      if(!native || args!=='start' || handoff || !active)throw new Error('Enable guarded tools; use start or finish');
      const owner=control('handoff');pendingHandoff=owner;owner.send({task_id:active.taskId});
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
      } catch(e){
        await owner.stop().catch(()=>{});
        if(handoff===owner&&originalModel)await pi.setModel(originalModel);
        handoff=undefined;throw e;
      } finally {if(pendingHandoff===owner)pendingHandoff=undefined;}
    }};
    async function disable() {
      // Fixed read binding is known even if auth_create's acknowledgement was
      // lost before active was assigned. Revocation never broadens authority.
      const task=active?.taskId??(readOnly?binding?.taskId:undefined);
      if(task)await rpc({action:'auth_revoke',task_id:task});
      await active?.workspace.close();active=undefined;outcomes=undefined;
      pi.setActiveTools(previous??[]);previous=undefined;
    }
    exposeCommands?.({disable,read:(id,args,signal,ctx)=>readDefinition.execute(id,args,signal,undefined,ctx),
      moe:normalOnly?async()=>{throw new Error('Lifecycle unavailable: normal-only owner; all-client cooperation unverified');}:hermesCommand.handler,
      status:normalOnly?async()=>({state:'unavailable',available:false,reason:'Normal-only owner; exclusive lifecycle disabled; all-client cooperation unverified'}):observedState,cancel:async()=>{
      if(pendingHandoff){pendingHandoff.expectedClose=true;await pendingHandoff.stop();}
    }});
    if(!normalOnly)pi.registerCommand('hn-hermes',{...hermesCommand,handler:(args,ctx)=>ownerControl?ownerControl(args==='start'?'on':args==='finish'?'off':args):hermesCommand.handler(args,ctx)});
    pi.registerCommand('moe',{description:'Trusted manual on/off/status; no startup preference or D1 permission grant',handler:async(args,ctx)=>{
      if(ownerControl)return ownerControl(args);
      if(args==='status') {const state=normalOnly?{state:'unavailable',available:false,reason:'Normal-only; all-client cooperation unverified'}:await observedState();ctx.ui.notify(JSON.stringify(state),'info');return state;}
      if(!['on','off'].includes(args))throw new Error('Use /moe on, /moe off or /moe status');
      await hermesCommand.handler(args==='on'?'start':'finish',ctx);
      const state=await observedState();ctx.ui.notify(JSON.stringify(state),state.state==='failed'?'error':'info');return state;
    }});
    pi.registerCommand('hn-tools', {
      description:'Enable guarded Pi tools: /hn-tools /absolute/workspace task-id app-id; or off; or network',
      handler: async (args, ctx) => {
        await ctx.waitForIdle();
        if (args === 'off') {
          await disable();
        } else if (args === 'network') {
          if(readOnly)throw new Error('READ-ONLY profile cannot expand network or IO permissions');
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
      if(parentOnly&&event.toolName!=='read')return {block:true,reason:'Parent-only owner permits read only; no helpers or delegation',terminate:true};
      if(readOnly&&!active)return {block:true,reason:'READ-ONLY tools not activated',terminate:true};
      // Only the exact one-shot nested native call of an already guarded provider.
      // Keep AFTER read-only/parent-only checks; raw namespace calls stay denied.
      if(!readOnly && active && providers?.allowsNativeCall?.(event))return;
      if(event.toolName==='subagents'&&durableGuard) {
        try {
          if(!validated(event.toolCallId))throw new Error('Incomplete native delegation call');
          await durableGuard(event.input);return;
        } catch(error){return {block:true,reason:error.message,terminate:true};}
      }
      if (active && !validated(event.toolCallId))
        return {block:true,reason:'Incomplete/unvalidated native tool call',terminate:true};
      if (active && ![...fileTools, ...(providers?.names ?? [])].includes(event.toolName))
        return {block:true, reason:'Tool outside guarded loadout', terminate:true};
    });
    async function run(name, id, input, signal, onUpdate, ctx, execute) {
      if(readOnly&&name!=='read')throw new Error('READ-ONLY profile forbids this tool');
      if (!active || !outcomes) throw new Error('Tools disabled; use trusted /hn-tools command');
      toolAdmission?.();
      signal?.throwIfAborted();
      const args = structuredClone(input);
      if (JSON.stringify(args).length > MAX_WRITE + 8192 || Object.keys(args).some(k => !(props[name] ?? providers?.properties(name) ?? []).includes(k)))
        throw new Error('Oversized or unknown arguments (approval fields are not accepted)');
      const path = name === 'bash' || !FILE_TOOLS.includes(name) ? active.workspace.root : active.workspace.target(args.path);
      if(readOnly&&!active.allowed.has(path))throw new Error('Read path outside exact allowlist');
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
      toolAdmission?.();
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
    for (const definition of (readOnly?[read]:[read,write,edit,shell])) {
      const name = definition.name;
      const guarded={...definition, executionMode:'sequential',
        async execute(id,args,signal,onUpdate,ctx) {
          return run(name,id,args,signal,onUpdate,ctx, async (input,workspace) => {
            const approvedPath = readOnly ? workspace.target(input.path) : undefined;
            const exact = p => {
              if(readOnly && workspace.target(p)!==approvedPath)throw new Error('Resolved read path differs from exact approved target');
              return p;
            };
            const operations = {access:p => workspace.access(exact(p)), mkdir:p => workspace.mkdir(p),
              detectImageMimeType:async p => {
                const b=await workspace.read(exact(p));
                if(b.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))return 'image/png';
                if(b[0]===255 && b[1]===216 && b[2]===255)return 'image/jpeg';
                if(b.subarray(0,3).toString()==='GIF')return 'image/gif';
                if(b.subarray(0,2).toString()==='BM')return 'image/bmp';
                if(b.subarray(0,4).toString()==='RIFF' && b.subarray(8,12).toString()==='WEBP')return 'image/webp';
              },
              writeFile:(p,text) => workspace.write(p,text),
              readFile:async p => {
                const data = await workspace.read(exact(p));
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
      };
      if(name==='read')readDefinition=guarded;
      pi.registerTool(guarded);
    }
    for (const definition of (readOnly?[]:providers?.tools ?? [])) pi.registerTool({...definition, executionMode:'sequential',
      execute:(id,args,signal,onUpdate,ctx) => run(definition.name,id,args,signal,onUpdate,ctx,
        input => providers.execute(definition.name,input,signal,{id,ctx}))});
  };
}
