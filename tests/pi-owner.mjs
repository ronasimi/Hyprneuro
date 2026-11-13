import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {createHost} from '../extensions/pi-owner/host.mjs';

const sdkPath=process.env.PI_HARNESS_SDK;
const durableDir=process.env.PI_HARNESS_DURABLE;
if(!sdkPath||!durableDir)throw new Error('Explicit installed PI_HARNESS_SDK and PI_HARNESS_DURABLE required; no installs');

test('real single Pi session loads native Durable; persistent chat + command workflow + child drain',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-owner-')),saved={...process.env};
  let host,requests=0,workspace,delegate=false;
  const server=createServer(async(req,res)=>{
    requests++;for await(const _ of req){}
    res.writeHead(200,{'content-type':'text/event-stream'});
    const args={action:'run',request:'actual-command',command:[process.execPath,'-e',
      "require('fs').writeFileSync('started','yes');setTimeout(()=>require('fs').appendFileSync('durable.txt','x'),400)"],cwd:workspace,timeoutMs:2000};
    const choice=delegate?{index:0,delta:{tool_calls:[{index:0,id:'delegate_1',type:'function',function:{name:'subagents',arguments:JSON.stringify(args)}}]},finish_reason:'tool_calls'}:
      {index:0,delta:{content:'native Pi answer'},finish_reason:'stop'};
    delegate=false;
    res.end('data: '+JSON.stringify({choices:[choice]})+'\n\ndata: [DONE]\n\n');
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  try {
    workspace=join(root,'workspace');await mkdir(workspace);
    const state=join(root,'residency');await mkdir(state,{mode:0o700});
    process.env.HYPRNEURO_PI_OWNER_ENABLE='1';process.env.HYPRNEURO_RESIDENCY_DIR=state;
    const ownerRoot=join(root,'owner');await mkdir(join(ownerRoot,'durable'),{recursive:true,mode:0o700});
    await writeFile(join(ownerRoot,'durable','config.json'),JSON.stringify({exactCapture:false,k:{idleExitMs:200}}),{mode:0o600});
    const model={id:'mock',provider:'hn-mock',api:'openai-completions',baseUrl:`http://127.0.0.1:${server.address().port}/v1`,
      input:['text'],reasoning:false,contextWindow:1000,maxTokens:100,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
      compat:{supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:false,maxTokensField:'max_tokens'}};
    const options={sdkPath,durableDir,piBin:'/home/ron/.pi/agent/bin/pi',root:ownerRoot,workspace,taskId:'test',appId:'test',serve:false,
      providers:{names:[]},model,rpc:async packet=>packet.action==='auth_check'?{allowed:true}:{authorized:true}};
    host=await createHost(options);
    host.runtime.registerProvider('hn-mock',{baseUrl:model.baseUrl,api:'openai-completions',apiKey:'local',models:[{...model,name:'mock'}]});
    const approve=event=>{if(event.type==='consent')host.owner.consent(event.id,true);};host.owner.listeners.add(approve);
    await assert.rejects(createHost({sdkPath,durableDir,piBin:'/home/ron/.pi/agent/bin/pi',root:ownerRoot,workspace}),/Previous\/live owner/);
    const id=host.session.sessionManager.getSessionId();
    const streamed=[];await host.owner.chat({text:'first'},event=>streamed.push(event));
    assert.equal(streamed.filter(e=>e.type==='delta').map(e=>e.text).join(''),'native Pi answer');
    assert.ok(streamed.some(e=>e.type==='turn_end'&&e.stopReason==='stop'&&typeof e.usage==='object'));
    await host.owner.chat({text:'second'},()=>{});
    assert.equal(requests,2);
    await host.owner.chat({text:'/moe on'},()=>{}); // RPC text must NOT dispatch registered trusted commands.
    assert.equal(requests,3);assert.equal(host.session.sessionManager.getSessionId(),id);
    assert.ok(host.session.getActiveToolNames().includes('subagents'));
    assert.ok(host.session.sessionManager.getEntries().filter(e=>e.type==='message'&&e.message.role==='user').length>=2);
    delegate=true;
    await host.owner.chat({text:'Run approved Durable command'},()=>{});
    assert.ok(host.session.extensionRunner.getCommand('moe'));
    const deadline=Date.now()+10000;
    while(true) {
      try{await readFile(join(workspace,'started'));break;}catch(error){if(error.code!=='ENOENT')throw error;}
      if(Date.now()>deadline)assert.fail('Native Durable command never started');
      await new Promise(r=>setTimeout(r,20));
    }
    await host.durable.quiesce(10000); // paused flag alone must NOT end this wait
    assert.equal(await readFile(join(workspace,'durable.txt'),'utf8'),'x');
    const workflows=host.durable.status().workflows;
    assert.equal(workflows.length,1);
    const receipt=await host.durable.describe(workflows[0].wid);
    assert.equal(receipt.calls[0].status,'ok');
    await host.durable.resume();
    delegate=true;
    await host.owner.chat({text:'Retry same durable request'},()=>{});
    assert.equal(await readFile(join(workspace,'durable.txt'),'utf8'),'x');
    assert.equal(host.session.sessionManager.getSessionId(),id);
    await host.close();host=undefined;
    host=await createHost({...options,serve:true});
    host.runtime.registerProvider('hn-mock',{baseUrl:model.baseUrl,api:'openai-completions',apiKey:'local',models:[{...model,name:'mock'}]});
    host.owner.listeners.add(event=>{if(event.type==='consent')host.owner.consent(event.id,true);});
    assert.equal(host.session.sessionManager.getSessionId(),id);
    const script=`import asyncio,sys
from hyprneuro.pi_owner_client import PiOwnerClient
async def main():
 c=await PiOwnerClient.connect(sys.argv[1],trusted=True)
 assert (await c.call('chat',text='after orderly restart'))['settled']
 events=[]
 while not c.events.empty(): events.append(c.events.get_nowait())
 assert any(e.get('event',{}).get('type')=='delta' for e in events)
 await c.close()
asyncio.run(main())
`;
    const p=spawn('/usr/bin/python3',['-c',script,ownerRoot],{env:{...process.env,PYTHONPATH:resolve('python/src')},stdio:['ignore','pipe','pipe']});
    let error='';p.stderr.on('data',data=>error+=data);
    assert.equal(await new Promise(r=>p.on('close',r)),0,error);
    await host.close();host=undefined;
    // Native orchestrator idle-exits; do not remove journals while it still owns them.
    const {pathToFileURL}=await import('node:url');
    const {readerLedger}=await import(pathToFileURL(join(durableDir,'dist/orchestrator/reader-ledger.js')));
    const {processAlive}=await import(pathToFileURL(join(durableDir,'dist/orchestrator/snapshot.js')));
    const until=Date.now()+5000;
    while(true){const o=readerLedger(join(ownerRoot,'durable')).state.state.orchestrator;if(!o||o.exited||!processAlive(o.pid,o.start))break;
      if(Date.now()>until)assert.fail('Owned temporary Durable orchestrator did not idle-exit');await new Promise(r=>setTimeout(r,25));}
  } finally {
    await host?.close().catch(()=>{});server.closeAllConnections();await new Promise(r=>server.close(r));
    for(const k of Object.keys(process.env))if(!(k in saved))delete process.env[k];Object.assign(process.env,saved);
    await rm(root,{recursive:true,force:true});
  }
});

test('actual Pi classifier/SystemOne schema recommends only after admitted D1 completion',async()=>{
  const {pathToFileURL}=await import('node:url');
  const sdk=await import(pathToFileURL(sdkPath));
  const aiURL=new URL('../../pi-ai/dist/index.js',pathToFileURL(sdkPath));
  const {classify}=await import(new URL('./api/typesafe-system-one.js',aiURL));
  const {recommendHermes}=await import('../extensions/pi-owner/routing.mjs');
  const root=await mkdtemp(join(tmpdir(),'hn-classify-'));let request;let released=false,score=.9,stall=false;
  const server=createServer(async(req,res)=>{
    let raw='';for await(const c of req)raw+=c;request={url:req.url,body:JSON.parse(raw)};
    if(stall)return;
    res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({answers:{escalate:{type:'noul',noul:score,route:'untrusted',consent:true}}}));
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  try {
    const runtime=await sdk.ModelRuntime.create({authPath:join(root,'auth.json'),modelsPath:null,modelsStorePath:join(root,'models.json'),refreshOnCreate:false,allowModelNetwork:false});
    const model={type:'classifier',id:'d1',name:'D1',api:'typesafe-system-one',baseUrl:`http://127.0.0.1:${server.address().port}/v1`,
      input:['text'],contextWindow:1024,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
    runtime.registerProvider('test-d1',{apiKey:'local',classifiers:{'typesafe-system-one':{classify}},models:[model]});
    const result=await recommendHermes(runtime,runtime.getAllModels().find(m=>m.provider==='test-d1'),'x'.repeat(1200),async role=>{
      assert.equal(role,'decision');return async()=>{released=true;};
    });
    assert.equal(result.route,'hermes');assert.equal(result.score,.9);assert.equal(released,true);
    assert.equal(request.url,'/v1/systemone');
    assert.equal(request.body.questions.escalate.type,'noul');
    assert.equal(request.body.state.request.length,800);
    const selected=runtime.getAllModels().find(m=>m.provider==='test-d1');
    for(const [value,route] of [[0,'current'],[.74999,'current'],[.75,'hermes'],[1,'hermes']]) {
      score=value;const answer=await recommendHermes(runtime,selected,'only current request',async()=>async()=>{});
      assert.deepEqual(answer,{route,score:value});
    }
    for(const value of [-.1,1.1,'0.9',null]) {
      score=value;assert.deepEqual(await recommendHermes(runtime,selected,'x',async()=>async()=>{}),{route:'current',unavailable:true});
    }
    stall=true;released=false;const cancel=new AbortController();
    const cancelled=recommendHermes(runtime,selected,'cancel this D1 request',async()=>async()=>{released=true;},cancel.signal);
    setTimeout(()=>cancel.abort(),20);
    assert.deepEqual(await cancelled,{route:'current',unavailable:true});assert.equal(released,true);
    released=false;
    assert.deepEqual(await recommendHermes(runtime,selected,'timeout',async()=>async()=>{released=true;},AbortSignal.timeout(20)),{route:'current',unavailable:true});
    assert.equal(released,true);
    const unavailable=await recommendHermes(runtime,model,'routine',async()=>{throw new Error('D1 inactive');});
    assert.deepEqual(unavailable,{route:'current',unavailable:true});
  } finally {server.closeAllConnections();await new Promise(r=>server.close(r));await rm(root,{recursive:true,force:true});}
});

test('actual Pi loader accepts dedicated child extension and denies every nonprotocol tool',async()=>{
  const {pathToFileURL}=await import('node:url');const sdk=await import(pathToFileURL(sdkPath));
  const root=await mkdtemp(join(tmpdir(),'hn-child-'));let session;
  try {
    const settings=sdk.SettingsManager.inMemory({retry:{enabled:false},compaction:{enabled:false},cacheWarming:'off'});
    const runtime=await sdk.ModelRuntime.create({authPath:join(root,'auth.json'),modelsPath:null,modelsStorePath:join(root,'models.json'),refreshOnCreate:false,allowModelNetwork:false});
    const loader=new sdk.DefaultResourceLoader({cwd:root,agentDir:root,settingsManager:settings,noExtensions:true,noSkills:true,noContextFiles:true,
      additionalExtensionPaths:[new URL('../extensions/pi-owner/child.ts',import.meta.url).pathname]});
    await loader.reload();assert.deepEqual(loader.getExtensions().errors,[]);
    ({session}=await sdk.createAgentSession({cwd:root,agentDir:root,modelRuntime:runtime,resourceLoader:loader,settingsManager:settings,
      sessionManager:sdk.SessionManager.inMemory(),tools:[],model:{provider:'hyprneuro-local',id:'lfm-text',api:'openai-completions',baseUrl:'http://127.0.0.1:8081/v1',input:['text'],contextWindow:1000,maxTokens:100,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}}));
    await session.bindExtensions({});
    for(const name of ['read','write','edit','bash','subagents','moe']) {
      const result=await session.extensionRunner.emitToolCall({type:'tool_call',toolName:name,toolCallId:'test',input:{}});
      assert.equal(result.block,true);assert.equal(result.terminate,true);
    }
    for(const name of ['ask','report'])assert.equal(await session.extensionRunner.emitToolCall({type:'tool_call',toolName:name,toolCallId:'test',input:{}}),undefined);
  } finally {if(session){await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();}await rm(root,{recursive:true,force:true});}
});

test('actual Pi loader accepts standalone TypeScript harness entry without subpath-alias failure',async()=>{
  const {pathToFileURL}=await import('node:url');const sdk=await import(pathToFileURL(sdkPath));
  const root=await mkdtemp(join(tmpdir(),'hn-entry-')),saved=process.env.XDG_CONFIG_HOME;
  try {
    process.env.XDG_CONFIG_HOME=root;
    const loader=new sdk.DefaultResourceLoader({cwd:root,agentDir:root,settingsManager:sdk.SettingsManager.inMemory(),
      noExtensions:true,noSkills:true,noContextFiles:true,additionalExtensionPaths:[new URL('../extensions/tool-harness.ts',import.meta.url).pathname]});
    await loader.reload();assert.deepEqual(loader.getExtensions().errors,[]);assert.equal(loader.getExtensions().extensions.length,1);
  } finally {if(saved===undefined)delete process.env.XDG_CONFIG_HOME;else process.env.XDG_CONFIG_HOME=saved;await rm(root,{recursive:true,force:true});}
});
