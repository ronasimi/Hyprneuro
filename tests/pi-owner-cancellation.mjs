// Actual installed SDK, dedicated parent-only roots and loopback mock HTTP only.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import {connect} from 'node:net';
import {createInterface} from 'node:readline';
import {createHost} from '../extensions/pi-owner/host.mjs';
import {signature} from '../extensions/pi-owner/socket.mjs';

const sdkPath=process.env.PI_HARNESS_SDK,durableDir=process.env.PI_HARNESS_DURABLE;
if(!sdkPath||!durableDir)throw new Error('Explicit installed SDK/Durable required, no installation');
const chunk=delta=>'data: '+JSON.stringify({choices:[{index:0,delta,finish_reason:null}]})+'\n\n';
async function client(root,role='chat') {
  const socket=connect(join(root,'owner.sock'));
  const nonce=await new Promise((r,j)=>{socket.once('data',r);socket.once('error',j);});
  socket.write(Buffer.concat([Buffer.from(role==='control'?'C':'T'),signature(await readFile(join(root,role+'.key')),nonce,role)]));
  const lines=createInterface({input:socket}),iterator=lines[Symbol.asyncIterator]();
  assert.equal(JSON.parse((await iterator.next()).value).type,'ready');
  return {send:value=>socket.write(JSON.stringify(value)+'\n'),next:async()=>JSON.parse((await iterator.next()).value),
    close(){lines.close();socket.destroy();}};
}
const until=async predicate=>{
  const deadline=Date.now()+3000;
  while(!predicate()){assert.ok(Date.now()<deadline,'Fixture state not reached');await new Promise(r=>setTimeout(r,5));}
};
const terminal=async(chat,count=2)=>{
  const packets=[];
  while(packets.length<count){const p=await chat.next();if(['result','error'].includes(p.type))packets.push(p);}
  return packets;
};
const cancel=(chat,admission,chat_id='first',id='cancel')=>chat.send({op:'cancel',id,chat_id,generation:admission.event.generation});
const finish=text=>'data: '+JSON.stringify({choices:[{index:0,delta:{content:text},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n';
async function fixture(run,respond,rpc) {
  const root=await mkdtemp(join(tmpdir(),'hn-cancel-')),env={...process.env},cwd=process.cwd();
  let host,chat,control,requests=0,passed=false;const approvals=[],sockets=new Set();
  const server=createServer(async(req,res)=>{
    for await(const _ of req){}requests++;
    respond(req,res,requests);
  });
  server.on('connection',socket=>{sockets.add(socket);socket.once('close',()=>sockets.delete(socket));});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  try {
    process.env.HYPRNEURO_PI_OWNER_ENABLE='1';delete process.env.HYPRNEURO_RESIDENCY_DIR;
    const ownerRoot=join(root,'owner'),workspace=join(ownerRoot,'home','workspace');
    await mkdir(workspace,{recursive:true,mode:0o700});await writeFile(join(workspace,'fixture.txt'),'PRIVATE_MOCK_FIXTURE');
    host=await createHost({sdkPath,durableDir,piBin:'/home/ron/.pi/agent/bin/pi',root:ownerRoot,workspace,taskId:'cancel',appId:'mock',
      profile:'read-only',normalOnly:true,parentOnly:true,persistent:true,readPaths:['fixture.txt'],
      textBaseUrl:`http://127.0.0.1:${server.address().port}/v1`,
      rpc:async packet=>rpc?rpc(packet):packet.action==='auth_check'?{allowed:true}:{authorized:true}});
    control=await client(ownerRoot,'control');chat=await client(ownerRoot);
    // Fixture-only genuine harness confirmation callback, never a production UI.
    host.owner.listeners.add(event=>{if(event.type==='consent'){approvals.push(event.title);host.owner.consent(event.id,true);}});
    await run({host,chat,control,ownerRoot,requests:()=>requests,approvals});passed=true;
  } catch(error) {
    await writeFile(join(root,'failure.json'),JSON.stringify({error:error.stack,requests,approvals,entries:host?.session.sessionManager.getEntries()},null,2));throw error;
  } finally {
    await host?.close();chat?.close();control?.close();
    for(const socket of sockets)socket.destroy();await new Promise(r=>server.close(r));
    process.chdir(cwd);for(const key of Object.keys(process.env))if(!(key in env))delete process.env[key];Object.assign(process.env,env);
    if(passed)await rm(root,{recursive:true,force:true});else console.error('Cancellation fixture retained:',root);
  }
}

test('actual SDK explicit same-generation cancel after text drains owned body; persisted cancelled-known, not success', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'Synthetic tool-free cancellation test'});
  const admission=await f.chat.next();assert.equal(admission.event.type,'chat_admission');
  let event;
  do{event=await f.chat.next();}while(event.event?.type!=='delta');
  assert.equal(event.event.text,'partial mock text');
  f.chat.send({op:'cancel',id:'cancel',chat_id:'first',generation:admission.event.generation});
  const results=[];
  while(results.length<2){const packet=await f.chat.next();if(packet.type==='error')assert.fail(JSON.stringify(packet));if(packet.type==='result')results.push(packet);}
  for(const packet of results)assert.deepEqual(packet.result,{settled:false,cancelled:true,outcome:'cancelled-known'});
  assert.equal(f.host.owner.phase,'ordinary');assert.equal(f.requests(),1);assert.deepEqual(f.approvals,['Enable READ-ONLY Hyprneuro tools?']);
  const cp=JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8'));
  assert.equal(cp.phase,'ordinary');assert.equal(cp.outcome.kind,'cancelled-known');
  const terminal=f.host.session.sessionManager.getEntries().findLast(e=>e.message?.role==='assistant').message;
  assert.equal(terminal.stopReason,'aborted');assert.equal(terminal.content[0].text,'partial mock text');
  assert.ok(!f.host.session.sessionManager.getEntries().some(e=>e.customType==='hyprneuro.tool-call/1'));
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({content:'partial mock text'}));}));

