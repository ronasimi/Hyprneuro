import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,cp,readFile,rm,writeFile } from 'node:fs/promises';
import { join,dirname } from 'node:path';
import { pathToFileURL,fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { createNativeMcpProviders,boundedMcpResult,validateMcpArguments,MCP_MAX_TEXT } from '../extensions/tool-harness/native-mcp.mjs';

if(!process.env.PI_HARNESS_SDK)throw new Error('PI_HARNESS_SDK required; installed SDK only, no installs');
const sdkURL=pathToFileURL(process.env.PI_HARNESS_SDK),sdk=await import(sdkURL);
const mcp=await import(new URL('../../pi-mcp/dist/index.js',sdkURL));
const {McpOAuthCredentialStore}=await import(new URL('./extensions/mcp/oauth.js',sdkURL));
const {InMemoryAuthStorageBackend}=await import(new URL('./core/auth-storage.js',sdkURL));
const source=dirname(dirname(fileURLToPath(import.meta.url)));
const base=process.env.TMPDIR;
if(!base || !base.startsWith('/') || !base.includes('/Workspace/'))throw new Error('Set TMPDIR to a private Workspace test directory');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const bindings={
  exa_search:{server:'fixture',tool:'web_search_exa'},
  context7_resolve:{server:'fixture',tool:'resolve-library-id',parameters:{libraryName:'libraryName',query:'query'}},
  context7_docs:{server:'fixture',tool:'query-docs',parameters:{libraryId:'library-id',query:'query'}},
  wikipedia_search:{server:'fixture',tool:'search_wikipedia'},wikipedia_read:{server:'fixture',tool:'get_article'},
};
const tool=(name,args,id='call_1')=>[
  {delta:{role:'assistant',tool_calls:[{index:0,id,type:'function',function:{name,arguments:JSON.stringify(args)}}]}},
  {delta:{},finish_reason:'tool_calls'}];
const stop=[{delta:{role:'assistant',content:'Fixture complete'}},{delta:{},finish_reason:'stop'}];

async function fixture(options,run) {
  const root=await mkdtemp(join(base,'native-mcp-'));
  let session,http;
  const priorFetch=globalThis.fetch;
  if(options.http)globalThis.fetch=(input,init)=>{
    const url=new URL(typeof input==='string'||input instanceof URL?input:input.url);
    if(url.hostname==='offline-fixture.invalid')return options.http(input,init);
    assert.equal(url.hostname,'127.0.0.1');return priorFetch(input,init);
  };
  try {
    const workspace=join(root,'workspace'),agentDir=join(root,'agent'),home=join(root,'home');
    for(const p of [workspace,agentDir,home])await mkdir(p,{mode:0o700});
    // Apply the supplied integration contract to a PRIVATE SOURCE COPY only.
    // Production owner/index files remain untouched in this task.
    await cp(join(source,'extensions/tool-harness'),join(root,'extensions/tool-harness'),{recursive:true});
    execFileSync('git',['apply',join(source,'tests/fixtures/native-mcp-harness.patch')],{cwd:root,env:{PATH:'/usr/bin:/bin'}});
    const {harnessExtension}=await import(pathToFileURL(join(root,'extensions/tool-harness/index.mjs')));
    const log=join(root,'calls.jsonl');
    const config={sdk,mcp,privateHome:home,logPath:join(root,'mcp.log'),credentials:new McpOAuthCredentialStore(new InMemoryAuthStorageBackend()),
      timeoutMs:options.timeoutMs??1000,servers:{fixture:{command:process.execPath,args:[join(source,'tests/fixtures/mcp-provider.mjs'),log,options.mode??'normal'],cwd:workspace}},
      bindings,enabled:options.enabled??{exa:true,context7:true,wikipedia:true},readOnly:options.readOnly??false};
    if(options.http) {
      config.servers={fixture:{url:'https://offline-fixture.invalid/mcp',auth:{provider:'mock'}}};
    }
    const adapter=createNativeMcpProviders(config);
    const requests=[],confirmations=[],policy=[],events=[],errors=[];
    let step=0;
    http=createServer(async(req,res)=>{
      let body='';for await(const c of req)body+=c;
      requests.push(JSON.parse(body));
      res.writeHead(200,{'content-type':'text/event-stream'});
      const response=options.responses?.[step++]??stop;
      for(const choice of typeof response==='function'?response(requests.at(-1)):response)
        res.write('data: '+JSON.stringify({id:'fixture',object:'chat.completion.chunk',created:1,model:'mock',choices:[{index:0,...choice}]})+'\n\n');
      res.end('data: [DONE]\n\n');
    });
    await new Promise(r=>http.listen(0,'127.0.0.1',r));
    const rpc=async m=>{policy.push(m);return m.action==='auth_check'?{allowed:options.broker?options.broker(m,confirmations):true,reason:'fixture'}:{authorized:true};};
    const confirm=async request=>{confirmations.push(request);return options.approve?options.approve(request,confirmations):true;};
    await writeFile(join(workspace,'fixture.txt'),'synthetic read');
    const harness=harnessExtension(sdk,{rpc,providers:adapter.providers,confirm,
      initial:options.noHarness?undefined:{workspace,taskId:'mcp-fixture',appId:'fixture-app'},
      readOnly:options.readOnly??false,normalOnly:options.readOnly??false,readPaths:['fixture.txt'],binding:{workspace,taskId:'mcp-fixture',appId:'fixture-app'}});
    const probe=pi=>pi.registerTool({name:'probe',label:'probe',description:'fixture raw nested call',parameters:{type:'object',properties:{}},
      execute:async(_id,_args,signal,_update,ctx)=>{const o=await ctx.executeTool('mcp__fixture__web_search_exa',{query:'escape'},{signal});return {...o.result,isError:o.isError};}});
    const settings=sdk.SettingsManager.inMemory({retry:{enabled:false,provider:{maxRetries:0}},compaction:{enabled:false},cacheWarming:'off'});
    const loader=new sdk.DefaultResourceLoader({cwd:workspace,agentDir,settingsManager:settings,noExtensions:true,noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,
      extensionFactories:[...adapter.extensions,...(options.noHarness?[probe]:[harness])]});
    await loader.reload();assert.deepEqual(loader.getExtensions().errors,[]);
    const runtime=await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:null,modelsStorePath:join(agentDir,'models-store.json'),refreshOnCreate:false,allowModelNetwork:false});
    runtime.registerProvider('mock',{baseUrl:`http://127.0.0.1:${http.address().port}/v1`,apiKey:'fixture-only',api:'openai-completions',
      models:[{id:'fixture',name:'fixture',reasoning:false,input:['text'],contextWindow:32768,maxTokens:1024,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]});
    const manager=sdk.SessionManager.create(workspace,join(root,'sessions'));
    ({session}=await sdk.createAgentSession({cwd:workspace,agentDir,modelRuntime:runtime,model:runtime.getModel('mock','fixture'),resourceLoader:loader,settingsManager:settings,sessionManager:manager,thinkingLevel:'off'}));
    session.subscribe(e=>events.push(e));await session.bindExtensions({onError:e=>errors.push(e)});
    if(adapter.providers.names.length && !['init-stall','pagination'].includes(options.mode)) {
      const start=Date.now();
      while(true){try{adapter.providers.available(adapter.providers.names[0]);break;}catch{if(Date.now()-start>3000)throw new Error('native discovery did not finish');await wait(10);}}
    }
    if(!options.noHarness&&!options.readOnly&&!options.skipNetwork)await session.extensionRunner.getCommand('hn-tools').handler('network',session.extensionRunner.createCommandContext());
    const calls=async()=>{try{return (await readFile(log,'utf8')).trim().split('\n').map(l=>JSON.parse(l));}catch(e){if(e.code==='ENOENT')return [];throw e;}};
    await run({root,session,manager,adapter,requests,confirmations,policy,events,errors,calls});
    assert.deepEqual(errors,[]);
  } finally {
    if(session){await session.abort();await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();}
    if(http){http.closeAllConnections();await new Promise(r=>http.close(r));}
    // Independently verify no child in the native process group survived cleanup.
    const rows=await readFile(join(root,'calls.jsonl'),'utf8').catch(()=> '');
    for(const row of rows.trim().split('\n').filter(Boolean).map(l=>JSON.parse(l)))for(const pid of [row.pid,row.child].filter(Boolean)) {
      for(let i=0;i<100;i++){try{process.kill(pid,0);}catch{break;}await wait(10);}
      // Linux can briefly leave an orphan zombie awaiting its subreaper; that is
      // not a live process, but the direct stdio server must be reaped by Pi.
      const stat=await readFile(`/proc/${pid}/stat`,'utf8').catch(()=> '');
      assert.ok(!stat || row.child===pid&&stat.slice(stat.lastIndexOf(')')+2).startsWith('Z '),`native fixture process survived: ${pid}`);
    }
    globalThis.fetch=priorFetch;
    await rm(root,{recursive:true,force:true});
  }
}

