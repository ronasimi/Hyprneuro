// One long-lived actual Pi session. This is scheduling/UI IO, never a model/tool loop.
import { randomUUID } from 'node:crypto';
import { boundedProof } from './cancellation.mjs';

export class PiOwner {
  constructor({session,durable,command,checkpoint,route,prepare,cancelTransition,settleParent,lifecycleUnavailable,detach,cancellation,cancellationIdle,callTimeoutMs=300000}) {
    Object.assign(this,{session,durable,command,checkpoint,route,prepare,cancelTransition,settleParent,lifecycleUnavailable,detach,cancellation,cancellationIdle,callTimeoutMs});
    this.phase='ordinary';this.queue=Promise.resolve();this.listeners=new Set();this.consents=new Map();this.grants=new Map();this.releases=new Map();this.closed=false;
  }
  emit(event){for(const listener of this.listeners)listener(event);}
  serial(work){
    if(this.closed||this.closing)return Promise.reject(new Error('Pi owner closed'));
    const result=this.queue.then(work);this.queue=result.catch(()=>{});return result;
  }
  async approve(request) {
    if(this.currentChat)this.currentChat.toolAdmission();
    if(request.audit) {
      if(!this.admission)throw new Error('Typed consent requires admitted request generation');
      request={...request,signal:request.signal?AbortSignal.any([request.signal,this.admission.signal]):this.admission.signal,
        audit:{...request.audit,generation:this.admission.generation}};
    }
    request.signal?.throwIfAborted();
    if(!this.listeners.size)throw Object.assign(new Error('No authenticated trusted control UI; denied'),{code:'HUMAN_DENIED'});
    const id=randomUUID();let timer,abort;
    try {
      return await new Promise((resolve,reject)=>{
        timer=setTimeout(()=>{this.consents.delete(id);reject(Object.assign(new Error('Trusted consent timed out'),request.audit?{}:{code:'HUMAN_DENIED'}));},120000);
        abort=()=>resolve(false);request.signal?.addEventListener('abort',abort,{once:true});
        this.consents.set(id,value=>{
          if(!request.audit)return resolve(typeof value==='boolean'?value:value.allowed);
          if(request.signal.aborted)return reject(request.signal.reason);
          const receipt=value?.receipt;
          if(!receipt||receipt.consent_id!==id||receipt.arguments_sha256!==request.audit.arguments_sha256||
            !/^[a-f0-9-]{36}$/.test(receipt.request)||!/^[a-f0-9]{64}$/.test(receipt.body_hash))
            return reject(new Error('Unproven typed consent outcome; no replay'));
          if(value.allowed!==true)return resolve(false);
          if(request.audit.kind!=='read_decision')this.grants.set(request.audit.scope.task_id,receipt.request);
          resolve(true);
        });
        this.emit({type:'consent',id,title:request.title,detail:request.detail,...(request.audit?{audit:request.audit}:{})});
      });
    } finally {clearTimeout(timer);request.signal?.removeEventListener('abort',abort);this.consents.delete(id);}
  }
  consent(id,allowed,receipt){
    if(typeof allowed!=='boolean'||!this.consents.has(id))throw new Error('No matching pending host consent');
    this.consents.get(id)({allowed,receipt});this.consents.delete(id);
  }
  async releaseGrants(){
    for(const [task,request] of this.grants){
      if(!this.listeners.size)throw new Error('Owned cleanup unproven without trusted control');
      const id=randomUUID();let timer;
      try{await new Promise((resolve,reject)=>{
        timer=setTimeout(()=>reject(new Error('Owned cleanup deadline; no replay')),5000);
        this.releases.set(id,{resolve,reject});this.emit({type:'grant_release',id,request});
      });this.grants.delete(task);}
      finally{clearTimeout(timer);this.releases.delete(id);}
    }
  }
  releaseDone(id,success){
    const pending=this.releases.get(id);
    if(!pending||typeof success!=='boolean')throw new Error('No exact owned cleanup request');
    this.releases.delete(id);
    if(success)pending.resolve();else pending.reject(new Error('Owned cleanup unknown'));
  }
  grantsInvalidated(){this.grants.clear();}
  disconnectControl(){for(const pending of this.releases.values())pending.reject(new Error('Control disconnected during cleanup'));this.releases.clear();for(const resolve of this.consents.values())resolve(false);this.consents.clear();}
  detachControl(){
    if(this.closing||this.closed)return this.shutdown??Promise.resolve();
    if(this.detaching)return this.detaching;
    this.disconnectControl();
    this.detaching=(async()=>{
      try {
        if(this.cancellationCleanup&&!this.cancellationCleanup.settled)await this.queue;
        if(this.cancellationCleanup&&!this.cancellationCleanup.settled)throw new Error('Cancellation cleanup pending; guard retained');
        this.session.clearQueue?.();await this.session.abort();await this.queue;
        await this.detach?.();await this.checkpoint(this.phase);
      } catch(error){this.phase='failed';await this.checkpoint('detach-unknown');throw error;}
      finally{this.detaching=undefined;}
    })();
    return this.detaching;
  }
  async status(){
    const observed=await this.command('status');
    return {...observed,...(['failed','transition'].includes(this.phase)?{state:this.phase}:{}),owner_phase:this.phase};
  }
  async transition(value) {
    if(this.lifecycleUnavailable)throw new Error(this.lifecycleUnavailable);
    if(!['on','off'].includes(value))throw new Error('Invalid transition');
    if(value==='off'&&this.phase==='transition'&&this.transitionKind==='on') {
      this.cancelOn=true;this.disconnectControl();
      // The queued on transaction verifies restoration; a helper's signal exit
      // alone is neither success nor permission to report off.
      await this.cancelTransition?.().catch(()=>{});
    }
    return this.serial(()=>this._transition(value));
  }
  async _transition(value) {
    if(this.lifecycleUnavailable)throw new Error(this.lifecycleUnavailable);
    if(this.phase==='failed')throw new Error('Owner outcome unknown; manual review required');
    const before=await this.command('status');
    if(value==='on'&&before.state==='on'&&this.phase!=='hermes')throw new Error('Another owner holds Hermes; never adopt its capability');
    if((value==='on'&&before.state==='on')||(value==='off'&&before.state==='off'))return this.status();
    this.transitionKind=value;this.cancelOn=false;
    this.phase='transition';await this.checkpoint('transition');let quiesced=false;
    try {
      // Settle already-started parent tool submissions BEFORE draining children.
      // This does not prove child quiescence: Durable's own API/ledger does that.
      await this.settleParent?.();
      if(value==='on'){await this.durable.quiesce();quiesced=true;}
      if(value==='on'&&this.cancelOn)throw new Error('Pending on cancelled by trusted off');
      await this.command(value);
      if(value==='off')await this.durable.resume();
      const state=await this.command('status');
      if(state.state!==value)throw new Error('Observed coordinator state is not settled');
      this.phase=state.state==='on'?'hermes':'ordinary';await this.checkpoint(this.phase);
      return this.status();
    } catch(error){
      const observed=await this.command('status').catch(()=>({state:'failed'}));
      if(quiesced&&observed.state==='off'){await this.durable.resume();this.phase='ordinary';}
      else this.phase='failed';
      await this.checkpoint(this.phase);throw error;
    } finally {this.transitionKind=undefined;}
  }
  chat({text,recommend=false},emit,signal,cancelRequest) {
    if(typeof text!=='string'||!text.trim()||text.length>16000||typeof recommend!=='boolean')throw new Error('Bounded text/recommend required');
    return this.serial(async()=>{
      const originalSignal=signal,deadline=new AbortController(),external=()=>deadline.abort(originalSignal.reason);
      signal?.addEventListener('abort',external,{once:true});if(signal?.aborted)external();
      signal=deadline.signal;
      const timer=setTimeout(()=>deadline.abort(new Error('Pi request deadline; inspect checkpoint, no replay')),this.callTimeoutMs);
      let nativeWork,cleanup,interrupted;
      const interruption=new Promise(resolve=>{interrupted=resolve;});
      const interrupt=()=>{
        this.currentChat?.seal();this.disconnectControl();interrupted();
        const record=cleanup={scope:this.currentChat,settled:false};this.cancellationCleanup=record;
        // Start the shared budget NOW, not after abort()/idle have returned.
        const aborting=Promise.resolve().then(()=>{this.session.clearQueue?.();return this.session.abort?.();});
        record.completion=(async()=>{
          // An early rejection must not hide another still-running SDK task.
          const results=await Promise.allSettled([aborting,nativeWork,
            Promise.resolve().then(()=>this.session.waitForIdle())]);
          const drained=record.scope?await record.scope.drained():false;
          return !results.some(result=>result.status==='rejected')&&drained;
        })();
        void record.completion.then(()=>{record.settled=true;},()=>{record.settled=true;});
        record.proof=boundedProof(record.completion,Math.min(2000,this.callTimeoutMs)).then(proven=>{record.proven=proven;return proven;});
      };
      signal.addEventListener('abort',interrupt,{once:true});
      this.admission={signal,generation:cancelRequest?.generation??randomUUID()};
      try {
      signal?.throwIfAborted();
      if(['failed','transition'].includes(this.phase))throw new Error('Pi conversation admission closed');
      await this.prepare?.();
      signal?.throwIfAborted();
      if(['failed','transition'].includes(this.phase))throw new Error('Pi conversation admission closed');
      if(recommend&&this.phase==='ordinary') {
        let suggestion;
        try{suggestion=this.lifecycleUnavailable?{route:'current',unavailable:true}:await this.route(text,signal);}catch{suggestion={route:'current',unavailable:true};}
        const valid=suggestion&&typeof suggestion==='object'&&!Array.isArray(suggestion)&&
          (suggestion.unavailable===undefined||typeof suggestion.unavailable==='boolean')&&Object.keys(suggestion).every(k=>['route','score','unavailable'].includes(k))&&
          ['current','hermes'].includes(suggestion.route)&&
          (suggestion.unavailable===true?suggestion.route==='current':typeof suggestion.score==='number'&&
            Number.isFinite(suggestion.score)&&suggestion.score>=0&&suggestion.score<=1&&
            (suggestion.route!=='hermes'||suggestion.score>=.75));
        const proposed=valid&&suggestion.route==='hermes';
        this.emit({type:'route_recommendation',route:proposed?'hermes':'current',available:!!valid&&!suggestion.unavailable,
          calibrated:false,...(valid&&!suggestion.unavailable?{score:suggestion.score}:{})});
        signal?.throwIfAborted();
        if(proposed) {
          try{await this._transition('on');} // always fresh trusted host consent, never D1 permission
          catch(error){
            if(this.phase!=='ordinary'||(await this.command('status')).state!=='off')throw error;
            this.emit({type:'route_dismissed',route:'current'}); // known rollback/denial: normal chat remains usable
          }
        }
      }
      signal?.throwIfAborted();
      await this.checkpoint('chat-intent');
      let scope;
      try{scope=this.cancellation?.();}catch(error){this.phase='failed';await this.checkpoint('chat-unknown');throw error;}
      this.currentChat=scope;
      if(cancelRequest)cancelRequest.fence=()=>scope?.seal();
      let nativeFailed=false,stopReason,nativeError,observing=true;
      const unsub=this.session.subscribe(event=>{
        if(!observing)return; // A retained late callback cannot resurrect a terminal request.
        const update=event.assistantMessageEvent;
        if(event.type==='message_update'&&['text_delta','thinking_delta'].includes(update?.type)) {
          for(let i=0;i<update.delta.length;i+=4000)emit({type:'delta',channel:update.type==='text_delta'?'answer':'reasoning',text:update.delta.slice(i,i+4000)});
        } else if(event.type==='message_end'&&event.message?.role==='assistant') {
          stopReason=event.message.stopReason;nativeError=event.message.errorMessage;
          if(['error','aborted'].includes(stopReason))nativeFailed=true;
          const usage=Object.fromEntries(['input','output','cacheRead','cacheWrite','totalTokens'].filter(k=>
            Number.isFinite(event.message.usage?.[k])&&event.message.usage[k]>=0).map(k=>[k,event.message.usage[k]]));
          emit({type:'turn_end',stopReason:event.message.stopReason,usage});
        } else if(['agent_settled','tool_execution_start','tool_execution_end'].includes(event.type))
          emit({type:event.type,tool:event.toolName,isError:event.isError});
      });
      try {
        // Checkpoint I/O can yield to cancel before this scope exists. Recheck
        // inside the unknown/finally guard, with no await before SDK admission.
        signal?.throwIfAborted();
        nativeWork=(async()=>{
          await this.session.prompt(text,{expandPromptTemplates:false,source:'rpc',streamingBehavior:'followUp'});
          await this.session.waitForIdle();
        })();
        await Promise.race([nativeWork,interruption.then(()=>{throw signal.reason;})]);signal?.throwIfAborted();
        // Pi resolves prompt() on native error/abort as well as success. Settled
        // is not successful: retain the unknown guard and never replay it.
        if(nativeFailed)throw new Error('Native Pi request failed; inspect checkpoint, no replay');
        await this.checkpoint(this.phase);signal.throwIfAborted();return {settled:true};}
      catch(error){
        // Only the same authenticated request's explicit cancel can qualify;
        // socket loss, deadline, HTTP errors, tools and unknown drains cannot.
        const proven=cleanup?await cleanup.proof:false;
        if(proven&&scope&&cancelRequest?.requested&&signal.reason===cancelRequest.reason&&
            !cancelRequest.disconnected()&&!this.closing&&this.phase==='ordinary'&&stopReason==='aborted'&&nativeError==='Request was aborted') {
          try {
            if(this.cancellationIdle()) {
              const outcome={kind:'cancelled-known',generation:cancelRequest.generation};
              await this.checkpoint(this.phase,outcome);
              if(cancelRequest.disconnected()||this.closing||this.detaching)throw new Error('Cancellation acknowledgement lost admission');
              return {settled:false,cancelled:true,outcome:'cancelled-known'};
            }
          }catch(proofError){error=new AggregateError([error,proofError],'Cancellation proof failed; inspect checkpoint, no replay');}
        }
        this.phase='failed';await this.checkpoint('chat-unknown');throw error;
      }
      finally{
        observing=false;unsub();scope?.seal();
        // Retain the sealed generation while SDK cleanup is unproven, even if
        // it settles later. Failed admission never reopens on late completion.
        if(!cleanup||!cleanup.scope||cleanup.proven===true)this.currentChat=undefined;
        if(cancelRequest)cancelRequest.fence=undefined;
      }
      } finally {this.admission=undefined;clearTimeout(timer);signal.removeEventListener('abort',interrupt);originalSignal?.removeEventListener('abort',external);}
    });
  }
  close(){
    return this.shutdown??=(async()=>{
      this.closing=true;this.disconnectControl();
      try {
        if(this.cancellationCleanup&&!this.cancellationCleanup.settled)await this.queue;
        if(this.cancellationCleanup&&!this.cancellationCleanup.settled)throw new Error('Cancellation cleanup pending; guard retained');
        await this.detaching;
        if(this.transitionKind==='on'){this.cancelOn=true;await this.cancelTransition?.().catch(()=>{});}
        this.session.clearQueue?.();await this.session.abort();await this.queue;
        if(this.phase==='hermes')await this._transition('off');
        await this.durable.quiesce();
        await this.detach?.();
        const safe=this.phase==='ordinary';await this.checkpoint(safe?'closed':'failed');this.closed=true;return safe;
      } catch(error) {
        this.phase='failed';
        try{await this.checkpoint('close-unknown');}
        catch(checkpointError){throw new AggregateError([error,checkpointError],'Owner shutdown and failure checkpoint failed; guard retained');}
        throw error;
      }
    })();
  }
}