test('before first token requires positive owned body closure, not just abort signal', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools, before tokens'});const admission=await f.chat.next();
  await until(()=>f.host.owner.currentChat?.requests.some(r=>r.reader));
  const scope=f.host.owner.currentChat;
  const abort=f.host.session.abort.bind(f.host.session);
  f.host.session.abort=async()=>{assert.equal(scope.closed,true,'fence precedes SDK abort');return abort();};
  cancel(f.chat,admission);
  const results=await terminal(f.chat);assert.ok(results.every(p=>p.result?.outcome==='cancelled-known'));
  assert.ok(await scope.drained());assert.equal(f.host.owner.phase,'ordinary');assert.equal(f.requests(),1);
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.flushHeaders();}));

test('stalled headers cannot prove response-body closure and retain unknown without retry', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools, stalled headers'});const admission=await f.chat.next();
  await until(()=>f.requests()===1);cancel(f.chat,admission);
  assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
  assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);
  assert.equal(JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8')).phase,'chat-unknown');
},()=>{}));

test('partial native tool call before cancel is not tool-free, even without dispatch', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'Synthetic partial toolcall test'});const admission=await f.chat.next();
  await until(()=>f.host.owner.currentChat?.uncertain);
  cancel(f.chat,admission);assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
  assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);
  assert.deepEqual(f.approvals,['Enable READ-ONLY Hyprneuro tools?']);
  assert.ok(!f.host.session.sessionManager.getEntries().some(e=>e.customType==='hyprneuro.tool-call/1'));
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({tool_calls:[{index:0,id:'late-read',type:'function',function:{name:'read',arguments:'{"path":'}}]}));}));

test('granted tool pending broker acknowledgement is fenced before late actual execution and stays unknown', {timeout:15000},async()=>{
  let checks=0,release;
  const barrier=new Promise(resolve=>{release=resolve;});
  await fixture(async f=>{
    f.chat.send({op:'chat',id:'first',text:'Synthetic pending approved mock read'});const admission=await f.chat.next();
    await until(()=>checks===2);assert.deepEqual(f.approvals,['Enable READ-ONLY Hyprneuro tools?','Allow read?']);
    cancel(f.chat,admission);await until(()=>f.host.owner.currentChat?.closed);release();
    assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
    const entries=f.host.session.sessionManager.getEntries();
    assert.ok(!entries.some(e=>e.customType==='hyprneuro.tool-call/1'&&e.data.status==='completed'));
    assert.ok(!JSON.stringify(entries).includes('PRIVATE_MOCK_FIXTURE'),'No actual read after pending broker drain');
    assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);
  },(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.end('data: '+JSON.stringify({choices:[{index:0,delta:{tool_calls:[{index:0,id:'approved-read',type:'function',function:{name:'read',arguments:'{"path":"fixture.txt"}'}}]},finish_reason:'tool_calls'}]})+'\n\ndata: [DONE]\n\n');},async packet=>{
    if(packet.action==='auth_check'&&++checks===2)await barrier;
    return packet.action==='auth_check'?{allowed:true}:{authorized:true};
  });
});

