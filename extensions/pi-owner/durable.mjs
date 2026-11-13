// Installed Durable APIs own submissions, children, journals and replay. No workflow loop here.
import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

// One immutable mutation envelope; callers never replace its identity on uncertainty.
export async function completeIdentified(control,home,rid,kind,body,env) {
  const result=await control.submitIdentified(home,rid,kind,body,undefined,env);
  if(!result.request)throw new Error('Durable request conflict');
  const deadline=performance.now()+10000; // original completion budget, never renewed
  do {
    const resolution=await control.resolution(home,rid,Math.max(0,Math.min(250,deadline-performance.now())),25);
    if(resolution)return resolution;
    // The initial starter can observe an idle-exiting lock holder AFTER its
    // intake loop closed. Waiting alone strands the published request. Native
    // start checks pending work and exclusion; it publishes NO new control envelope.
    // Do not resubmit, replace rid, resume anything, or restart a live authority.
    if(performance.now()<deadline)await control.start(home,env);
  } while(performance.now()<deadline);
  throw new Error(`Durable hold/resume not applied: outcome unknown; inspect journals, never replay (${rid})`);
}

export async function durableRuntime(packageDir,home,env) {
  const manifest=JSON.parse(await readFile(join(packageDir,'package.json'),'utf8'));
  if(manifest.name!=='pi-durable-subagents'||manifest.version!=='1.4.3')throw new Error('Reviewed Durable1.4.3 required; review other versions before activation');
  const load=p=>import(pathToFileURL(join(packageDir,'dist',p)));
  const control=await load('cli/control.js'),{requestRid}=await load('requests.js');
  const {statusView}=await load('orchestrator/snapshot.js');
  const {readerLedger}=await load('orchestrator/reader-ledger.js');
  const {describe}=await load('cli/requests.js');
  let held=[];
  async function decide(kind,body) {
    const rid=requestRid('hn-'+randomUUID());
    const resolution=await completeIdentified(control,home,rid,kind,body,env);
    if(resolution?.type==='rejected'&&kind==='resume'&&resolution.reason.startsWith('terminal:')) {
      const workflow=statusView(home).workflows.find(w=>w.wid===body.wid);
      if(workflow&&!workflow.active&&['done','failed','stopped'].includes(workflow.status))return;
    }
    if(resolution?.type!=='applied')throw new Error('Durable hold/resume not applied: '+(resolution?.reason??'outcome unknown; inspect journals, never replay'));
  }
  return {
    status:()=>statusView(home),describe:wid=>describe(home,{wid}),
    async quiesce(timeout=120000) {
      const before=statusView(home);
      held=before.workflows.filter(w=>!w.paused && (w.status==='running'||w.active)).map(w=>w.wid);
      await decide('drain',{});
      const deadline=performance.now()+timeout;
      while(true) {
        const view=statusView(home);
        // A paused flag alone is not quiescence: live commands/agents/asks and
        // unreleased provider slots may still run after drain was accepted.
        const busy=view.workflows.some(w=>w.calls.some(c=>c.phase==='running'||(c.phase==='asking'&&!c.hibernated)||c.pid));
        const slots=readerLedger(home).state.state.held.size;
        if(!busy && slots===0 && view.workflows.every(w=>w.paused||!w.active&&w.status!=='running'))return;
        if(performance.now()>=deadline)throw new Error('Durable children did not quiesce; handoff refused, holds retained');
        await delay(25);
      }
    },
    async resume() {
      // Restore only holds created by this transaction, not prior user pauses.
      for(const wid of held)await decide('resume',{wid});
      held=[];
    }
  };
}

export function durablePolicy({workspace,phase,broker,approve}) {
  return async args=>{
    const action=args.action??'run';
    if(['status','agents'].includes(action)) {
      const allowed=action==='status'?['action','wid']:['action'];
      if(Object.keys(args).some(k=>!allowed.includes(k))||args.wid!==undefined&&(typeof args.wid!=='string'||!/^[A-Za-z0-9._:-]{1,124}$/.test(args.wid)))
        throw new Error('Bounded native workflow metadata only');
      return;
    }
    if(phase()!=='ordinary')throw new Error('Durable mutation held during residency transition/Hermes');
    if(action!=='run')throw new Error('Durable control is trusted-host only; model may propose a bounded run');
    const launch=structuredClone(args);
    if(Object.keys(launch).some(k=>!['action','request','command','timeoutMs','cwd','rerun','agent','task','tools','model','once','writer','context'].includes(k)))
      throw new Error('Unsupported delegation shape; no scripts, gates, env injection or implicit child permission');
    if(!launch.request || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,123}$/.test(launch.request))throw new Error('Durable run needs stable request id');
    if(launch.cwd!==workspace || !Number.isFinite(launch.timeoutMs)||launch.timeoutMs<=0||launch.timeoutMs>120000 || launch.rerun!==undefined&&launch.rerun!==false)
      throw new Error('Explicit workspace, bounded duration and no uncertain replay required');
    if(launch.command!==undefined) {
      if(['agent','task','tools','model','once','writer','context'].some(k=>k in launch))throw new Error('Command and agent permissions cannot be mixed');
      if(!Array.isArray(launch.command)||!launch.command.length||launch.command.some(v=>typeof v!=='string')||launch.command.join('').length>8192)
        throw new Error('Bounded argv command required');
    } else if(launch.agent!=='delegate'||typeof launch.task!=='string'||!launch.task.trim()||launch.task.length>8000||
      !Array.isArray(launch.tools)||launch.tools.length||launch.model!=='hyprneuro-local/lfm-text'||launch.once!==true||launch.writer!==false||launch.context!=='fresh')
      throw new Error('Child must be explicit local-text, fresh, once, non-writer with NO inherited IO permissions');
    await broker('execute');
    if(await approve({title:'Allow Durable run?',detail:JSON.stringify({warning:'UNSANDBOXED HOST EXECUTION: cwd is NOT containment; may access host files, network and credentials. No sandbox or inherited authorization. Native Durable owns execution',args:launch})})!==true)
      throw new Error('Trusted delegation consent required');
    await broker('execute');
    if(phase()!=='ordinary')throw new Error('Durable mutation held after consent; owner transition began');
  };
}
