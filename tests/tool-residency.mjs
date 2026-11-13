import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,writeFile,rm } from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {control,admit} from '../extensions/tool-harness/residency.mjs';

// Real Node->Python control, real flock; fake systemctl output, NO live services.
test('cross-language admission holds and releases OS locks; invalid/stale owner denied',async()=>{
  const root=await mkdtemp(join(tmpdir(),'hn-residency-'));
  const saved={...process.env};
  try {
    const directory=join(root,'private');await mkdir(directory,{mode:0o700});
    const expected=Object.fromEntries(['text','omni','decision','moe'].map(r=>[r,{
      Id:`lfm@${r}.service`,ActiveState:r==='text'?'active':'inactive',SubState:r==='text'?'running':'dead',
      MainPID:r==='text'?'123':'0',InvocationID:r==='text'?'fake':''}]));
    const output=Object.values(expected).map(row=>Object.entries(row).map(([k,v])=>k+'='+v).join('\n')).join('\n\n');
    await writeFile(join(root,'services'),output);
    await writeFile(join(root,'systemctl'),`#!/bin/sh\n/bin/cat '${root}/services'\n`,{mode:0o700});
    await writeFile(join(directory,'state.json'),JSON.stringify({phase:'idle',expected}),{mode:0o600});
    process.env.HYPRNEURO_RESIDENCY_DIR=directory;
    process.env.HYPRNEURO_PYTHON='/usr/bin/python3';
    process.env.PATH=root+':'+saved.PATH;
    const release=await admit('text');
    const another=await admit('text');await another();await release();
    await assert.rejects(()=>admit('hermes','invalid'),/Residency|admission/);
    await writeFile(join(directory,'state.json'),JSON.stringify({phase:'blocked',expected}));
    await assert.rejects(()=>admit('text'),/Residency|admission/);
    const helper=control('admit','text');await assert.rejects(()=>helper.next(),/Residency/);await helper.closed.catch(()=>{});
  } finally {
    for(const key of Object.keys(process.env))if(!(key in saved))delete process.env[key];
    Object.assign(process.env,saved);await rm(root,{recursive:true,force:true});
  }
});

test('native Pi transport fails CLOSED before HTTP; verifies release before terminal event; abort releases',async()=>{
  const {pathToFileURL}=await import('node:url');
  const {createServer}=await import('node:http');
  const {guardedStream}=await import('../extensions/tool-harness/residency.mjs');
  const aiURL=new URL('../../pi-ai/dist/index.js',pathToFileURL(process.env.PI_HARNESS_SDK));
  const {lazyStream}=await import(aiURL);
  const {streamSimple}=await import(new URL('./api/openai-completions.js',aiURL));
  const native={lazyStream,streamSimple};let requests=0,stall=false;
  const server=createServer(async(req,res)=>{
    requests++;for await(const _ of req){}
    res.writeHead(200,{'content-type':'text/event-stream'});res.flushHeaders();
    if(stall)return;
    res.end('data: '+JSON.stringify({choices:[{index:0,delta:{content:'ok'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const model={id:'lfm-text',provider:'hyprneuro-local',api:'openai-completions',baseUrl:`http://127.0.0.1:${server.address().port}/v1`,
    input:['text'],reasoning:false,contextWindow:1000,maxTokens:100,cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
    compat:{supportsDeveloperRole:false,supportsStore:false,supportsUsageInStreaming:false,maxTokensField:'max_tokens'}};
  const context={messages:[{role:'user',content:[{type:'text',text:'test'}],timestamp:Date.now()}]};
  try {
    const denied=guardedStream(native,model,context,{apiKey:'mock'},undefined,async()=>{throw new Error('blocked');});
    assert.equal((await denied.result()).stopReason,'error');assert.equal(requests,0);
    let releases=0;
    const failure=guardedStream(native,model,context,{apiKey:'mock'},undefined,async()=>async()=>{releases++;throw new Error('external residency change');});
    const events=[];for await(const event of failure)events.push(event);
    assert.equal(releases,1);assert.equal(events.at(-1).type,'error');assert.ok(!events.some(e=>e.type==='done'));
    stall=true;const abort=new AbortController();
    const cancelled=guardedStream(native,model,context,{apiKey:'mock',signal:abort.signal},undefined,async()=>async()=>{releases++;});
    setTimeout(()=>abort.abort(),50);
    assert.equal((await cancelled.result()).stopReason,'aborted');assert.equal(releases,2);
  } finally {server.closeAllConnections();await new Promise(r=>server.close(r));}
});

test('lease status never confers ownership, including the same task ID',async()=>{
  const {releaseOwnedLease}=await import('../extensions/tool-harness/residency.mjs');
  const calls=[];
  const rpc=async packet=>{calls.push(packet);return packet.action==='lease_status'?{active:{task_id:'same-task',token:'observed-not-owned'}}:{released:true};};
  await assert.rejects(()=>releaseOwnedLease(rpc,'same-task'),/not held/);
  assert.deepEqual(calls.map(p=>p.action),['lease_status']);calls.length=0;
  await releaseOwnedLease(rpc,'same-task',{task_id:'same-task',token:'actual-acquisition-capability'});
  assert.equal(calls[1].token,'actual-acquisition-capability');
  assert.notEqual(calls[1].token,'observed-not-owned');
});

test('unexpected helper exit invalidates capability before failure/model restoration; expected exit is quiet',async()=>{
  const {watchHandoff}=await import('../extensions/tool-harness/residency.mjs');
  for(const failed of [false,true]) {
    let close,fail;
    const owner={token:'private',closed:new Promise((r,j)=>{close=r;fail=j;})};
    let selected='hermes',failure;
    const observed=watchHandoff(owner,error=>{assert.equal(owner.token,undefined);failure=error.message;selected='prior';});
    failed?fail(new Error('helper crashed')):close();
    await observed;
    assert.equal(owner.token,undefined);assert.equal(selected,'prior');assert.match(failure,/unexpectedly/);
  }
  let close;const owner={token:'private',expectedClose:true,closed:new Promise(r=>{close=r;})};
  const observed=watchHandoff(owner,()=>assert.fail('expected off reported as failure'));
  close();await observed;assert.equal(owner.token,undefined);
});
