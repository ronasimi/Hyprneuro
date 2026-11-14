import { open,mkdir,readFile,writeFile,unlink,realpath,lstat } from 'node:fs/promises';
import { dirname,join,relative,isAbsolute } from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { harnessExtension } from '../tool-harness/index.mjs';
import { Workspace } from '../tool-harness/workspace.mjs';
import { checkBroker,sidecar } from '../tool-harness/policy.mjs';
import { admit } from '../tool-harness/residency.mjs';
import { Providers } from '../tool-harness/providers.mjs';
import { privateDirectory,serveOwner } from './socket.mjs';
import { PiOwner } from './owner.mjs';
import { recommendHermes } from './routing.mjs';
import { durablePolicy,durableRuntime } from './durable.mjs';

// Fixture-only read profile: native Durable discovery has no "builtins only"
// switch. Refuse ambient project agent/package configuration rather than claim
// --no-tools or DSA_SCOPE isolates discovery. Recheck before child admission.
async function readWorkspace(workspace,root) {
  const home=join(root,'home');
  if(!isAbsolute(root)||root!==await realpath(root)||workspace!==join(home,'workspace'))throw new Error('READ-ONLY workspace must be dedicated HOME/workspace beneath owner root');
  // Durable project discovery walks cwd ancestors until canonical HOME; user
  // discovery also reads HOME/.agents. Check that entire visible chain, including
  // HOME itself, before native discovery and each delegation preflight.
  for(let p=workspace;;p=dirname(p)) {
    const st=await lstat(p);
    if(p!==await realpath(p)||!st.isDirectory()||st.uid!==process.getuid()||(st.mode&0o022))throw new Error('Canonical owner-controlled dedicated read workspace/HOME required');
    for(const name of ['.pi','.agents','package.json']) {
      if(await lstat(join(p,name)).catch(e=>{if(e.code!=='ENOENT')throw e;}))throw new Error('READ-ONLY discovery metadata forbidden throughout workspace/HOME chain');
    }
    if(p===home)break;
  }
  for(let p=workspace;;p=dirname(p)) {
    if(await lstat(join(p,'.git')).catch(e=>{if(e.code!=='ENOENT')throw e;}))throw new Error('READ-ONLY dedicated workspace must be outside project discovery roots');
    if(p===dirname(p))break;
  }
}

