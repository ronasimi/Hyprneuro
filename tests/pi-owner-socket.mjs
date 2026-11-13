import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,stat,chmod} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {connect} from 'node:net';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {serveOwner,signature,MAX_FRAME} from '../extensions/pi-owner/socket.mjs';
import {PiOwner} from '../extensions/pi-owner/owner.mjs';

async function client(root,role='chat',bad=false) {
  const socket=connect(join(root,'owner.sock'));
  const nonce=await new Promise((resolve,reject)=>{socket.once('data',resolve);socket.once('error',reject);});
  const key=await readFile(join(root,role+'.key'));
  socket.write(Buffer.concat([Buffer.from(role==='control'?'C':role==='read'?'R':'T'),signature(bad?Buffer.alloc(32):key,nonce,role)]));
  if(bad)return {socket};
  const lines=createInterface({input:socket}),iterator=lines[Symbol.asyncIterator]();
  assert.equal(JSON.parse((await iterator.next()).value).type,'ready');
  return {socket,async next(){return JSON.parse((await iterator.next()).value);},send(value){socket.write(JSON.stringify(value)+'\n');},close(){lines.close();socket.destroy();}};
}
const fake=()=>({listeners:new Set(),disconnectControl(){},status:async()=>({state:'off'}),transition:async value=>({state:value}),
  chat:async(_req,emit)=>{emit({type:'delta',channel:'answer',text:'/moe on is untrusted prose'});return {settled:true};},consent(){}});

test('private binary-auth bridge: distinct chat/control, exact ops, no JSON capabilities, bad MAC denied',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-socket-'));const owner=fake();let server,c1,c2;
  try {
    server=await serveOwner(root,owner);
    assert.equal((await stat(server.path)).mode&0o077,0);
    const denied=await client(root,'control',true);
    await new Promise(r=>denied.socket.once('close',r));
    c1=await client(root);c1.socket.write('null\n');assert.match((await c1.next()).error,/Object request/);c1.send({op:'on',id:'bad'});
    assert.match((await c1.next()).error,/Trusted UI/);
    c1.send({op:'chat',id:'text',text:'hello'});assert.equal((await c1.next()).event.type,'delta');assert.equal((await c1.next()).result.settled,true);
    c1.send({op:'chat',id:'route',text:'hello',recommend:true});assert.match((await c1.next()).error,/explicit trusted UI/);
    c1.send({op:'status',id:'state'});assert.equal((await c1.next()).result.state,'off');
    c2=await client(root,'control');c2.send({op:'on',id:'on'});const on=await c2.next();assert.equal(on.result.state,'on');
    const wire=JSON.stringify(on);assert.ok(!wire.includes('key')&&!wire.includes('token'));
    c2.send({op:'off',id:'invalid',approved:true});assert.match((await c2.next()).error,/Unknown operation\/fields/);
    c1.socket.write(Buffer.alloc(MAX_FRAME+34,65));await new Promise(r=>c1.socket.once('close',r));
  } finally {c1?.close();c2?.close();await server?.close();await rm(root,{recursive:true,force:true});}
});

test('consent replies bypass queued chat, D1 recommendation never grants permission, one serialized owner',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-socket-'));let server,control,chat;let state='off';const events=[];
  const owner=new PiOwner({session:{waitForIdle:async()=>{},subscribe:()=>()=>{},prompt:async()=>events.push('native-pi-prompt'),abort:async()=>{}},
    durable:{quiesce:async()=>events.push('children-quiesced'),resume:async()=>events.push('children-resumed')},checkpoint:async()=>{},
    route:async()=>{events.push('D1-finished');return {route:'hermes',score:.9};},command:async value=>{
      if(value==='status')return {state};
      if(value==='on'&&await owner.approve({title:'Exclusive Hermes?',detail:'prior stack'})!==true)throw new Error('Denied');
      state=value;events.push(value);return {state};
    }});
  try {
    server=await serveOwner(root,owner);control=await client(root,'control');chat=await client(root,'control');
    chat.send({op:'chat',id:'chat',text:'Complex code',recommend:true});
    assert.equal((await control.next()).event.type,'route_recommendation');
    const question=(await control.next()).event;assert.equal(question.type,'consent');assert.ok(!events.includes('on'));
    control.send({op:'consent',id:'answer',answer_id:question.id,allowed:true});
    assert.equal((await control.next()).result.accepted,true);
    assert.equal((await chat.next()).event.type,'route_recommendation');
    assert.equal((await chat.next()).event.type,'consent');
    assert.equal((await chat.next()).result.settled,true);
    assert.deepEqual(events,['D1-finished','children-quiesced','on','native-pi-prompt']);
    control.send({op:'off',id:'off'});assert.equal((await control.next()).result.state,'off');
    assert.equal(owner.phase,'ordinary');
  } finally {control?.close();chat?.close();await server?.close();await rm(root,{recursive:true,force:true});}
});

