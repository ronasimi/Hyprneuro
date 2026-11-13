import { Workspace, exactEdits, MAX_WRITE } from './workspace.mjs';
import { Outcomes, sidecar, checkBroker } from './policy.mjs';

const FILE_TOOLS = ['read', 'write', 'edit', 'bash'];
const props = {read:['path','offset','limit'], write:['path','content'], edit:['path','edits'], bash:['command','timeout']};

// Factory injected with Pi's public exports: no separate model client or loop.
export function harnessExtension(sdk, { rpc = sidecar, providers, initial, confirm } = {}) {
  return function(pi) {
    let active, outcomes, previous;
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
      active = undefined; outcomes = undefined;
      // Resuming never restores consent. Tests/embedded hosts may supply explicit activation.
      if (initial) await activate(ctx, initial.workspace, initial.taskId, initial.appId);
    });
    pi.on('session_shutdown', async () => { await active?.workspace.close(); active = undefined; });
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