// Explicit paths; no package install, auto-discovery, existing auth/token stores,
// service setup, or independent conversation framework.
export async function createHost({sdkPath,durableDir,piBin,root,workspace,taskId,appId,
    rpc=sidecar,model,native,providers,mcpAdapter,authorizeMcpDiscovery,route,serve=true,profile='standard',normalOnly=false,readPaths=[],childRead=false,parentOnly=false,persistent=false,textBaseUrl='http://127.0.0.1:8081/v1'}) {
  if(process.env.HYPRNEURO_PI_OWNER_ENABLE!=='1')throw new Error('Pi owner is opt-in and source/mock-only, not activated');
  if(!['standard','read-only'].includes(profile)||typeof normalOnly!=='boolean'||typeof childRead!=='boolean'||typeof parentOnly!=='boolean')throw new Error('Explicit supported owner profile/mode required');
  const readOnly=profile==='read-only';
  if(mcpAdapter){
    if(readOnly)throw new Error('READ-ONLY owner forbids native MCP adapters');
    if(providers)throw new Error('Choose one provider facade for the single owner session');
    if(!mcpAdapter.providers||!Array.isArray(mcpAdapter.extensions)||!Array.isArray(mcpAdapter.discovery)||!Array.isArray(mcpAdapter.nativeToolNames))
      throw new Error('Explicit guarded native MCP adapter required');
    if(mcpAdapter.discovery.length&&(!authorizeMcpDiscovery||await authorizeMcpDiscovery(mcpAdapter.discovery)!==true))
      throw new Error('Trusted discovery and credential/destination authorization required');
    providers=mcpAdapter.providers;
  }
  if(typeof persistent!=='boolean'||persistent&&(!parentOnly||!normalOnly||!readOnly||childRead))throw new Error('Persistent service requires normal-only parent READ-ONLY; no children');
  if(parentOnly&&(!readOnly||!normalOnly||childRead))throw new Error('Parent-only requires normal-only READ-ONLY and child-read disabled');
  if(normalOnly&&!readOnly||childRead&&!readOnly)throw new Error('Normal-only/child read require explicit READ-ONLY profile');
  if(readOnly&&(model||!Array.isArray(readPaths)||!readPaths.length||readPaths.length>32||workspace!==await realpath(workspace)))throw new Error('READ-ONLY requires canonical workspace, exact read allowlist and fixed local text model');
  if(readOnly){
    await readWorkspace(workspace,root);const scope=await Workspace.create(workspace);
    try{readPaths=Object.freeze([...new Set(readPaths.map(p=>scope.target(p)))].sort());}finally{await scope.close();}
  }
  const url=new URL(textBaseUrl);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||textBaseUrl!==url.origin+'/v1'||url.username||url.password||url.pathname!=='/v1'||url.search||url.hash)throw new Error('Explicit loopback text endpoint required');
  if(normalOnly&&process.env.HYPRNEURO_RESIDENCY_DIR)throw new Error('Normal-only owner cannot claim coordinator admission; use a separate explicit launch environment');
  if(!normalOnly&&!process.env.HYPRNEURO_RESIDENCY_DIR)throw new Error('All clients must explicitly share residency directory');
  const configuration={profile,normalOnly,workspace,taskId,appId,readPaths:readOnly?[...readPaths].sort():[],childRead,parentOnly,textBaseUrl,...(persistent?{persistent:true,runtime:{sdkPath,durableDir,piBin,host:fileURLToPath(import.meta.url)}}:{})};
  process.umask(0o077); // Dedicated owner and its native children create private files/dirs.
  await privateDirectory(root);
  const rel=relative(workspace,root);
  if(!isAbsolute(workspace)||!rel||!(rel==='..'||rel.startsWith('../')||isAbsolute(rel)))throw new Error('Owner secrets must be outside the explicit workspace');
  const guard=await open(join(root,'owner.guard'),'wx',0o600).catch(()=>{throw new Error('Previous/live owner exists; review unknown outcomes, never adopt');});
  const syncDirectory=async path=>{const fd=await open(path,'r');try{await fd.sync();}finally{await fd.close();}};
  await guard.sync();await syncDirectory(root); // durable guard BEFORE any runtime effect
  let owner,session,socket;
  const checkpoint=async phase=>{
    let persistedSession;
    if(session?.sessionManager.getSessionFile()) {
      session.sessionManager.appendCustomEntry('hyprneuro.pi-owner/1',{phase});
      try {
        const file=session.sessionManager.getSessionFile();
        const fd=await open(file,'r+');try{await fd.sync();}finally{await fd.close();}
        await syncDirectory(dirname(file));persistedSession=file;
      } catch(error) {
        // Native Pi intentionally keeps setup-only sessions in memory. Never
        // fabricate an assistant reply merely to force persistence.
        if(error.code!=='ENOENT'||session.sessionManager.getEntries().some(e=>e.type==='message'&&['user','assistant'].includes(e.message.role)))throw error;
      }
    }
    const fd=await open(join(root,'checkpoint.json'),'w',0o600);
    try {await fd.writeFile(JSON.stringify({phase,session:persistedSession,configuration}));await fd.sync();}finally{await fd.close();}
    await syncDirectory(root);
  };
  try {
    // Validate restart identity BEFORE loading an SDK/provider from the runtime
    // descriptor. Never adopt a changed configuration or uncertain journal.
    let previous;try{previous=JSON.parse(await readFile(join(root,'checkpoint.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
    if(previous&&(previous.configuration?JSON.stringify(previous.configuration)!==JSON.stringify(configuration):readOnly))throw new Error('Owner configuration changed; fresh root or explicit manual review required');
    if(previous&&previous.phase!=='closed')throw new Error('Uncertain prior owner checkpoint; manual review required');
    const agentDir=join(root,'agent'),home=join(root,'durable');
    await privateDirectory(agentDir);await privateDirectory(home);
    if(readOnly){
      const isolatedHome=join(root,'home');await privateDirectory(isolatedHome);
      process.env.HOME=isolatedHome;process.env.PI_OFFLINE='1';delete process.env.PI_SUBAGENT_EXTRA_AGENT_DIRS;
      process.chdir(workspace); // dedicated owner process only, never embed in parent
      const configFile=join(home,'config.json');
      try{await writeFile(configFile,JSON.stringify({exactCapture:false,k:{lossBound:1}}),{flag:'wx',mode:0o600});}
      catch(e){if(e.code!=='EEXIST')throw e;const config=JSON.parse(await readFile(configFile,'utf8'));if(config.k?.lossBound!==1||config.exactCapture!==false)throw new Error('READ-ONLY dedicated Durable requires lossBound=1 and exactCapture=false; no automatic child replay');}
      const settings=JSON.stringify({retry:{enabled:false,provider:{maxRetries:0}},compaction:{enabled:false},cacheWarming:'off',subagents:{agentOverrides:{delegate:{inheritProjectContext:false,inheritSkills:false,skills:[],tools:[],defaultContext:'fresh'}}}});
      const file=join(agentDir,'settings.json');
      try{await writeFile(file,settings,{flag:'wx',mode:0o600});}catch(e){if(e.code!=='EEXIST'||await readFile(file,'utf8')!==settings)throw new Error('Dedicated read profile settings changed; manual review required');}
    }
    const sdk=await import(pathToFileURL(sdkPath));
    const aiURL=new URL('../../pi-ai/dist/index.js',pathToFileURL(sdkPath));
    native??={lazyStream:(await import(aiURL)).lazyStream,streamSimple:(await import(new URL('./api/openai-completions.js',aiURL))).streamSimple};
    // Dedicated home only; never drain/resume the parent's existing workflows.
    process.env.DSA_HOME=home;process.env.DSA_CACHE_HOME=join(home,'cache');process.env.DSA_SCOPE='off';process.env.PI_CODING_AGENT_DIR=agentDir;
    for(const key of ['DSA_SESSION','DSA_EXEC','DSA_CALL','DSA_INBOX','DSA_JOURNAL','DSA_SCHEMA','DSA_BUDGET','DSA_MODEL','DSA_RESULT','DSA_OUTPUT','DSA_PROBE','DSA_ORCHESTRATOR_ENTRY'])delete process.env[key];
    const stat=await readFile(`/proc/${process.pid}/stat`,'utf8');
    process.env.HYPRNEURO_PI_OWNER_ID=process.pid+':'+stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s+/)[19];
    const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
    const child=fileURLToPath(new URL('./child.ts',import.meta.url));
    const launcher=join(root,'pi-child');
    if(!isAbsolute(piBin))throw new Error('Explicit installed Pi executable required');
    await writeFile(launcher,`#!/bin/sh\nexport HYPRNEURO_PI_NORMAL_ONLY=${quote(normalOnly?'1':'0')} HYPRNEURO_PI_TEXT_URL=${quote(textBaseUrl)} HYPRNEURO_PI_CHILD_READ_DIR=${quote(childRead?root:'')}\nexec ${quote(piBin)} --offline --no-extensions --no-skills --no-context-files --no-prompt-templates -e ${quote(child)} "$@"\n`,{mode:0o700});
    process.env.DSA_PI_BIN=launcher;
    const durable=await durableRuntime(durableDir,home,{...process.env});
    let commands,activated=false;
    const settings=sdk.SettingsManager.inMemory({retry:{enabled:false,provider:{maxRetries:0}},compaction:{enabled:false},cacheWarming:'off'});
    const runtime=await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:null,modelsStorePath:join(agentDir,'models-store.json'),refreshOnCreate:false,allowModelNetwork:false});
    const approvedChildReads=new Set();
    const policy=durablePolicy({workspace,preflight:()=>readWorkspace(workspace,root),readOnly,childRead,onReadApproved:request=>approvedChildReads.add(request),phase:()=>owner?.closing?'closed':owner?.phase??'closed',
      broker:op=>checkBroker(rpc,taskId,appId,op,workspace),approve:request=>owner.approve(request)});
    providers=readOnly?undefined:providers??await Providers.load();
    const extension=harnessExtension(sdk,{rpc,providers,native,readOnly,normalOnly,parentOnly,readPaths,textBaseUrl,binding:Object.freeze({workspace,taskId,appId}),confirm:request=>owner.approve(request),durableGuard:policy,
      toolAdmission:()=>{if(owner?.closing||!['ordinary','hermes'].includes(owner?.phase))throw new Error('Owner transition blocks new tool side effects');},
      inferenceGate:(role,token)=>{
        if(owner?.closing||!['ordinary','hermes'].includes(owner?.phase))throw new Error('Owner transition blocks native background inference');
        if(normalOnly){if(role!=='text'||token)throw new Error('Normal-only owner permits existing text only; no exclusive admission');return async()=>{};}
        return admit(role,token);
      },ownerControl:value=>value==='status'?owner.status():owner.transition(value),exposeCommands:value=>{commands=value;}});
    if(parentOnly&&durable.status().workflows.length)throw new Error('Parent-only root contains unexpected Durable work; manual review required');
    if(!previous&&durable.status().workflows.length)throw new Error('Existing Durable workflows without an owner checkpoint; never adopt');
    const decision=(await import(new URL('./api/typesafe-system-one.js',aiURL))).classify;
    const loader=new sdk.DefaultResourceLoader({cwd:workspace,agentDir,settingsManager:settings,
      noExtensions:true,noSkills:true,noThemes:true,noPromptTemplates:true,noContextFiles:true,
      additionalExtensionPaths:parentOnly?[]:[join(durableDir,'index.js')],extensionFactories:[...(mcpAdapter?.extensions??[]),extension,...(normalOnly?[]:[pi=>{
        pi.registerProvider('hyprneuro-decision',{apiKey:'local-no-credential',classifiers:{'typesafe-system-one':{classify:decision}},
          models:[{type:'classifier',id:'d1-omni-600m',name:'D1 advisory',api:'typesafe-system-one',baseUrl:'http://127.0.0.1:8083/v1',
            contextWindow:1024,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]});
      }])]});
    await loader.reload();
    if(loader.getExtensions().errors.length)throw new Error('Pi/Durable extension load failed: '+JSON.stringify(loader.getExtensions().errors));
    const manager=previous?.session?sdk.SessionManager.open(previous.session):sdk.SessionManager.create(workspace,join(root,'sessions'));
    model??={id:'lfm-text',provider:'hyprneuro-local',api:'openai-completions',name:'lfm-text',baseUrl:textBaseUrl,reasoning:false,
      input:['text'],contextWindow:131072,maxTokens:2048,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
    ({session}=await sdk.createAgentSession({cwd:workspace,agentDir,modelRuntime:runtime,model,sessionManager:manager,settingsManager:settings,
      resourceLoader:loader,thinkingLevel:'off',tools:parentOnly?['read']:readOnly?['read','subagents']:['read','write','edit','bash','subagents',...(providers?.names??[]),...(mcpAdapter?.nativeToolNames??[])]}));
    const singleSession=async()=>{throw new Error('Single owner session; reset/fork/reload requires trusted restart/review');};
    let errors=[];await session.bindExtensions({onError:error=>errors.push(error),commandContextActions:{
      waitForIdle:()=>session.waitForIdle(),newSession:singleSession,fork:singleSession,navigateTree:singleSession,switchSession:singleSession,reload:singleSession}});
    if(parentOnly)session.setActiveToolsByName(['read']);
    else if(mcpAdapter)session.setActiveToolsByName(['read','write','edit','bash','subagents']);
    if(errors.length||!parentOnly&&!session.extensionRunner.getCommand('subagents')&&!session.getActiveToolNames().includes('subagents'))
      throw new Error('Native Durable unavailable in owner session: '+JSON.stringify(errors));
    const context=()=>session.extensionRunner.createCommandContext();
    async function activate() {
      if(activated)return;
      await session.extensionRunner.getCommand('hn-tools').handler(`${workspace} ${taskId} ${appId}`,context());activated=true;
    }
    const command=async value=>{
      if(value==='status'){const status=await commands.status();return normalOnly?{...status,normal_only:true,parent_only:parentOnly,persistent,tools:session.getCallableToolNames(),task_id:taskId,app_id:appId,tool_permission:activated?'fresh_read_consent':'activation_required',workspace,read_paths:readPaths,session_id:session.sessionManager.getSessionId()}:status;}
      if(normalOnly)throw new Error('Lifecycle unavailable: normal-only owner; all-client cooperation unverified');
      await activate();
      if(value==='on'&&owner.cancelOn)throw new Error('Pending on cancelled by trusted off');
      // This is a real trusted manual request, not model approval text. Native
      // Pi materializes its session at the first actual user/control request.
      session.sessionManager.appendMessage({role:'user',content:[{type:'text',text:`[Trusted UI requested MoE ${value}]`}],timestamp:Date.now()});
      return commands.moe(value==='on'?'start':'finish',context());
    };
    const recommend=route??((text,signal)=>recommendHermes(runtime,runtime.getAllModels().find(m=>m.provider==='hyprneuro-decision'),text,admit,signal));
    owner=new PiOwner({session,durable:parentOnly?{...durable,quiesce:async()=>{if(durable.status().workflows.length)throw new Error('Unexpected parent-only Durable work; no automatic drain/adoption');}}:durable,command,lifecycleUnavailable:normalOnly?'Lifecycle unavailable: normal-only owner; all-client cooperation unverified':undefined,checkpoint,route:recommend,settleParent:()=>session.waitForIdle(),cancelTransition:()=>commands.cancel(),prepare:async()=>{
        if(persistent&&(!owner.listeners.size||owner.detaching))throw new Error('Trusted UI required; owner idle/disconnected');
        if(persistent&&!activated){
          await checkpoint('activation-intent');
          try{await activate();await checkpoint('ordinary');}
          catch(error){if(error.code!=='HUMAN_DENIED')owner.phase='failed';await checkpoint(owner.phase==='failed'?'activation-unknown':'ordinary');throw error;}
        }else await activate();
        await context().waitForIdle();
      },
      detach:persistent?async()=>{activated=false;await commands.disable();session.setActiveToolsByName(['read']);}:undefined});
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
    if(serve||childRead)socket=await serveOwner(root,owner,{singleControl:persistent,read:childRead?async(packet,signal)=>{
      if(owner.closing||owner.phase!=='ordinary')throw new Error('Owner read admission closed');
      if(typeof packet.call!=='string'||packet.call.length>256||typeof packet.exec!=='string'||!packet.exec.startsWith(packet.call+'#')||!/^\d+\.\d+$/.test(packet.exec.slice(packet.call.length+1))||typeof packet.tool_id!=='string'||!/^[\w-]{1,128}$/.test(packet.tool_id))throw new Error('Bounded native child identity required');
      await durable.readChild(packet.call,packet.exec,approvedChildReads,workspace);
      const result=await commands.read('child:'+packet.call+':'+packet.tool_id,packet.args,signal,context());
      if(Buffer.byteLength(JSON.stringify(result))>60000)throw new Error('Child read result exceeds bridge bound; inspect journal, never replay');
      return result;
    }:undefined,onControlDisconnect:()=>{if(owner.closing||owner.closed)return;void (persistent?owner.detachControl():close()).catch(()=>console.error('Pi owner cleanup failed; manual checkpoint review required'));}});
    return {owner,session,runtime,durable,socket,close};
  } catch(error) {
    await socket?.close();if(session){await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();}
    await guard.close();throw error; // retain guard/checkpoint: no automatic unknown replay
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const required=name=>{if(!process.env[name])throw new Error('Explicit '+name+' required');return process.env[name];};
  const mode=process.env.HYPRNEURO_PI_OWNER_MODE??'coordinated';
  if(!['coordinated','normal-only'].includes(mode))throw new Error('Explicit supported owner mode required');
  const host=await createHost({sdkPath:required('HYPRNEURO_PI_SDK'),durableDir:required('HYPRNEURO_DURABLE_PACKAGE'),piBin:required('HYPRNEURO_PI_BIN'),
    root:required('HYPRNEURO_PI_OWNER_DIR'),workspace:required('HYPRNEURO_WORKSPACE'),taskId:required('HYPRNEURO_TASK_ID'),appId:required('HYPRNEURO_APP_ID'),
    profile:process.env.HYPRNEURO_PI_OWNER_PROFILE??'standard',normalOnly:mode==='normal-only',
    childRead:process.env.HYPRNEURO_PI_CHILD_READ==='1',parentOnly:process.env.HYPRNEURO_PI_PARENT_ONLY==='1',persistent:process.env.HYPRNEURO_PI_PERSISTENT==='1',readPaths:JSON.parse(process.env.HYPRNEURO_PI_READ_PATHS??'[]')});
  let closing=false;
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{if(!closing){closing=true;host.close().then(()=>process.exit(),()=>process.exit(1));}});
}
