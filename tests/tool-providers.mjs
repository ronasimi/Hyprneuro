import test from 'node:test';
import assert from 'node:assert/strict';
import { Providers, publicAddress, requestProvider } from '../extensions/tool-harness/providers.mjs';

test('provider configuration/credentials are explicit, disabled/missing fail without requests', async () => {
  let calls=0;
  for (const config of [{},{exa:true},{context7:true}]) {
    const p=new Providers({config,env:{EXA_API_KEY:'not-consented'},request:async()=>{calls++;}});
    assert.throws(()=>p.available('exa_search'),/disabled|Credential unavailable/);
    assert.throws(()=>p.available('context7_docs'),/disabled|Credential unavailable/);
  }
  assert.equal(calls,0);
  assert.throws(()=>new Providers({config:{exa:{apiKey:'never-accepted'}}}),/booleans/);
  const p=new Providers({config:{exa:true},env:{HYPRNEURO_EXA_API_KEY:''}});
  await assert.rejects(()=>p.execute('exa_search',{query:'hello'}),/empty\/invalid/);
});

test('documented Exa, Context7 resolution/context, Wikipedia search/extract schemas; bounded untrusted results', async () => {
  const calls=[];
  const responses=[{results:[{title:'test',url:'https://example.org',text:'x'.repeat(3000)}]},
    {results:[{id:'/facebook/react',title:'React',description:'UI'}]},
    {codeSnippets:[{codeTitle:'Hooks',codeId:'https://example.org',codeList:[{language:'js',code:'useState(1)'}]}],infoSnippets:[{content:'info',pageId:'https://example.org'}],version:{requested:'v1',served:'v2',status:'unverified'}},
    {query:{search:[{title:'London, Ontario',snippet:'Canadian <b>city</b>'}]}},
    {query:{pages:[{title:'London, Ontario',extract:'London is a city in Ontario.'}]}}];
  const p=new Providers({config:{exa:true,context7:true,wikipedia:true},env:{HYPRNEURO_EXA_API_KEY:'test-exa',HYPRNEURO_CONTEXT7_API_KEY:'test-c7'},
    request:async(url,options)=>{calls.push({url:new URL(url),...options});return responses.shift();}});
  const results=[];
  for (const [name,args] of [['exa_search',{query:'public docs'}],['context7_resolve',{libraryName:'react',query:'hooks'}],
      ['context7_docs',{libraryId:'/facebook/react',query:'hooks'}],['wikipedia_search',{query:'London Ontario'}],['wikipedia_read',{title:'London, Ontario'}]]) {
    const r=await p.execute(name,args);results.push(JSON.parse(r.content[0].text));
    assert.equal(r.details.untrusted,true);assert.ok(r.content[0].text.length<=12000);
    assert.doesNotMatch(r.content[0].text,/test-exa|test-c7/);
  }
  assert.equal(calls[0].url.href,'https://api.exa.ai/search');
  assert.deepEqual(calls[0].body,{query:'public docs',type:'auto',numResults:5,contents:{text:{maxCharacters:2000}}});
  assert.equal(calls[1].url.pathname,'/api/v2/libs/search');
  assert.equal(calls[1].url.searchParams.get('libraryName'),'react');
  assert.equal(calls[2].url.pathname,'/api/v2/context');
  assert.equal(calls[2].url.searchParams.get('type'),'json');
  assert.equal(calls[2].url.searchParams.get('libraryId'),'/facebook/react');
  assert.equal(results[2].version.status,'unverified');
  assert.equal(calls[3].url.searchParams.get('list'),'search');
  assert.equal(calls[4].url.searchParams.get('prop'),'extracts');
  assert.equal(results[3].results[0].snippet,'Canadian city');
});

test('no guessed URL, redirects, private addresses, management endpoint, error body or credential leaks', async () => {
  for(const address of ['127.0.0.1','10.0.0.2','169.254.169.254','::1','::ffff:127.0.0.1','fc00::1','2001:db8::1']) assert.equal(publicAddress(address),false,address);
  assert.equal(publicAddress('1.1.1.1'),true);
  await assert.rejects(()=>requestProvider('http://127.0.0.1/'),/destination denied/);
  await assert.rejects(()=>requestProvider('https://context7.com/api/v2/teamspaces'),/destination denied/);
  const p=new Providers({config:{context7:true},env:{HYPRNEURO_CONTEXT7_API_KEY:'secret'},request:async()=>{throw new Error('secret body');}});
  await assert.rejects(()=>p.execute('context7_resolve',{libraryName:'react',query:'hooks'}),e=>!e.message.includes('secret'));
  await assert.rejects(()=>p.execute('context7_docs',{libraryId:'https://evil.test',query:'hooks'}),/Invalid Context7/);
  for(const response of [{error:'secret'},{results:'invalid'},null]) {
    p.request=async()=>response;
    await assert.rejects(()=>p.execute('context7_resolve',{libraryName:'react',query:'hooks'}));
  }
});