test('bounded typed schemas and strict trusted-only configuration',()=>{
  for(const name of Object.keys(bindings)) {
    const args=Object.fromEntries((name==='context7_docs'?['libraryId','query']:name==='context7_resolve'?['libraryName','query']:name==='wikipedia_read'?['title']:['query']).map(k=>[k,k==='libraryId'?'/owner/project':'q']));
    validateMcpArguments(name,args);
    for(const bad of [null,[],{}, {...args,approved:true},Object.fromEntries(Object.keys(args).map(k=>[k,'x'.repeat(501)])),Object.fromEntries(Object.keys(args).map(k=>[k,'\n']))])assert.throws(()=>validateMcpArguments(name,bad));
  }
  for(const libraryId of ['https://evil.test','/x','/a/b/../../secret','/a b/c'])assert.throws(()=>validateMcpArguments('context7_docs',{libraryId,query:'q'}));
  const config={sdk,mcp,credentials:{},privateHome:'/private/home',logPath:'/private/log',servers:{fixture:{command:'/usr/bin/node',args:[],cwd:'/private/workspace'}},bindings};
  assert.deepEqual(createNativeMcpProviders(config).providers.names,[]);
  for(const change of [{enabled:{exa:'yes'}},{timeoutMs:15001},{servers:{fixture:{command:'npx',args:[],cwd:'/private'}}},{servers:{fixture:{url:'https://example.org/mcp?key=hidden'}}},{servers:{fixture:{url:'https://example.org/mcp',headers:{Authorization:'never accepted'}}}},{bindings:{exa_search:{server:'fixture',tool:'search.anything'}}}])assert.throws(()=>createNativeMcpProviders({...config,...change}));
});

