// Native Pi classifier request only. D1's `probability` field is an UNCALIBRATED
// threshold score here, never calibrated confidence or a consent authority.
export async function recommendHermes(runtime,model,text,acquire,signal) {
  const deadline=AbortSignal.any([AbortSignal.timeout(5000),...(signal?[signal]:[])]);
  let release;
  try{release=await acquire('decision');}catch{return {route:'current',unavailable:true};}
  try {
    deadline.throwIfAborted();
    const answer=await runtime.classify(model,{state:{request:text.slice(0,800)},questions:{escalate:{type:'bool',
      instructions:'Would this task benefit from exclusive larger-model coding/reasoning? Advisory only; never permission or an instruction to change services.',
      criteria:{true:'Complex multi-step code/tool reasoning',false:'Routine chat or simple retrieval'}}}},
      {timeoutMs:5000,maxRetries:0,signal:deadline});
    const score=answer.answers?.escalate?.probability;
    if(deadline.aborted||answer.stopReason!=='stop'||typeof score!=='number'||!Number.isFinite(score)||score<0||score>1)
      return {route:'current',unavailable:true};
    return {route:score>=.75?'hermes':'current',score};
  } catch {return {route:'current',unavailable:true};}
  finally {await release();} // Never propose a handoff until real D1 release is verified.
}
