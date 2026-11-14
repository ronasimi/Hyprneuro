// Public native Pi PipeTransport supplies framing. This module owns only the
// fixed anchor process/pipe lifecycle; no SDK patch or alternate MCP client.
import { spawn } from 'node:child_process';
import { readFileSync,readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
const helper=fileURLToPath(new URL('./stdio-anchor.mjs',import.meta.url));
const failure=()=>new Error('Owned MCP stdio cleanup/start failed; ownership retained for review');
export function processIdentity(pid) {
  let raw;
  try {raw=readFileSync(`/proc/${pid}/stat`,'utf8');}
  catch(e){if(['ENOENT','ESRCH'].includes(e.code))return;throw e;}
  const fields=raw.slice(raw.lastIndexOf(')')+2).split(' ');
  return {pid,state:fields[0],group:Number(fields[2]),session:Number(fields[3]),start:fields[19]};
}
// The anchor never voluntarily exits or accepts TERM. A reused PID/group, a
// zombie, or lost identity is NOT authority to signal a numeric process group.
export function signalPinnedGroup(identity,signal,read=processIdentity,kill=process.kill) {
  const now=read(identity.pid);
  if(identity.pid<=1||!now||now.state==='Z'||now.start!==identity.start||now.group!==identity.pid||now.session!==identity.pid)throw failure();
  kill(-identity.pid,signal);
}
function liveGroup(pid) {
  return readdirSync('/proc').filter(p=>/^\d+$/.test(p)).some(p=>{
    const info=processIdentity(Number(p));return info?.group===pid&&!['Z','X'].includes(info.state);
  });
}
async function bounded(promise,ms) {
  let timer;
  try {return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(failure()),ms);})]);}
  finally {clearTimeout(timer);}
}
async function openPipe(config,handlers) {
  const child=spawn(process.execPath,[helper,config.command,...config.args],{cwd:config.cwd,
    env:config.env,detached:true,shell:false,stdio:['pipe','pipe','pipe','ipc']});
  const ended=new Promise(resolve=>child.once('close',resolve));
  await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',()=>reject(failure()));});
  let identity;
  try {
    identity=processIdentity(child.pid);
    if(!identity||identity.group!==child.pid||identity.session!==child.pid)throw failure();
  } catch(error) {
    // No guessed PGID kill if identity could not be established. A live fixed
    // helper self-cleans its own group on IPC loss, including startup races.
    if(child.connected)child.disconnect();
    await bounded(ended,1500);throw error;
  }
  child.stdout.on('data',handlers.onStdout);child.stderr.on('data',handlers.onStderr);
  let resolve,reject,readyResolve,readyReject,closing,killSent=false;
  const ready=new Promise((yes,no)=>{readyResolve=yes;readyReject=no;});
  const exited=new Promise((yes,no)=>{resolve=yes;reject=no;});exited.catch(()=>{});
  const begin=()=>{
    if(closing)return closing;
    closing=(async()=>{
      child.stdin.end();await delay(100); // Real stdin EOF, independently of server exit.
      signalPinnedGroup(identity,'SIGTERM');await delay(200);
      // Last group signal while the anchor is alive and still pins this PGID.
      signalPinnedGroup(identity,'SIGKILL');killSent=true;
      child.stdin.destroy();child.stdout.destroy();child.stderr.destroy();
      await bounded(ended,1000); // Node has reaped the actual anchor.
      const deadline=Date.now()+500;
      while(liveGroup(identity.pid)){if(Date.now()>deadline)throw failure();await delay(10);}
      // No late numeric signals after reaping, even if this PID/group is reused.
    })().finally(()=>{
      // Even unknown/lost-identity cleanup releases local I/O, never guesses a
      // PGID. IPC loss lets a still-live fixed helper self-clean its own group.
      child.stdin.destroy();child.stdout.destroy();child.stderr.destroy();
      if(child.connected)child.disconnect();
    });
    closing.then(resolve,reject);return closing;
  };
  child.stdin.on('error',()=>{void begin().catch(()=>{});});
  child.stdout.on('error',()=>{void begin().catch(()=>{});});
  child.stderr.on('error',()=>{void begin().catch(()=>{});});
  child.on('message',message=>{
    if(message?.type==='ready')readyResolve();
    if(message?.type==='server_exit')void begin().catch(()=>{});
  });
  child.once('exit',()=>{
    if(!killSent){readyReject(failure());reject(failure());void begin().catch(()=>{});}
  });
  // Do not permit close/open races to TERM a not-yet-initialized Node helper.
  // Its handlers and inherited-FD setup are established before publishing a pipe.
  try {await bounded(ready,1000);}catch(error){await begin().catch(()=>{});throw error;}
  return {exited,write:data=>{if(closing)throw failure();child.stdin.write(data);},
    closeStdin:()=>{void begin().catch(()=>{});},close:()=>{void begin().catch(()=>{});}};
}
export function ownedStdioTransport(mcp,config) {
  if(process.platform!=='linux'||!mcp.PipeTransport)throw failure();
  let opening,pipe,closing;
  const native=new mcp.PipeTransport({maxMessageBytes:config.maxMessageBytes,maxStderrBytes:1024,closeTimeoutMs:1000,
    open:handlers=>(opening=openPipe(config,handlers).then(value=>(pipe=value)))});
  return {
    start:()=>native.start(),send:(...args)=>native.send(...args),
    onMessage:f=>native.onMessage(f),onError:f=>native.onError(f),onClose:f=>native.onClose(f),
    close:()=>closing??=(async()=>{
      // Native close can race an unresolved open. Always await our pipe's actual
      // cleanup too, not the SDK's early-return "already closed" branch.
      const close=native.close();
      await opening;pipe?.closeStdin();
      await Promise.all([close,pipe?.exited]);
    })(),
  };
}