test('result/error shapes bounded before native conversion; no binary, metadata or error-body spill',()=>{
  for(const value of [null,{}, {isError:'false',content:[]},{isError:true,content:[{type:'text',text:'SECRET'}]}, {content:[{type:'image',data:'SECRET'}]}, {content:[{type:'resource_link',uri:'file:///secret'}]}, {content:[{type:'text',text:42}]}]) {
    const r=boundedMcpResult(value);assert.equal(r.isError,true);assert.doesNotMatch(JSON.stringify(r),/SECRET/);
  }
  for(const text of ['北'.repeat(20000),'\\"\n'.repeat(20000)]) {
    const r=boundedMcpResult({content:[{type:'text',text}],_meta:{secret:'SECRET'}});
    assert.ok(Buffer.byteLength(r.content[0].text)<=MCP_MAX_TEXT);assert.equal(JSON.parse(r.content[0].text).truncated,true);
  }
});

test('actual Pi registration + native discovery + all five MCP invocations + native journal continuation', {timeout:15000},()=>fixture({responses:[
  tool('exa_search',{query:'public docs'},'exa'),tool('context7_resolve',{libraryName:'react',query:'hooks'},'c7resolve'),
  tool('context7_docs',{libraryId:'/facebook/react',query:'hooks'},'c7docs'),tool('wikipedia_search',{query:'London Ontario'},'wikiSearch'),
  tool('wikipedia_read',{title:'London, Ontario'},'wikiRead'),stop,
]},async f=>{
  await f.session.prompt('Fixture retrieval only');
  const calls=await f.calls();assert.ok(calls.some(c=>c.method==='initialize'));assert.ok(calls.some(c=>c.method==='tools/list'));
  assert.deepEqual(calls.filter(c=>c.method==='tools/call').map(c=>c.params.name),Object.values(bindings).map(b=>b.tool));
  assert.deepEqual(calls.filter(c=>c.method==='tools/call')[2].params.arguments,{'library-id':'/facebook/react',query:'hooks'});
  assert.equal(calls[0].ambient,false);assert.equal(calls[0].home,join(f.root,'home'));
  assert.equal((await readFile(join(f.root,'mcp.log'),'utf8').catch(()=>'')),'');
  assert.equal(f.confirmations.length,7); // activation, network scope, five exact queries
  for(const q of f.confirmations.slice(2))assert.match(q.detail,/native MCP: fixture\//);
  assert.deepEqual(f.policy.filter(p=>p.action==='auth_check').map(p=>p.op),Array.from({length:5},()=>['network','submit_external','network','submit_external']).flat());
  for(const req of f.requests.slice(1))assert.match(JSON.stringify(req.messages),/untrusted/);
  assert.doesNotMatch(JSON.stringify(f.requests),/UNTRUSTED DESCRIPTION|UNTRUSTED INSTRUCTION|SECRET_META|SECRET_SERVER_LOG|NOT_REPEATED/);
  const reopened=sdk.SessionManager.open(f.manager.getSessionFile());
  const results=reopened.getEntries().filter(e=>e.type==='message'&&e.message.role==='toolResult');
  assert.equal(results.length,5);assert.ok(results.every(e=>e.message.nestedCalls?.calls?.length===1),JSON.stringify(results.map(e=>e.message.nestedCalls)));
  assert.equal(reopened.getEntries().filter(e=>e.customType==='hyprneuro.tool-call/1'&&e.data.status==='completed').length,5);
  const names=f.session.getActiveToolNames();assert.ok(!names.some(n=>n.startsWith('mcp__')));assert.ok(!names.includes('tool_search'));
}));

test('fresh denial and broker revocation prevent native dispatch', {timeout:15000},async()=>{
  for(const deny of ['human','network','submit_external','post-consent'])await fixture({responses:[tool('exa_search',{query:'denied'}),stop],
    approve:(r)=>deny!=='human'||!r.title.startsWith('Allow '),
    broker:(m,confirmations)=>!(m.op===deny || deny==='post-consent'&&confirmations.some(c=>c.title==='Allow exa_search?')),
  },async f=>{
    await f.session.prompt('denial fixture');assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,0);
    assert.ok(f.events.some(e=>e.type==='tool_execution_end'&&e.isError));
  });
});

