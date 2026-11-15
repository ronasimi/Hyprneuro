import {mockConsent} from './support/mock-consent.mjs';
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

test('UNSUPPORTED legacy/nonpersistent/Durable command owner profiles reject before SDK, inference or authorization',async()=>{
  const saved=process.env.HYPRNEURO_PI_OWNER_ENABLE;process.env.HYPRNEURO_PI_OWNER_ENABLE='1';
  const root=await mkdtemp(join(tmpdir(),'hn-unsupported-'));let calls=0;
  try {
    for(const flags of [{},{profile:'read-only',normalOnly:true,parentOnly:true,persistent:false},
      {profile:'read-only',normalOnly:true,parentOnly:false,persistent:true},
      {profile:'read-only',normalOnly:true,parentOnly:true,persistent:true,childRead:true}]) {
      await assert.rejects(createHost({root:join(root,'never-created'),workspace:'/never-opened',sdkPath:'/never-imported',
        rpc:async()=>{calls++;},...flags}),/Unsupported authorization profile/);
    }
    assert.equal(calls,0);await assert.rejects(readFile(join(root,'never-created','owner.guard')),{code:'ENOENT'});
    const script=`import asyncio,os,sys
async def main():
 p=await asyncio.create_subprocess_exec(sys.executable,'-m','hyprneuro.pi_desktop_bridge',
   env=dict(os.environ,HYPRNEURO_PI_UI='0',HYPRNEURO_PI_OWNER_DIR=sys.argv[1]),
   stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
 out,err=await p.communicate();assert p.returncode==2;assert out==b'';assert err==b''
asyncio.run(main())
`;
    const p=spawn('/usr/bin/python3',['-c',script,root],{env:{...process.env,PYTHONPATH:resolve('python/src')},stdio:['ignore','pipe','pipe']});
    let error='';p.stderr.on('data',data=>error+=data);
    assert.equal(await new Promise(r=>p.on('close',r)),0,error);
  } finally {if(saved===undefined)delete process.env.HYPRNEURO_PI_OWNER_ENABLE;else process.env.HYPRNEURO_PI_OWNER_ENABLE=saved;await rm(root,{recursive:true,force:true});}
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
