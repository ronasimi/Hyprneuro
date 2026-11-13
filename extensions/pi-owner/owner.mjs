// One long-lived actual Pi session. This is scheduling/UI IO, never a model/tool loop.
import { randomUUID } from 'node:crypto';

export class PiOwner {
  constructor({session,durable,command,checkpoint,route,prepare,cancelTransition,settleParent}) {
    Object.assign(this,{session,durable,command,checkpoint,route,prepare,cancelTransition,settleParent});
    this.phase='ordinary';this.queue=Promise.resolve();this.listeners=new Set();this.consents=new Map();this.closed=false;
  }
  emit(event){for(const listener of this.listeners)listener(event);}
  serial(work){
    if(this.closed||this.closing)return Promise.reject(new Error('Pi owner closed'));
    const result=this.queue.then(work);this.queue=result.catch(()=>{});return result;
  }
  async approve(request) {
    if(!this.listeners.size)throw new Error('No authenticated trusted control UI; denied');
    const id=randomUUID();let timer;
    try {
      return await new Promise((resolve,reject)=>{
        timer=setTimeout(()=>{this.consents.delete(id);reject(new Error('Trusted consent timed out'));},120000);
        this.consents.set(id,resolve);this.emit({type:'consent',id,title:request.title,detail:request.detail});
      });
    } finally {clearTimeout(timer);this.consents.delete(id);}
  }
  consent(id,allowed){
    if(typeof allowed!=='boolean'||!this.consents.has(id))throw new Error('No matching pending host consent');
    this.consents.get(id)(allowed);this.consents.delete(id);
  }
  disconnectControl(){for(const resolve of this.consents.values())resolve(false);this.consents.clear();}
  async status(){
    const observed=await this.command('status');
    return {...observed,...(['failed','transition'].includes(this.phase)?{state:this.phase}:{}),owner_phase:this.phase};
  }
  async transition(value) {
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
  chat({text,recommend=false},emit,signal) {
    if(typeof text!=='string'||!text.trim()||text.length>16000||typeof recommend!=='boolean')throw new Error('Bounded text/recommend required');
    return this.serial(async()=>{
      signal?.throwIfAborted();
      await this.prepare?.();
      signal?.throwIfAborted();
      if(['failed','transition'].includes(this.phase))throw new Error('Pi conversation admission closed');
      if(recommend&&this.phase==='ordinary') {
        let suggestion;
        try{suggestion=await this.route(text,signal);}catch{suggestion={route:'current',unavailable:true};}
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
      const unsub=this.session.subscribe(event=>{
        const update=event.assistantMessageEvent;
        if(event.type==='message_update'&&['text_delta','thinking_delta'].includes(update?.type)) {
          for(let i=0;i<update.delta.length;i+=4000)emit({type:'delta',channel:update.type==='text_delta'?'answer':'reasoning',text:update.delta.slice(i,i+4000)});
        } else if(event.type==='message_end'&&event.message?.role==='assistant') {
          const usage=Object.fromEntries(['input','output','cacheRead','cacheWrite','totalTokens'].filter(k=>
            Number.isFinite(event.message.usage?.[k])&&event.message.usage[k]>=0).map(k=>[k,event.message.usage[k]]));
          emit({type:'turn_end',stopReason:event.message.stopReason,usage});
        } else if(['agent_settled','tool_execution_start','tool_execution_end'].includes(event.type))
          emit({type:event.type,tool:event.toolName,isError:event.isError});
      });
      const abort=()=>{this.session.clearQueue?.();void this.session.abort();};signal?.addEventListener('abort',abort,{once:true});
      try {await this.session.prompt(text,{expandPromptTemplates:false,source:'rpc',streamingBehavior:'followUp'});await this.session.waitForIdle();signal?.throwIfAborted();await this.checkpoint(this.phase);return {settled:true};}
      catch(error){this.phase='failed';await this.checkpoint('chat-unknown');throw error;}
      finally{signal?.removeEventListener('abort',abort);unsub();}
    });
  }
  close(){
    return this.shutdown??=(async()=>{
      this.closing=true;this.disconnectControl();
      try {
        if(this.transitionKind==='on'){this.cancelOn=true;await this.cancelTransition?.().catch(()=>{});}
        this.session.clearQueue?.();await this.session.abort();await this.queue;
        if(this.phase==='hermes')await this._transition('off');
        await this.durable.quiesce();
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
