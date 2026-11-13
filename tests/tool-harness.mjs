import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, symlink, link, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createServer } from 'node:http';
import { Workspace, exactEdits } from '../extensions/tool-harness/workspace.mjs';
import { harnessExtension } from '../extensions/tool-harness/index.mjs';

const sdkPath = process.env.PI_HARNESS_SDK;
if (!sdkPath) throw new Error('Set PI_HARNESS_SDK to installed Pi dist/index.js (no installs performed)');
const sdk = await import(pathToFileURL(sdkPath));

async function fixture(run) {
  const root = await mkdtemp(join(tmpdir(),'hn-pi-'));
  try { await run(root); } finally { await rm(root,{recursive:true,force:true}); }
}

test('workspace escape, symlink, hardlink and exact original edits', () => fixture(async root => {
  const dir = join(root,'workspace'); await mkdir(dir);
  const outside = join(root,'outside'); await writeFile(outside,'untouched');
  await symlink(outside,join(dir,'link')); await symlink(root,join(dir,'dirlink'));
  await link(outside,join(dir,'hard'));
  const w = await Workspace.create(dir);
  try {
    for (const p of ['../outside',outside,'link','dirlink/outside','hard','.env','.ssh/key'])
      await assert.rejects(() => w.write(p,'bad'));
    assert.equal(await readFile(outside,'utf8'),'untouched');
    await w.write('sub/a','one\ntwo\nthree');
    assert.equal((await w.read('sub/a')).toString(),'one\ntwo\nthree');
    assert.throws(() => exactEdits(Buffer.from('aaa'),[{oldText:'aa',newText:'b'}]),/uniquely/);
    assert.throws(() => exactEdits(Buffer.from('abc'),[{oldText:'ab',newText:'b'},{oldText:'bc',newText:'d'}]),/Overlapping/);
  } finally { await w.close(); }
}));

async function sessionFixture(root, {approve=true, responses, rpc: customRpc} = {}) {
  const workspace = join(root,'workspace'); await mkdir(workspace,{recursive:true});
  const agentDir = join(root,'agent'); await mkdir(agentDir,{recursive:true});
  const requests = [], confirmations = [], errors = [], policy = [];
  let phase = 0;
  const http = createServer(async (req,res) => {
    try {
      let body = ''; for await (const c of req) body += c;
      requests.push(JSON.parse(body));
      res.writeHead(200,{'content-type':'text/event-stream'});
      const response = responses[phase++];
      if (response === 'stall') return;
      const objects = typeof response === 'function' ? response(requests.at(-1)) : response;
      for (const object of objects) {
        const data = 'data: ' + JSON.stringify({id:'mock',object:'chat.completion.chunk',created:1,model:'mock',choices:[{index:0,...object}]}) + '\n\n';
        // Independent TCP/SSE fragment boundaries; actual Pi OpenAI adapter parses.
        for (let i=0;i<data.length;i+=7) res.write(data.slice(i,i+7));
      }
      res.end('data: [DONE]\n\n');
    } catch(e) { errors.push(e); res.destroy(); }
  });
  await new Promise(r => http.listen(0,'127.0.0.1',r));
  const rpc = customRpc ?? (async message => {policy.push(message); return message.action === 'auth_check' ? {allowed:true,reason:'ok'} : {authorized:true};});
  const extension = harnessExtension(sdk, {rpc, initial:{workspace,taskId:'test',appId:'test-app'},
    confirm:async request => {confirmations.push(request); return approve;}});
  const settings = sdk.SettingsManager.inMemory({retry:{enabled:false,provider:{maxRetries:0}},compaction:{enabled:false},cacheWarming:'off'});
  const loader = new sdk.DefaultResourceLoader({cwd:workspace,agentDir,settingsManager:settings,
    noExtensions:true,noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,
    extensionFactories:[extension]});
  await loader.reload();
  const runtime = await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:null,
    modelsStorePath:join(agentDir,'models-store.json'),refreshOnCreate:false,allowModelNetwork:false});
  runtime.registerProvider('hn-mock',{baseUrl:`http://127.0.0.1:${http.address().port}/v1`,apiKey:'mock-local-only',api:'openai-completions',
    models:[{id:'mock',name:'mock',reasoning:false,input:['text'],contextWindow:32768,maxTokens:1024,
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0},compat:{supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:false,maxTokensField:'max_tokens'}}]});
  const manager = sdk.SessionManager.create(workspace,join(root,'sessions'));
  const {session} = await sdk.createAgentSession({cwd:workspace,agentDir,modelRuntime:runtime,
    model:runtime.getModel('hn-mock','mock'),thinkingLevel:'off',resourceLoader:loader,
    settingsManager:settings,sessionManager:manager,tools:['read','write','edit','bash']});
  const events = []; session.subscribe(e => events.push(e));
  await session.bindExtensions({onError:e=>errors.push(e)});
  return {session,manager,workspace,requests,confirmations,events,errors,policy,
    async close(){await session.abort();session.dispose();http.closeAllConnections();await new Promise(r=>http.close(r));}};
}
const tool = (name,args,id='call_1') => [
  {delta:{role:'assistant',tool_calls:[{index:0,id,type:'function',function:{name,arguments:JSON.stringify(args).slice(0,10)}}]}},
  {delta:{tool_calls:[{index:0,function:{arguments:JSON.stringify(args).slice(10)}}]}},
  {delta:{},finish_reason:'tool_calls'}];