test('repeat correlated cancel drains once; stale/cross-connection generations cannot cancel later chat or replay', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools first'});const admission=await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  // Wrong generation and different authenticated connection carry no authority.
  f.chat.send({op:'cancel',id:'wrong',chat_id:'first',generation:'00000000-0000-0000-0000-000000000000'});
  assert.equal((await f.chat.next()).type,'error');
  const other=await client(f.ownerRoot);
  try{cancel(other,admission);assert.equal((await other.next()).type,'error');}finally{other.close();}
  cancel(f.chat,admission,'first','cancel-one');cancel(f.chat,admission,'first','cancel-two');
  assert.ok((await terminal(f.chat,3)).every(p=>p.result?.outcome==='cancelled-known'));
  const session=f.host.session.sessionManager.getSessionId();
  const next=await client(f.ownerRoot);
  try {
    next.send({op:'cancel',id:'stale',chat_id:'first',generation:admission.event.generation});assert.equal((await next.next()).type,'error');
    next.send({op:'chat',id:'second',text:'No tools, explicit new prompt after known cancel'});
    assert.equal((await next.next()).event.type,'chat_admission');
    const [result]=await terminal(next,1);assert.deepEqual(result.result,{settled:true});
  }finally{next.close();}
  assert.equal(f.host.owner.phase,'ordinary');assert.equal(f.requests(),2);assert.equal(f.host.session.sessionManager.getSessionId(),session);
  assert.equal(f.host.session.sessionManager.getEntries().filter(e=>e.message?.role==='user').length,2);
  assert.deepEqual(f.approvals,['Enable READ-ONLY Hyprneuro tools?']);
},(_req,res,n)=>{res.writeHead(200,{'content-type':'text/event-stream'});if(n===1)res.write(chunk({content:'first partial'}));else res.end(finish('explicit next reply'));}));

test('ordinary socket drop after text is UNKNOWN, never explicit cancellation', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools disconnect'});await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  f.chat.close();await f.host.owner.queue;assert.equal(f.host.owner.phase,'failed');
  assert.equal(JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8')).phase,'chat-unknown');assert.equal(f.requests(),1);
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({content:'partial before disconnect'}));}));

test('retryable HTTP failure remains UNKNOWN with exactly one request, no automatic SDK backoff/replay', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools HTTP error'});await f.chat.next();
  const [result]=await terminal(f.chat,1);assert.equal(result.type,'error');assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);
  assert.equal(JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8')).phase,'chat-unknown');
},(_req,res)=>{res.writeHead(503,{'content-type':'application/json'});res.end(JSON.stringify({error:{message:'private fixture failure'}}));}));

test('cancel after native finish rejects stale generation without changing successful reply', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools, naturally finish'});const admission=await f.chat.next();
  assert.deepEqual((await terminal(f.chat,1))[0].result,{settled:true});
  cancel(f.chat,admission);assert.equal((await f.chat.next()).type,'error');
  assert.equal(f.host.owner.phase,'ordinary');assert.equal(f.requests(),1);
  assert.equal(f.host.session.sessionManager.getEntries().findLast(e=>e.message?.role==='assistant').message.stopReason,'stop');
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.end(finish('finished, not cancelled'));}));

test('a separate explicitly queued prompt starts its own generation after known cancel, not replay', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools first queued case'});const admission=await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  const other=await client(f.ownerRoot);
  try {
    other.send({op:'chat',id:'second',text:'No tools explicit second queued request'});
    const nextAdmission=await other.next();assert.notEqual(nextAdmission.event.generation,admission.event.generation);
    f.chat.send({op:'chat',id:'duplicate',text:'Must not submit concurrent same-socket prompt'});
    assert.equal((await f.chat.next()).type,'error');
    cancel(f.chat,admission);assert.ok((await terminal(f.chat)).every(p=>p.result?.outcome==='cancelled-known'));
    assert.deepEqual((await terminal(other,1))[0].result,{settled:true});
    assert.equal(f.requests(),2);assert.equal(f.host.owner.phase,'ordinary');
    assert.deepEqual(f.host.session.sessionManager.getEntries().filter(e=>e.message?.role==='user').map(e=>e.message.content[0].text),
      ['No tools first queued case','No tools explicit second queued request']);
  }finally{other.close();}
},(_req,res,n)=>{res.writeHead(200,{'content-type':'text/event-stream'});if(n===1)res.write(chunk({content:'partial'}));else res.end(finish('queued explicit request completed'));}));