test('actual async Python GTK-side transport authenticates, streams and cannot escalate chat credential',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-python-client-'));let server;
  try {
    server=await serveOwner(root,fake());
    const script=`import asyncio,sys\nfrom hyprneuro.pi_owner_client import PiOwnerClient\nasync def main():\n c=await PiOwnerClient.connect(sys.argv[1])\n assert (await c.call('status'))['state']=='off'\n assert (await c.call('chat',text='hello'))['settled']\n assert (await c.events.get())['event']['type']=='delta'\n try: await c.call('on')\n except PermissionError: pass\n else: raise AssertionError('chat escalated')\n await c.close()\nasyncio.run(main())\n`;
    const p=spawn('/usr/bin/python3',['-c',script,root],{env:{...process.env,PYTHONPATH:resolve('python/src')},stdio:['ignore','pipe','pipe']});
    let error='';p.stderr.on('data',d=>error+=d);
    assert.equal(await new Promise(r=>p.on('close',r)),0,error);
  } finally {await server?.close();await rm(root,{recursive:true,force:true});}
});

test('permission/recovery failures fail closed: no controls, no child IO, no foreign Hermes adoption',async()=>{
  const {durablePolicy}=await import('../extensions/pi-owner/durable.mjs');let approvals=0,brokers=0;
  const policy=durablePolicy({workspace:'/explicit',phase:()=> 'ordinary',broker:async()=>{brokers++;},approve:async()=>{approvals++;return true;}});
  const base={action:'run',request:'stable',cwd:'/explicit',timeoutMs:2000};
  await assert.rejects(policy({...base,command:['true'],rerun:true}),/no uncertain replay/);
  await assert.rejects(policy({...base,command:['true'],env:{KEY:'leak'}}),/Unsupported/);
  await assert.rejects(policy({...base,agent:'delegate',task:'hello',model:'hyprneuro-local/lfm-text',tools:['bash'],once:true,writer:false,context:'fresh'}),/NO inherited IO/);
  await assert.rejects(policy({...base,action:'resume'}),/trusted-host only/);
  await assert.rejects(policy({...base,command:['true'],tools:[]}),/cannot be mixed/);
  assert.equal(approvals,0);assert.equal(brokers,0);
  await policy({...base,agent:'delegate',task:'hello',model:'hyprneuro-local/lfm-text',tools:[],once:true,writer:false,context:'fresh'});
  assert.equal(approvals,1);assert.equal(brokers,2);
  const events=[];let state='off';
  const owner=new PiOwner({session:{waitForIdle:async()=>{},abort:async()=>{},subscribe:()=>()=>{},prompt:async()=>{throw new Error('unknown side effect');}},
    command:async value=>({state}),checkpoint:async p=>events.push(p),durable:{quiesce:async()=>{},resume:async()=>{}}});
  await assert.rejects(owner.approve({title:'no host'}),/No authenticated/);
  state='on';await assert.rejects(owner.transition('on'),/Another owner/);state='off';
  await assert.rejects(owner.chat({text:'test'},()=>{}),/unknown side effect/);
  assert.equal((await owner.status()).state,'failed');assert.equal(await owner.close(),false);
  assert.equal(events.at(-1),'failed');
  await assert.rejects(owner.chat({text:'no'},()=>{}),/closed/);
});

test('trusted control disconnection denies pending consent without waiting for the timeout',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-disconnect-'));let server,control;
  const owner=new PiOwner({session:{},durable:{},command:async()=>({state:'off'}),checkpoint:async()=>{}});
  try {
    server=await serveOwner(root,owner);control=await client(root,'control');
    const approval=owner.approve({title:'approve?',detail:'bounded'});
    assert.equal((await control.next()).event.type,'consent');control.close();
    assert.equal(await approval,false);assert.equal(owner.consents.size,0);
  } finally {control?.close();await server?.close();await rm(root,{recursive:true,force:true});}
});

