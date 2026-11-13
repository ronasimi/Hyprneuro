import { open,mkdir,readFile,writeFile,unlink } from 'node:fs/promises';
import { dirname,join,relative,isAbsolute } from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { harnessExtension } from '../tool-harness/index.mjs';
import { checkBroker,sidecar } from '../tool-harness/policy.mjs';
import { admit } from '../tool-harness/residency.mjs';
import { Providers } from '../tool-harness/providers.mjs';
import { privateDirectory,serveOwner } from './socket.mjs';
import { PiOwner } from './owner.mjs';
import { recommendHermes } from './routing.mjs';
import { durablePolicy,durableRuntime } from './durable.mjs';

// Explicit paths; no package install, auto-discovery, existing auth/token stores,
// service setup, or independent conversation framework.
export async function createHost({sdkPath,durableDir,piBin,root,workspace,taskId,appId,
    rpc=sidecar,model,native,providers,route,serve=true}) {
  if(process.env.HYPRNEURO_PI_OWNER_ENABLE!=='1')throw new Error('Pi owner is opt-in and source/mock-only, not activated');
  if(!process.env.HYPRNEURO_RESIDENCY_DIR)throw new Error('All clients must explicitly share residency directory');
  process.umask(0o077); // Dedicated owner and its native children create private files/dirs.
  await privateDirectory(root);
  const rel=relative(workspace,root);
  if(!isAbsolute(workspace)||!rel||!(rel==='..'||rel.startsWith('../')||isAbsolute(rel)))throw new Error('Owner secrets must be outside the explicit workspace');
  const guard=await open(join(root,'owner.guard'),'wx',0o600).catch(()=>{throw new Error('Previous/live owner exists; review unknown outcomes, never adopt');});
  const syncDirectory=async path=>{const fd=await open(path,'r');try{await fd.sync();}finally{await fd.close();}};
  await guard.sync();await syncDirectory(root); // durable guard BEFORE any runtime effect
  let owner,session,socket;
  const checkpoint=async phase=>{
    if(session?.sessionManager.getSessionFile()) {
      session.sessionManager.appendCustomEntry('hyprneuro.pi-owner/1',{phase});
      try {
        const file=session.sessionManager.getSessionFile();
        const fd=await open(file,'r+');try{await fd.sync();}finally{await fd.close();}
        await syncDirectory(dirname(file));
      } catch(error) {
        // Native Pi intentionally keeps setup-only sessions in memory. Never
        // fabricate an assistant reply merely to force persistence.
        if(error.code!=='ENOENT'||session.sessionManager.getEntries().some(e=>e.type==='message'&&['user','assistant'].includes(e.message.role)))throw error;
      }
    }
    const fd=await open(join(root,'checkpoint.json'),'w',0o600);
    try {await fd.writeFile(JSON.stringify({phase,session:session?.sessionManager.getSessionFile()}));await fd.sync();}finally{await fd.close();}
    await syncDirectory(root);
  };
  try {
    const sdk=await import(pathToFileURL(sdkPath));
    const aiURL=new URL('../../pi-ai/dist/index.js',pathToFileURL(sdkPath));
    native??={lazyStream:(await import(aiURL)).lazyStream,streamSimple:(await import(new URL('./api/openai-completions.js',aiURL))).streamSimple};
    const agentDir=join(root,'agent'),home=join(root,'durable');
    await privateDirectory(agentDir);await privateDirectory(home);
    // Dedicated home only; never drain/resume the parent's existing workflows.
    process.env.DSA_HOME=home;process.env.DSA_SCOPE='off';process.env.PI_CODING_AGENT_DIR=agentDir;
    for(const key of ['DSA_SESSION','DSA_EXEC','DSA_CALL','DSA_INBOX','DSA_JOURNAL','DSA_SCHEMA','DSA_BUDGET','DSA_MODEL','DSA_RESULT','DSA_OUTPUT','DSA_PROBE','DSA_ORCHESTRATOR_ENTRY'])delete process.env[key];
    const stat=await readFile(`/proc/${process.pid}/stat`,'utf8');
    process.env.HYPRNEURO_PI_OWNER_ID=process.pid+':'+stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s+/)[19];
    const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
    const child=fileURLToPath(new URL('./child.ts',import.meta.url));
    const launcher=join(root,'pi-child');
    if(!isAbsolute(piBin))throw new Error('Explicit installed Pi executable required');
    await writeFile(launcher,`#!/bin/sh\nexec ${quote(piBin)} --offline --no-extensions --no-skills --no-context-files --no-prompt-templates -e ${quote(child)} "$@"\n`,{mode:0o700});
    process.env.DSA_PI_BIN=launcher;
    const durable=await durableRuntime(durableDir,home,{...process.env});
    let commands,activated=false;
    const settings=sdk.SettingsManager.inMemory({retry:{enabled:false,provider:{maxRetries:0}},compaction:{enabled:false},cacheWarming:'off'});
    const runtime=await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:null,modelsStorePath:join(agentDir,'models-store.json'),refreshOnCreate:false,allowModelNetwork:false});
    const policy=durablePolicy({workspace,phase:()=>owner?.phase??'closed',
      broker:op=>checkBroker(rpc,taskId,appId,op,workspace),approve:request=>owner.approve(request)});
    providers??=await Providers.load();
    const extension=harnessExtension(sdk,{rpc,providers,native,confirm:request=>owner.approve(request),durableGuard:policy,
      toolAdmission:()=>{if(owner?.closing||!['ordinary','hermes'].includes(owner?.phase))throw new Error('Owner transition blocks new tool side effects');},
      inferenceGate:(role,token)=>{
        if(owner?.closing||!['ordinary','hermes'].includes(owner?.phase))throw new Error('Owner transition blocks native background inference');
        return admit(role,token);
      },ownerControl:value=>value==='status'?owner.status():owner.transition(value),exposeCommands:value=>{commands=value;}});
    // Always reuse the single native session on a verified orderly restart.
    let previous;try{previous=JSON.parse(await readFile(join(root,'checkpoint.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
    if(previous&&previous.phase!=='closed')throw new Error('Uncertain prior owner checkpoint; manual review required');
    if(!previous&&durable.status().workflows.length)throw new Error('Existing Durable workflows without an owner checkpoint; never adopt');
    const decision=(await import(new URL('./api/typesafe-system-one.js',aiURL))).classify;
    const loader=new sdk.DefaultResourceLoader({cwd:workspace,agentDir,settingsManager:settings,
      noExtensions:true,noSkills:true,noThemes:true,noPromptTemplates:true,noContextFiles:true,
      additionalExtensionPaths:[join(durableDir,'index.js')],extensionFactories:[extension,pi=>{
        pi.registerProvider('hyprneuro-decision',{apiKey:'local-no-credential',classifiers:{'typesafe-system-one':{classify:decision}},
          models:[{type:'classifier',id:'d1-omni-600m',name:'D1 advisory',api:'typesafe-system-one',baseUrl:'http://127.0.0.1:8083/v1',
            contextWindow:1024,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]});
      }]});
    await loader.reload();
    if(loader.getExtensions().errors.length)throw new Error('Pi/Durable extension load failed: '+JSON.stringify(loader.getExtensions().errors));
    const manager=previous?.session?sdk.SessionManager.open(previous.session):sdk.SessionManager.create(workspace,join(root,'sessions'));
    model??={id:'lfm-text',provider:'hyprneuro-local',api:'openai-completions',name:'lfm-text',baseUrl:'http://127.0.0.1:8081/v1',reasoning:false,
      input:['text'],contextWindow:131072,maxTokens:2048,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
    ({session}=await sdk.createAgentSession({cwd:workspace,agentDir,modelRuntime:runtime,model,sessionManager:manager,settingsManager:settings,
      resourceLoader:loader,thinkingLevel:'off',tools:['read','write','edit','bash','subagents']}));
    const singleSession=async()=>{throw new Error('Single owner session; reset/fork/reload requires trusted restart/review');};
    let errors=[];await session.bindExtensions({onError:error=>errors.push(error),commandContextActions:{
      waitForIdle:()=>session.waitForIdle(),newSession:singleSession,fork:singleSession,navigateTree:singleSession,switchSession:singleSession,reload:singleSession}});
    if(errors.length||!session.extensionRunner.getCommand('subagents')&&!session.getActiveToolNames().includes('subagents'))
      throw new Error('Native Durable unavailable in owner session: '+JSON.stringify(errors));
    const context=()=>session.extensionRunner.createCommandContext();
    async function activate() {
      if(activated)return;
      await session.extensionRunner.getCommand('hn-tools').handler(`${workspace} ${taskId} ${appId}`,context());activated=true;
    }
    const command=async value=>{
      if(value==='status')return commands.status();
      await activate();
      if(value==='on'&&owner.cancelOn)throw new Error('Pending on cancelled by trusted off');
      // This is a real trusted manual request, not model approval text. Native
      // Pi materializes its session at the first actual user/control request.
      session.sessionManager.appendMessage({role:'user',content:[{type:'text',text:`[Trusted UI requested MoE ${value}]`}],timestamp:Date.now()});
      return commands.moe(value==='on'?'start':'finish',context());
    };
    const recommend=route??((text,signal)=>recommendHermes(runtime,runtime.getAllModels().find(m=>m.provider==='hyprneuro-decision'),text,admit,signal));
    owner=new PiOwner({session,durable,command,checkpoint,route:recommend,settleParent:()=>session.waitForIdle(),cancelTransition:()=>commands.cancel(),prepare:async()=>{await activate();await context().waitForIdle();}});
    await checkpoint('ordinary');
    let shutdown;
    const close=()=>shutdown??=(async()=>{
      let safe=false;
      try {safe=await owner.close();}
      finally {
        await socket?.close();await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();await guard.close();
        if(safe){await unlink(join(root,'owner.guard'));await syncDirectory(root);}
      }
    })();
    if(serve)socket=await serveOwner(root,owner,{onControlDisconnect:()=>{void close().catch(()=>{});}});
    return {owner,session,runtime,durable,socket,close};
  } catch(error) {
    await socket?.close();if(session){await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();}
    await guard.close();throw error; // retain guard/checkpoint: no automatic unknown replay
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const required=name=>{if(!process.env[name])throw new Error('Explicit '+name+' required');return process.env[name];};
  const host=await createHost({sdkPath:required('HYPRNEURO_PI_SDK'),durableDir:required('HYPRNEURO_DURABLE_PACKAGE'),piBin:required('HYPRNEURO_PI_BIN'),
    root:required('HYPRNEURO_PI_OWNER_DIR'),workspace:required('HYPRNEURO_WORKSPACE'),taskId:required('HYPRNEURO_TASK_ID'),appId:required('HYPRNEURO_APP_ID')});
  let closing=false;
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{if(!closing){closing=true;host.close().then(()=>process.exit(),()=>process.exit(1));}});
}
