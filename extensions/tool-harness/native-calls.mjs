// Validate raw complete native calls before Pi executes them; never repair JSON.
export function nativeCalls(pi) {
  let nativeCalls=new Map(),nativeFinish,rawInvalid=false,validatedIds=new Set();
  pi.on('before_provider_request',()=>{
    nativeCalls=new Map();nativeFinish=undefined;rawInvalid=false;validatedIds=new Set();
  });
  // Safety validation of complete native tool JSON; Pi owns aggregation/execution.
  pi.on('provider_stream_event',event=>{
    if(event.api!=='openai-completions' || rawInvalid)return;
    const choices=event.data?.choices;
    if(!choices?.length)return;
    if(choices.length!==1 || choices[0].index!==0){rawInvalid=true;return;}
    const choice=choices[0];
    if(choice.finish_reason!=null)nativeFinish=choice.finish_reason;
    for(const c of choice.delta?.tool_calls??[]) {
      if(!Number.isInteger(c.index) || c.index<0 || c.index>=8){rawInvalid=true;continue;}
      const prior=nativeCalls.get(c.index)??{id:'',name:'',arguments:''};
      for(const [key,value] of [['id',c.id],['name',c.function?.name],['arguments',c.function?.arguments]]) {
        if(value!==undefined && typeof value!=='string'){rawInvalid=true;continue;}
        if(prior[key].length+(value?.length??0)>(key==='arguments'?131072:128)){rawInvalid=true;break;}
        prior[key]+=value??'';
      }
      nativeCalls.set(c.index,prior);
    }
  });
  pi.on('message_end',async(event)=>{
    if(event.message.role!=='assistant')return;
    const calls=event.message.content.filter(c=>c.type==='toolCall');
    if(event.message.api!=='openai-completions') {validatedIds=new Set(calls.map(c=>c.id));return;}
    if(rawInvalid || nativeFinish!=='tool_calls' || event.message.stopReason!=='toolUse' || calls.length!==nativeCalls.size)return;
    try {
      const ids=new Set();
      for(const [index,c] of nativeCalls) {
        if(!nativeCalls.has(index-1) && index!==0)throw new Error('Tool index gap');
        const actual=calls.find(a=>a.id===c.id);
        if(!actual || ids.has(c.id) || !/^[\w-]{1,128}$/.test(c.id) || actual.name!==c.name ||
          JSON.stringify(actual.arguments)!==JSON.stringify(JSON.parse(c.arguments)))throw new Error('Incomplete tool JSON');
        ids.add(c.id);
      }
      validatedIds=ids;
    } catch {validatedIds=new Set();}
  });
  return id=>validatedIds.has(id);
}