test('native namespace direct/nested calls cannot bypass facade; disabled and read-only stay off', {timeout:15000},async()=>{
  for(const name of ['mcp__fixture__web_search_exa','probe'])await fixture({noHarness:true,responses:[tool(name,name==='probe'?{}:{query:'escape'}),stop]},async f=>{
    f.session.setActiveToolsByName([name]);await f.session.prompt('raw bypass fixture');
    assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,0);
    assert.ok(f.events.some(e=>e.type==='tool_execution_end'&&e.isError));
  });
  for(const options of [{enabled:{}},{readOnly:true}])await fixture({...options,responses:[tool('exa_search',{query:'escape'}),stop]},async f=>{
    assert.deepEqual(f.adapter.providers.names,[]);await f.session.prompt('disabled fixture');assert.equal((await f.calls()).length,0);
  });
});

test('native result errors, protocol failure, content boundaries and unknown outcomes are never replayed', {timeout:20000},async()=>{
  for(const query of ['error','protocol-error','binary','malformed','large','exit','structured','long'])await fixture({responses:[tool('exa_search',{query},'same'),tool('exa_search',{query},'again'),stop]},async f=>{
    await f.session.prompt('result boundary fixture');
    assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,1,query);
    assert.doesNotMatch(JSON.stringify(f.requests),/SECRET_ERROR_BODY|SECRET_META|SECRET_SERVER_LOG/);
    const status=f.manager.getEntries().filter(e=>e.customType==='hyprneuro.tool-call/1').at(-1).data.status;
    assert.equal(status,['structured','long'].includes(query)?'completed':'unknown',query);
    assert.ok(!JSON.stringify(f.requests).includes('Full output saved'));
    for(const e of f.events.filter(e=>e.type==='tool_execution_end'&&e.parentToolCallId)) {
      assert.ok(Buffer.byteLength(JSON.stringify(e.result))<40000);
      if(!e.isError)assert.ok(Buffer.byteLength(e.result.content[0].text)<=MCP_MAX_TEXT);
    }
  });
});

