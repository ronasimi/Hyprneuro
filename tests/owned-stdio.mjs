// Installed native Pi PipeTransport/McpClient; fixed local inert processes only.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,rm } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { pathToFileURL,fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { ownedProcesses as owned } from './fixtures/owned-processes.mjs';
import { ownedStdioTransport,signalPinnedGroup } from '../extensions/tool-harness/owned-stdio.mjs';
if(!process.env.PI_HARNESS_SDK||!process.env.TMPDIR?.includes('/Workspace/'))throw new Error('Explicit installed SDK and private Workspace TMPDIR required');
const mcp=await import(new URL('../../pi-mcp/dist/index.js',pathToFileURL(process.env.PI_HARNESS_SDK)));
const server=fileURLToPath(new URL('./fixtures/mcp-provider.mjs',import.meta.url));
async function fixture(mode,run) {
  const root=await mkdtemp(join(process.env.TMPDIR,'owned-stdio-'));await mkdir(join(root,'home'),{mode:0o700});
  const record=join(root,'calls.jsonl');let transport,client,witness;
  try {
    // An unrelated but test-owned sentinel group must never receive a signal
    // from closing the MCP group, including repeated late close/cancel calls.
    witness=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{detached:true,stdio:'ignore'});
    await new Promise((resolve,reject)=>{witness.once('spawn',resolve);witness.once('error',reject);});
    transport=ownedStdioTransport(mcp,{command:mode==='spawn-fail'?join(root,'not-installed'):process.execPath,
      args:mode==='spawn-fail'?[]:[server,record,mode],cwd:root,env:{HOME:join(root,'home'),PATH:'/usr/bin:/bin',LANG:'C.UTF-8'},maxMessageBytes:262144});
    client=new mcp.McpClient({name:'offline-fixture',version:'1',requestTimeoutMs:1000});
    await run({transport,client,root,record,witness});
  } finally {
    // Cleanup completes BEFORE assertions or removing fixture files. If it
    // fails, retain the failure but emergency-clean only our pinned helper group.
    let failure;
    try {
      try {await Promise.all([client?.close(),transport?.close()]);}catch(e){failure=e;}
      const remaining=await owned(root);
      if(remaining.length) {
        failure??=new Error('Owned fixture processes survived normal cleanup');
        for(const info of remaining)if(info.pid===info.group&&info.session===info.pid)signalPinnedGroup(info,'SIGKILL');
        for(let i=0;i<100&&(await owned(root)).length;i++)await delay(10);
        assert.equal((await owned(root)).length,0,'Emergency cleanup left an owned live fixture');
      }
    } catch(e){failure??=e;} finally {
      if(witness) {
        if(witness.exitCode!==null||witness.signalCode!==null)failure??=new Error('MCP cleanup killed unrelated sentinel');
        else {const exited=new Promise(resolve=>witness.once('close',resolve));witness.kill('SIGKILL');await exited;}
      }
      await rm(root,{recursive:true,force:true});
    }
    if(failure)throw failure;
  }
}

test('group reuse/lost/zombie identities never authorize a stale numeric group signal',()=>{
  const identity={pid:4242,start:'123',group:4242,session:4242},signals=[];
  for(const now of [undefined,{...identity,start:'456',state:'S'},{...identity,group:999,state:'S'},{...identity,session:999,state:'S'},{...identity,state:'Z'}])
    assert.throws(()=>signalPinnedGroup(identity,'SIGKILL',()=>now,(...args)=>signals.push(args)),/ownership retained/);
  assert.deepEqual(signals,[]);
  signalPinnedGroup(identity,'SIGTERM',()=>({...identity,state:'S'}),(...args)=>signals.push(args));
  assert.deepEqual(signals,[[-4242,'SIGTERM']]);
});

test('actual SDK repeated cancel + concurrent/late close clean resistant descendants exactly once',{timeout:10000},()=>fixture('orphan-eof',async f=>{
  await f.client.connect(f.transport);await f.client.listTools();
  const abort=new AbortController();
  const call=f.client.callTool('web_search_exa',{query:'stall'},{signal:abort.signal}).catch(e=>e);
  abort.abort();abort.abort();
  const close=f.transport.close();assert.equal(f.transport.close(),close);
  await Promise.all([close,f.client.close(),call]);
  assert.equal(f.transport.close(),close);await f.transport.close();
  assert.equal((await owned(f.root)).length,0);
  assert.equal(f.witness.exitCode,null);
}));

test('actual SDK startup failure has bounded cleanup and no retained live anchor',{timeout:10000},()=>fixture('spawn-fail',async f=>{
  const start=Date.now();await assert.rejects(()=>f.client.connect(f.transport));await f.transport.close();
  assert.ok(Date.now()-start<2000);assert.equal((await owned(f.root)).length,0);
}));

test('actual SDK close racing native pipe open awaits real process cleanup',{timeout:10000},async()=>{
  for(let i=0;i<3;i++)await fixture('orphan-eof',async f=>{
    const start=f.transport.start(),close=f.transport.close();
    await Promise.allSettled([start,close]);await f.transport.close();
    assert.equal((await owned(f.root)).length,0);assert.equal(f.witness.exitCode,null);
  });
});


test('host exit disconnects private IPC and self-cleans the pinned group',{timeout:10000},()=>fixture('orphan-eof',async f=>{
  const helperScript=`
import {ownedStdioTransport} from ${JSON.stringify(new URL('../extensions/tool-harness/owned-stdio.mjs',import.meta.url).href)};
import * as mcp from ${JSON.stringify(new URL('../../pi-mcp/dist/index.js',pathToFileURL(process.env.PI_HARNESS_SDK)).href)};
const transport=ownedStdioTransport(mcp,{command:process.execPath,args:[${JSON.stringify(server)},${JSON.stringify(f.record)},'orphan-eof'],cwd:${JSON.stringify(f.root)},env:{PATH:'/usr/bin:/bin',HOME:${JSON.stringify(join(f.root,'home'))}},maxMessageBytes:262144});
const client=new mcp.McpClient({name:'offline',version:'1',requestTimeoutMs:1000});
await client.connect(transport);await client.listTools();process.exit(0);
`;
  const parent=spawn(process.execPath,['--input-type=module','-e',helperScript],{cwd:f.root,env:{PATH:'/usr/bin:/bin',HOME:join(f.root,'home')},stdio:'ignore'});
  try {
    await new Promise((resolve,reject)=>{parent.once('error',reject);parent.once('close',code=>code===0?resolve():reject(new Error('private fixture host failed')));});
    for(let i=0;i<100&&(await owned(f.root)).length;i++)await delay(10);
    assert.equal((await owned(f.root)).length,0);
  } finally {
    if(parent.exitCode===null){const ended=new Promise(r=>parent.once('close',r));parent.kill('SIGKILL');await ended;}
  }
}));


test('an assertion failure still explicitly cleans and reaps private SDK fixtures',{timeout:10000},async()=>{
  await assert.rejects(()=>fixture('orphan-eof',async f=>{
    await f.client.connect(f.transport);await f.client.listTools();
    assert.fail('intentional fixture assertion');
  }),/intentional fixture assertion/);
});
