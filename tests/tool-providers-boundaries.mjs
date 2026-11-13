// Additional offline regressions for the existing REST providers. These do NOT
// relabel REST as MCP; native MCP is tested independently in native-mcp.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,writeFile,chmod,symlink,rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { Providers,requestProvider } from '../extensions/tool-harness/providers.mjs';
const args={exa_search:{query:'docs'},context7_resolve:{libraryName:'react',query:'hooks'},context7_docs:{libraryId:'/facebook/react',query:'hooks'},wikipedia_search:{query:'London Ontario'},wikipedia_read:{title:'London, Ontario'}};
const config={exa:true,context7:true,wikipedia:true};
const env={HYPRNEURO_EXA_API_KEY:'synthetic-exa',HYPRNEURO_CONTEXT7_API_KEY:'synthetic-c7'};

test('REST metadata file absent/private/unknown/oversized/symlink cases do not enable ambient access',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-provider-bound-'));
  try {
    const path=join(root,'tools.json');const p=await Providers.load(path);
    for(const name of Object.keys(args))assert.throws(()=>p.available(name),/disabled/);
    for(const value of ['{"exa":"true"}','{"other":true}','{',' '.repeat(4097)]) {
      await writeFile(path,value,{mode:0o600});await assert.rejects(()=>Providers.load(path));
    }
    await writeFile(path,JSON.stringify(config));await chmod(path,0o644);await assert.rejects(()=>Providers.load(path));
    await chmod(path,0o600);assert.deepEqual((await Providers.load(path)).config,config);
    const alias=join(root,'alias');await symlink(path,alias);await assert.rejects(()=>Providers.load(alias));
  } finally {await rm(root,{recursive:true,force:true});}
});

test('all REST tool arguments are bounded, exact and reject approval/endpoint injection before request',async()=>{
  let calls=0;const p=new Providers({config,env,request:async()=>{calls++;}});
  for(const [name,valid] of Object.entries(args)) {
    assert.equal(p.tools.find(t=>t.name===name).parameters.additionalProperties,false);
    for(const invalid of [null,[],{}, {...valid,approved:true},{...valid,url:'https://evil.invalid'},Object.fromEntries(Object.keys(valid).map(k=>[k,123])),Object.fromEntries(Object.keys(valid).map(k=>[k,'x'.repeat(501)])),Object.fromEntries(Object.keys(valid).map(k=>[k,'\u0000']))])await assert.rejects(()=>p.execute(name,invalid));
  }
  assert.equal(calls,0);
  for(const key of ['', 'bad\r\nheader']) {
    const p=new Providers({config,env:{HYPRNEURO_EXA_API_KEY:key},request:async()=>{calls++;}});
    await assert.rejects(()=>p.execute('exa_search',args.exa_search));
  }
  assert.equal(calls,0);
});

test('each REST provider has independent malformed/error handling and bounded untrusted response',async()=>{
  for(const name of Object.keys(args)) {
    for(const response of [null,42,'text',[],{error:{message:'PRIVATE_ERROR'}},{}]) {
      const p=new Providers({config,env,request:async()=>response});
      await assert.rejects(()=>p.execute(name,args[name]),e=>!e.message.includes('PRIVATE_ERROR'));
    }
    const p=new Providers({config,env,request:async()=>{throw new Error('PRIVATE_ERROR synthetic-exa');}});
    await assert.rejects(()=>p.execute(name,args[name]),e=>!e.message.includes('PRIVATE_ERROR')&&!e.message.includes('synthetic-exa'));
  }
  const many=Array.from({length:50},()=>({title:'t'.repeat(1000),url:'https://example.org',text:'x'.repeat(10000)}));
  const p=new Providers({config,env,request:async()=>({results:many})});
  const r=await p.execute('exa_search',args.exa_search);assert.ok(r.content[0].text.length<=12000);assert.equal(r.details.untrusted,true);
  const wiki=new Providers({config,env,request:async()=>({query:{pages:[{title:'Missing',missing:true}]}})});
  assert.deepEqual(JSON.parse((await wiki.execute('wikipedia_read',args.wikipedia_read)).content[0].text).pages,[{title:'Missing',missing:true,extract:''}]);
});

test('REST destination failures are offline and never follow model-chosen URLs or management endpoints',async()=>{
  for(const url of ['https://user:pass@api.exa.ai/search','https://api.exa.ai:444/search','https://exa.ai/search','https://context7.com/api/v2/teamspaces','file:///etc/passwd']) {
    await assert.rejects(()=>requestProvider(url),/destination denied/);
  }
});