test('concurrent supported fixture close cannot classify known cancellation or remove failed guard', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools close race'});const admission=await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  let release;const barrier=new Promise(resolve=>{release=resolve;});
  const original=f.host.session.abort.bind(f.host.session);
  f.host.session.abort=async()=>{await original();await barrier;};
  cancel(f.chat,admission);await until(()=>f.host.owner.currentChat?.closed);
  const closing=f.host.close();assert.equal(f.host.owner.closing,true);release();await closing;
  assert.equal(f.host.owner.phase,'failed');assert.ok(await readFile(join(f.ownerRoot,'owner.guard')));
  assert.ok(!f.host.session.sessionManager.getEntries().some(e=>e.data?.outcome?.kind==='cancelled-known'));
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({content:'partial before close race'}));}));

test('unacknowledged owned reader cancellation stays UNKNOWN despite native abort/idle', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools stalled body cleanup'});const admission=await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  const scope=f.host.owner.currentChat,reader=scope.requests[0].reader,original=reader.cancel.bind(reader);
  let release;const barrier=new Promise(resolve=>{release=resolve;});reader.cancel=async()=>{await barrier;return original();};
  try {
    cancel(f.chat,admission);assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
    assert.equal(f.host.session.isIdle,true);assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);
    assert.equal(JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8')).phase,'chat-unknown');
  }finally{release();await scope.requests[0].cancellation.catch(()=>{});}
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({content:'partial before unacknowledged cleanup'}));}));

test('attempted late native fetch after fence is rejected before transport and invalidates tool-free proof', {timeout:15000},()=>fixture(async f=>{
  f.chat.send({op:'chat',id:'first',text:'No tools late fetch race'});const admission=await f.chat.next();
  let event;do{event=await f.chat.next();}while(event.event?.type!=='delta');
  const original=f.host.session.abort.bind(f.host.session),scope=f.host.owner.currentChat;
  f.host.session.abort=async()=>{
    assert.equal(scope.closed,true);
    await assert.rejects(scope.fetch(`http://127.0.0.1:1/NEVER_FETCH`),/admission sealed/);
    return original();
  };
  cancel(f.chat,admission);assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
  assert.equal(f.host.owner.phase,'failed');assert.equal(f.requests(),1);assert.equal(scope.requests.length,1);
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write(chunk({content:'partial before late request attempt'}));}));

test('cancel while chat-intent checkpoint awaits admits ZERO native prompts or HTTP requests and releases scope', {timeout:15000},()=>fixture(async f=>{
  let entered,release,aborts=0,prompts=0;
  const checkpointEntered=new Promise(resolve=>{entered=resolve;});
  const barrier=new Promise(resolve=>{release=resolve;});
  const checkpoint=f.host.owner.checkpoint;
  f.host.owner.checkpoint=async(...args)=>{await checkpoint(...args);if(args[0]==='chat-intent'){entered();await barrier;}};
  const prompt=f.host.session.prompt.bind(f.host.session),abort=f.host.session.abort.bind(f.host.session);
  f.host.session.prompt=(...args)=>{prompts++;return prompt(...args);};
  f.host.session.abort=async()=>{aborts++;return abort();};
  const scopes=[],factory=f.host.owner.cancellation;
  f.host.owner.cancellation=()=>{const scope=factory();scopes.push(scope);return scope;};
  f.chat.send({op:'chat',id:'first',text:'Synthetic cancelled during checkpoint, never dispatch'});
  const admission=await f.chat.next();await checkpointEntered;
  cancel(f.chat,admission);await until(()=>aborts===1);
  assert.equal(f.host.owner.currentChat,undefined);assert.equal(prompts,0);assert.equal(f.requests(),0);
  release();assert.ok((await terminal(f.chat)).every(p=>p.type==='error'));
  assert.equal(prompts,0,'No native prompt admitted after checkpoint cancellation');assert.equal(f.requests(),0);
  assert.equal(f.host.owner.phase,'failed');assert.equal(f.host.owner.currentChat,undefined);
  assert.equal(scopes.length,1);assert.equal(scopes[0].closed,true);assert.equal(scopes[0].streams.length,0);
  assert.equal(f.host.session.isIdle,true);
  assert.equal(JSON.parse(await readFile(join(f.ownerRoot,'checkpoint.json'),'utf8')).phase,'chat-unknown');
  f.chat.send({op:'chat',id:'again',text:'Do not replay cancelled admission'});await f.chat.next();
  assert.equal((await terminal(f.chat,1))[0].type,'error');assert.equal(prompts,0);assert.equal(f.requests(),0);
  await f.host.close();assert.ok(await readFile(join(f.ownerRoot,'owner.guard')));
},(_req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.end(finish('MUST NOT BE REQUESTED'));}));