const stop = [{delta:{role:'assistant',content:'Verified.'}},{delta:{},finish_reason:'stop'}];

test('real Pi SDK OpenAI stream -> approval -> actual write -> result continuation -> persistent resume', () => fixture(async root => {
  const f = await sessionFixture(root,{responses:[tool('write',{path:'made.txt',content:'actual Pi tool'}), request => {
    assert.equal(request.messages.at(-1).role,'tool');
    assert.match(request.messages.at(-1).content,/Successfully/);
    return stop;
  }]});
  try {
    await f.session.prompt('Create the file');
    assert.deepEqual(f.errors,[]);
    assert.equal(await readFile(join(f.workspace,'made.txt'),'utf8'),'actual Pi tool');
    assert.equal(f.requests.length,2);
    assert.equal(f.confirmations.length,2); // activation plus actual exact call
    assert.ok(f.events.some(e=>e.type==='tool_execution_end' && !e.isError));
    assert.ok(f.events.some(e=>e.type==='agent_settled'));
    const path = f.manager.getSessionFile();
    const reopened = sdk.SessionManager.open(path);
    assert.ok(reopened.getEntries().some(e=>e.type==='message' && e.message.role==='toolResult'));
    assert.ok(reopened.getEntries().some(e=>e.customType==='hyprneuro.tool-call/1' && e.data.status==='completed'));
  } finally {await f.close();}
}));

test('model approval strings cannot authorize; broker denial and abort use Pi lifecycle', () => fixture(async root => {
  const f = await sessionFixture(root,{responses:[tool('write',{path:'no',content:'bad',approved:true}),stop]});
  try {
    await f.session.prompt('attempt model self approval');
    await assert.rejects(()=>readFile(join(f.workspace,'no')));
    assert.ok(f.events.some(e=>e.type==='tool_execution_end' && e.isError));
    assert.equal(f.confirmations.length,1);
  } finally {await f.close();}
}));

test('Pi session abort stops a stalled real HTTP stream', () => fixture(async root => {
  const f = await sessionFixture(root,{responses:['stall']});
  try {
    const run = f.session.prompt('wait');
    while (!f.requests.length) await new Promise(r=>setTimeout(r,10));
    await f.session.abort(); await run;
    assert.ok(f.events.some(e=>e.type==='agent_settled' && e.aborted));
  } finally {await f.close();}
}));