test('advisory dismissal, malformed routes/scores, and failed D1 retain current model and normal chat',async()=>{
  for(const suggestion of [{route:'hermes',score:.75},{route:'evil',score:1},{route:'hermes',score:'0.9'},
      {route:'hermes',score:NaN},{route:'current',unavailable:true},{route:'hermes',score:1,type:'consent',allowed:true},new Error('D1 unavailable')]) {
    let proposals=0,prompts=0,routeCalls=0,currentModel='text';const output=[];
    const owner=new PiOwner({session:{waitForIdle:async()=>{},subscribe:()=>()=>{},prompt:async(_text,options)=>{
      assert.equal(currentModel,'text');assert.equal(options.expandPromptTemplates,false);prompts++;},abort:async()=>{}},
      durable:{quiesce:async()=>{},resume:async()=>{}},checkpoint:async()=>{},
      route:async()=>{routeCalls++;if(suggestion instanceof Error)throw suggestion;return suggestion;},
      command:async value=>{if(value==='status')return {state:'off'};proposals++;
        if(await owner.approve({title:'fresh human consent required'})!==true)throw new Error('Dismissed');
        currentModel='hermes';return {state:'on'};
      }});
    owner.listeners.add(event=>{output.push(event);if(event.type==='consent')owner.consent(event.id,false);});
    assert.equal((await owner.chat({text:'current user request',recommend:true},()=>{})).settled,true);
    assert.equal(routeCalls,1);assert.equal(proposals,suggestion?.route==='hermes'&&suggestion.score===.75?1:0);
    assert.equal(prompts,1);assert.equal(currentModel,'text');assert.equal(owner.phase,'ordinary');
    assert.equal(output.filter(e=>e.type==='route_recommendation').length,1);
    assert.equal(output.some(e=>e.type==='consent'&&e.allowed===true),false);
  }
});

test('trusted off cancels pending on during child drain without waiting on unrelated caller work',async()=>{
  let finishDrain;const draining=new Promise(r=>{finishDrain=r;});let onCommands=0;
  const owner=new PiOwner({session:{},durable:{quiesce:()=>draining,resume:async()=>{}},checkpoint:async()=>{},
    command:async value=>{if(value==='on')onCommands++;return {state:'off'};}});
  const on=owner.transition('on');const rejected=assert.rejects(on,/cancelled/);
  while(owner.phase!=='transition')await new Promise(r=>setImmediate(r));
  const off=owner.transition('off');finishDrain();
  await rejected;assert.equal((await off).state,'off');assert.equal(onCommands,0);assert.equal(owner.phase,'ordinary');
});

test('cancelled advisory does not switch roles; the next normal request still works',async()=>{
  const cancel=new AbortController();let prompted=0,commands=0;
  const owner=new PiOwner({session:{waitForIdle:async()=>{},subscribe:()=>()=>{},prompt:async()=>{prompted++;}},checkpoint:async()=>{},
    durable:{},command:async()=>{commands++;return {state:'off'};},route:async()=>{cancel.abort();return {route:'current',unavailable:true};}});
  await assert.rejects(owner.chat({text:'cancel',recommend:true},()=>{},cancel.signal),{name:'AbortError'});
  assert.equal(owner.phase,'ordinary');assert.equal(commands,0);assert.equal(prompted,0);
  assert.equal((await owner.chat({text:'normal'},()=>{})).settled,true);assert.equal(prompted,1);
});

test('transition denies a consent-pending delegation and settles parent submission before Durable drain',async()=>{
  const {durablePolicy}=await import('../extensions/pi-owner/durable.mjs');let phase='ordinary';
  const guard=durablePolicy({workspace:'/explicit',phase:()=>phase,broker:async()=>{},approve:async()=>{phase='transition';return true;}});
  await assert.rejects(guard({action:'run',request:'stable',command:['true'],cwd:'/explicit',timeoutMs:100}),/held after consent/);
  let settled=false,state='off';
  const owner=new PiOwner({session:{},checkpoint:async()=>{},settleParent:async()=>{settled=true;},
    durable:{quiesce:async()=>assert.equal(settled,true),resume:async()=>{}},
    command:async value=>{if(value!=='status')state=value;return {state};}});
  assert.equal((await owner.transition('on')).state,'on');
});