test('absolute timeout/cancel/initialize-stall and process-group cleanup are bounded', {timeout:15000},async()=>{
  for(const mode of ['normal','child','init-stall'])await fixture({mode,timeoutMs:150,responses:[tool('exa_search',{query:'stall'}),stop]},async f=>{
    const start=Date.now();await f.session.prompt('timeout fixture');assert.ok(Date.now()-start<2500);
    const calls=await f.calls();assert.ok(calls.filter(c=>c.method==='tools/call').length<=1);
  });
  await fixture({timeoutMs:2000,responses:[tool('exa_search',{query:'stall'}),stop]},async f=>{
    const run=f.session.prompt('cancel fixture');
    for(let i=0;i<100 && !(await f.calls()).some(c=>c.method==='tools/call');i++)await wait(10);
    const start=Date.now();await f.session.abort();await run;assert.ok(Date.now()-start<1000);
    assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,1);
    assert.ok(f.manager.getEntries().some(e=>e.customType==='hyprneuro.tool-call/1'&&e.data.status==='unknown'));
  });
});


test('model approval/server/URL fields and schema bounds cannot authorize native requests', {timeout:15000},async()=>{
  for(const args of [{query:'q',approved:true},{query:'q',server:'evil'},{query:'q',url:'https://evil.invalid'},{query:'x'.repeat(501)},{query:'\n'},{}])await fixture({responses:[tool('exa_search',args),stop]},async f=>{
    await f.session.prompt('argument boundary fixture');assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,0);
    assert.equal(f.confirmations.length,2);assert.ok(f.events.some(e=>e.type==='tool_execution_end'&&e.isError));
  });
});

test('native discovery pagination fails closed instead of unbounded page loops', {timeout:10000},()=>fixture({mode:'pagination',responses:[tool('exa_search',{query:'q'}),stop]},async f=>{
  await wait(100);assert.throws(()=>f.adapter.providers.available('exa_search'),/unavailable/);
  await f.session.prompt('discovery failure fixture');assert.equal((await f.calls()).filter(c=>c.method==='tools/list').length,1);
  assert.equal((await f.calls()).filter(c=>c.method==='tools/call').length,0);
}));

test('native StreamableHTTP reuses opaque Pi provider auth; offline fetch only, no external network or retry', {timeout:15000},async()=>{
  for(const status of [200,401,404,429,500]) {
    const methods=[];let authenticated=false;
    const fetch=async(_url,opts)=>{
      assert.equal(opts.redirect,'error');
      if(opts.method==='DELETE')return new Response(null,{status:204});
      const request=JSON.parse(opts.body);methods.push(request.method);
      authenticated=opts.headers.get('Authorization')==='Bearer fixture-only';
      let result;
      if(request.method==='initialize')result={protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'offline',version:'1'}};
      else if(request.method==='notifications/initialized'||request.method==='notifications/cancelled')return new Response(null,{status:202});
      else if(request.method==='tools/list')result={tools:[{name:'web_search_exa',inputSchema:{type:'object'}}]};
      else if(request.method==='tools/call') {
        if(status!==200)return new Response('SECRET_HTTP_BODY',{status});
        result={content:[{type:'text',text:'offline native HTTP docs'}]};
      }
      return new Response(JSON.stringify({jsonrpc:'2.0',id:request.id,result}),{headers:{'content-type':'application/json','mcp-session-id':'fixture-session'}});
    };
    await fixture({http:fetch,responses:[tool('exa_search',{query:'docs'}),stop]},async f=>{
      await f.session.prompt('offline HTTP fixture');
      assert.equal(authenticated,true);assert.equal(methods.filter(m=>m==='tools/call').length,1);
      assert.doesNotMatch(JSON.stringify(f.requests),/SECRET_HTTP_BODY|fixture-only/);
      const outcomes=f.manager.getEntries().filter(e=>e.customType==='hyprneuro.tool-call/1');
      assert.equal(outcomes.at(-1).data.status,status===200?'completed':'unknown');
    });
  }
});
