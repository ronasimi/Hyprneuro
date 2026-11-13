import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {completeIdentified} from '../extensions/pi-owner/durable.mjs';

const packageDir=process.env.PI_HARNESS_DURABLE;
if(!packageDir)throw new Error('Explicit installed PI_HARNESS_DURABLE required; no installs');
const load=p=>import(pathToFileURL(join(packageDir,'dist',p)));
const {readerLedger}=await load('orchestrator/reader-ledger.js');
const {readJournalSnapshot}=await load('kernel/journal.js');
const control=await load('cli/control.js');
const {findRequest}=await load('requests.js');
const {processAlive}=await load('orchestrator/snapshot.js');

async function until(check,message,ms=5000) {
  const deadline=performance.now()+ms;
  while(!await check()) {
    if(performance.now()>=deadline)assert.fail(message);
    await delay(10);
  }
}
async function exists(path){try{await readFile(path);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
function records(home){return readJournalSnapshot(join(home,'orchestrator.jsonl'));}
async function drainEnvelopes(home) {
  // Native API owns checksum/journal reading. Never inspect the parent's home.
  const {readdir}=await import('node:fs/promises');
  const dir=join(home,'outbox'),envelopes=[];
  for(const file of await readdir(dir).catch(e=>{if(e.code==='ENOENT')return [];throw e;})) {
    for(const entry of readJournalSnapshot(join(dir,file)))
      if(entry.type==='sent'&&entry.request.kind==='drain')envelopes.push(entry.request);
  }
  return envelopes;
}
async function pendingDrain(home){return (await drainEnvelopes(home))[0];}

// Actual installed Engine/main, with a test-only barrier at executor shutdown.
// The real loop has exited but still owns the actual orchestrator flock. A
// request published now cannot be consumed by that generation. No model/agent
// launches, service operations, default-home work or installed-package edits.
async function closingOrchestrator(run) {
  const root=await mkdtemp(join(tmpdir(),'hn-durable-exit-')),home=join(root,'durable'),priorCache=process.env.DSA_CACHE_HOME;
  process.env.DSA_CACHE_HOME=join(home,'cache');
  await mkdir(home,{mode:0o700});await mkdir(join(root,'agent'),{mode:0o700});
  await writeFile(join(home,'config.json'),JSON.stringify({exactCapture:false,k:{idleExitMs:10}}),{mode:0o600});
  const entry=join(root,'closing.mjs'),closing=join(root,'closing'),release=join(root,'release');
  await writeFile(entry,`
import {main} from ${JSON.stringify(pathToFileURL(join(packageDir,'dist/orchestrator/main.js')).href)};
import factory from ${JSON.stringify(pathToFileURL(join(packageDir,'dist/orchestrator/executor/index.js')).href)};
import {open,readFile} from 'node:fs/promises';
import {setTimeout as delay} from 'node:timers/promises';
await main({home:${JSON.stringify(home)},executor:(...args)=>{
 const executor=factory(...args),shutdown=executor.shutdown.bind(executor);
 executor.shutdown=async()=>{
  let first;
  try{first=await open(${JSON.stringify(closing)},'wx',0o600);}catch(e){if(e.code!=='EEXIST')throw e;}
  if(first){
   await first.writeFile(String(process.pid));await first.close();const deadline=performance.now()+15000;
   while(true){try{await readFile(${JSON.stringify(release)});break;}catch(e){if(e.code!=='ENOENT')throw e;}
    if(performance.now()>deadline)throw new Error('Test shutdown barrier deadline');await delay(10);}
  }
  await shutdown();
 };return executor;
}});
`,{mode:0o600});
  const env={...process.env,DSA_HOME:home,DSA_CACHE_HOME:join(home,'cache'),DSA_SCOPE:'off',DSA_PI_BIN:'/home/ron/.pi/agent/bin/pi',
    PI_CODING_AGENT_DIR:join(root,'agent'),DSA_ORCHESTRATOR_ENTRY:entry};
  const child=spawn(process.execPath,[entry],{env,stdio:['ignore','ignore','pipe']});
  let stderr='';child.stderr.on('data',d=>{stderr=(stderr+d).slice(-10000);});
  const ended=new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',resolve);});
  let passed=false,retain=false;
  try {
    await until(()=>exists(closing),'Actual native Engine never reached shutdown');
    assert.equal(readerLedger(home).state.state.orchestrator.pid,child.pid);
    retain=(await run({root,home,env,release,ended,child}))?.retain===true;
    passed=true;
  } catch(error) {
    await writeFile(join(root,'failure.txt'),(error.stack??String(error))+'\n'+stderr,{mode:0o600});throw error;
  } finally {
    await writeFile(release,'release',{mode:0o600});
    // Only this fixture's known child may be signalled; never a discovered PID.
    const timer=setTimeout(()=>child.kill('SIGTERM'),2000);
    try{await ended;}finally{clearTimeout(timer);}
    await until(()=>{const o=readerLedger(home).state.state.orchestrator;return !o||o.exited||!processAlive(o.pid,o.start);},'Temporary native orchestrator did not exit');
    if(priorCache===undefined)delete process.env.DSA_CACHE_HOME;else process.env.DSA_CACHE_HOME=priorCache;
    if(passed&&!retain)await rm(root,{recursive:true,force:true});
    else console.error('Durable failure/uncertainty journals retained:',root);
  }
}

test('identified drain survives an exiting orchestrator using exactly one request identity',async()=>{
  await closingOrchestrator(async({home,env,release,ended,child})=>{
    let submitted,submissionError,submissions=0,starts=0;
    const firstStarterReturned=new Promise(resolve=>{submitted=resolve;});
    const native={...control,submitIdentified:async(...args)=>{
      submissions++;
      try{return await control.submitIdentified(...args);}catch(error){submissionError=error;throw error;}finally{submitted();}
    },start:async(...args)=>{starts++;return control.start(...args);}};
    const quiesced=completeIdentified(native,home,'req:shutdown-drain','drain',{},env);
    quiesced.catch(()=>{});
    await firstStarterReturned; // deterministic: native starter ALREADY observed the retiring lock
    if(submissionError)throw submissionError;
    await until(async()=>!!await pendingDrain(home),'Identified drain was not published');
    const sent=await pendingDrain(home);
    assert.equal((await findRequest(home,sent.rid)).admitted,false);
    // The first native starter observed the retiring lock holder. Let that
    // generation finish without admitting the request; no request is resubmitted.
    await writeFile(release,'release',{mode:0o600});assert.equal(await ended,0);
    assert.deepEqual(await quiesced,{type:'applied'});
    const ledger=records(home);
    assert.equal(ledger.filter(e=>e.type==='request'&&e.request.rid===sent.rid).length,1);
    assert.equal(ledger.filter(e=>e.type==='applied'&&e.rid===sent.rid).length,1);
    assert.equal(ledger.filter(e=>e.type==='request'&&e.request.kind==='drain').length,1);
    assert.equal((await control.resolution(home,sent.rid,0)).type,'applied');
    assert.ok(ledger.some(e=>e.type==='orchestrator'&&e.pid!==child.pid));
    assert.equal((await findRequest(home,sent.rid)).request.rid,sent.rid);
    assert.equal(submissions,1);assert.ok(starts>=1);
    assert.deepEqual(await drainEnvelopes(home),[sent]);
  });
});

test('unavailable successor retains the same unresolved drain and original 10s completion budget',async()=>{
  await closingOrchestrator(async({root,home,env})=>{
    let submissions=0,starts=0,submittedAt;
    const native={...control,submitIdentified:async(...args)=>{
      submissions++;const result=await control.submitIdentified(...args);submittedAt=performance.now();return result;
    },start:async(...args)=>{starts++;return control.start(...args);}};
    // Keep the old authority's real flock held through the entire decision
    // deadline. Startup probes may NOT replace/kill it or fabricate application.
    let failure;
    await assert.rejects(completeIdentified(native,home,'req:unresolved-drain','drain',{},env),error=>{
      failure=error;return /outcome unknown.*req:unresolved-drain/.test(error.message);
    });
    const elapsed=performance.now()-submittedAt;
    assert.ok(elapsed>=10000&&elapsed<11500,`Completion deadline changed: ${elapsed}ms`);
    assert.equal(submissions,1);assert.ok(starts>=2);
    assert.equal(records(home).filter(e=>e.type==='orchestrator').length,1);
    assert.equal(records(home).filter(e=>e.type==='request').length,0);
    const sent=await pendingDrain(home);
    assert.equal(sent.rid,'req:unresolved-drain');assert.deepEqual(await drainEnvelopes(home),[sent]);
    assert.equal((await findRequest(home,sent.rid)).admitted,false);
    assert.equal(await control.resolution(home,sent.rid,0),undefined);
    await writeFile(join(root,'expected-uncertainty.txt'),failure.stack,{mode:0o600});
    return {retain:true};
  });
});

test('already-decided rejection and request conflict do not kick or replace the mutation',async()=>{
  let submissions=0;
  const rejected={type:'rejected',reason:'test rejection'};
  const native={submitIdentified:async(_home,rid)=>{submissions++;assert.equal(rid,'req:one');return {request:{rid}};},
    resolution:async(_home,rid)=>{assert.equal(rid,'req:one');return rejected;},start:async()=>assert.fail('Known decision needs no starter')};
  assert.equal(await completeIdentified(native,'/unused','req:one','drain',{},{}),rejected);
  assert.equal(submissions,1);
  await assert.rejects(completeIdentified({...native,submitIdentified:async()=>({conflict:{}})},'/unused','req:one','drain',{},{}),/request conflict/);
});