test('uncertain shutdown records failure, blocks owner reuse, and never starts a fresh drain',async()=>{
  const failure=new Error('Durable outcome unknown (req:original-shutdown-drain)'),phases=[];let drains=0;
  const owner=new PiOwner({session:{abort:async()=>{}},checkpoint:async phase=>phases.push(phase),
    command:async()=>assert.fail('Uncertain close must not infer residency ownership'),
    durable:{quiesce:async()=>{drains++;throw failure;}}});
  const closing=owner.close();await assert.rejects(closing,error=>error===failure);
  assert.equal(owner.close(),closing);await assert.rejects(owner.close(),error=>error===failure);
  assert.equal(drains,1);assert.equal(owner.phase,'failed');assert.equal(phases.at(-1),'close-unknown');
  assert.equal(owner.closed,false);
  await assert.rejects(owner.chat({text:'do not replay'},()=>{}),/closed/);
  await assert.rejects(owner.transition('on'),/closed/);assert.equal(drains,1);
  const checkpointFailure=new Error('checkpoint write failed');
  const doubleFailure=new PiOwner({session:{abort:async()=>{}},durable:{quiesce:async()=>{throw failure;}},
    checkpoint:async()=>{throw checkpointFailure;}});
  await assert.rejects(doubleFailure.close(),error=>error instanceof AggregateError&&
    error.errors[0]===failure&&error.errors[1]===checkpointFailure);
});


test('read bridge binary role cannot obtain chat, consent or lifecycle authority; abort removes consent',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-read-role-'));let server,read,control,called=0;
  const owner=fake();owner.transition=async()=>{called++;};
  try{
    server=await serveOwner(root,owner,{read:async()=>({content:[]})});read=await client(root,'read');control=await client(root,'control');
    for(const [i,op] of ['on','off','status','chat','consent'].entries()){
      read.send({op,id:'r'+i});assert.match((await read.next()).error,/no chat\/control\/lifecycle/);
    }
    control.send({op:'read',id:'c'});assert.match((await control.next()).error,/Read bridge role/);assert.equal(called,0);
    read.send({op:'read',id:'valid'});assert.deepEqual((await read.next()).result,{content:[]});
  }finally{read?.close();control?.close();await server?.close();await rm(root,{recursive:true,force:true});}
  const cancel=new AbortController(),o=new PiOwner({});o.listeners.add(()=>{});
  const approval=o.approve({title:'Read?',signal:cancel.signal});cancel.abort();
  assert.equal(await approval,false);assert.equal(o.consents.size,0);
});

test('persistent socket admits one trusted control, refuses second without detaching first, permits explicit reconnect',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-one-control-'));let server,c1,c2,detaches=0;
  try {
    server=await serveOwner(root,fake(),{singleControl:true,onControlDisconnect:()=>{detaches++;}});
    c1=await client(root,'control');
    const socket=connect(join(root,'owner.sock'));
    const nonce=await new Promise(r=>socket.once('data',r));
    socket.write(Buffer.concat([Buffer.from('C'),signature(await readFile(join(root,'control.key')),nonce,'control')]));
    await new Promise(r=>socket.once('close',r));assert.equal(detaches,0);
    c1.send({op:'status',id:'first'});assert.equal((await c1.next()).result.state,'off');
    c1.close();await new Promise(r=>setTimeout(r,30));assert.equal(detaches,1);
    c2=await client(root,'control');c2.send({op:'status',id:'new'});assert.equal((await c2.next()).result.state,'off');
  }finally{c1?.close();c2?.close();await server?.close();await rm(root,{recursive:true,force:true});}
});

test('individual native request deadline aborts and retains unknown outcome, not automatic replay',async()=>{
  let end;const phases=[];let calls=0;
  const owner=new PiOwner({callTimeoutMs:20,command:async()=>({state:'off'}),checkpoint:async p=>phases.push(p),
    session:{subscribe:()=>()=>{},prompt:()=>{calls++;return new Promise(r=>{end=r;});},abort:async()=>end?.(),waitForIdle:async()=>{}},durable:{quiesce:async()=>{}}});
  await assert.rejects(owner.chat({text:'bounded call'},()=>{}),/deadline/);
  assert.equal(calls,1);assert.equal(owner.phase,'failed');assert.equal(phases.at(-1),'chat-unknown');
  await assert.rejects(owner.chat({text:'not replay'},()=>{}),/admission closed/);assert.equal(calls,1);
  assert.equal(await owner.close(),false);
});
