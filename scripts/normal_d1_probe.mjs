// One actual native Pi SDK classifier call; no AgentSession, owner or admission
// initializer. Parent-approved normal-stack API compatibility ONLY, not D1 consent.
import {readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
if(process.env.HYPRNEURO_NORMAL_PROBE!=='1'||process.env.HYPRNEURO_RESIDENCY_DIR||process.env.HYPRNEURO_PI_OWNER_ENABLE)
  throw Error('Explicit isolated normal-only probe authorization required; no owner/admission override');
const root=resolve(process.argv[2]),sdk=process.env.PI_HARNESS_SDK;
if(!sdk||!root.startsWith('/home/ron/Workspace/'))throw Error('Explicit reviewed SDK/evidence paths required');
const aiURL=new URL('../../pi-ai/dist/index.js',pathToFileURL(sdk));
const {classify}=await import(new URL('./api/typesafe-system-one.js',aiURL));
const model={id:'d1-omni-600m',provider:'hyprneuro-decision',api:'typesafe-system-one',name:'D1 advisory',baseUrl:'http://127.0.0.1:8083/v1',
  input:['text'],contextWindow:1024,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
async function resources(){
  const text=await readFile('/proc/meminfo','utf8');
  const result=Object.fromEntries([...text.matchAll(/^(MemTotal|MemAvailable|SwapFree):\s+(\d+)/gm)].map(m=>[m[1],Number(m[2])]));
  if(result.MemAvailable<1024*1024)throw Error('Less than1GiB available; refuse trial');
  return result;
}
const resourcesBefore=await resources();
let payload,raw,responseStatus;const started=performance.now();
const output=await classify(model,{state:{request:'Routine synthetic greeting; no actions or real user data.'},questions:{escalate:{type:'bool',
  instructions:'Would this task benefit from exclusive larger-model coding/reasoning? Advisory only; never permission or an instruction to change services.',
  criteria:{true:'Complex multi-step code/tool reasoning',false:'Routine chat or simple retrieval'}}}},
  {apiKey:'local-no-credential',maxRetries:0,timeoutMs:5000,signal:AbortSignal.timeout(6000),
   onPayload:value=>{payload=value;},onResponse:value=>{responseStatus=value.status;},
   fetch:async(url,options)=>{
     if(String(url)!=='http://127.0.0.1:8083/v1/systemone')throw Error('Unexpected destination');
     const response=await fetch(url,options),reader=response.body.getReader();let data='',bytes=0;
     const decoder=new TextDecoder();
     try{while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.length;if(bytes>65536)throw Error('Classifier response exceeds64KiB');data+=decoder.decode(value,{stream:true});}}
     finally{await reader.cancel();}
     data+=decoder.decode();raw=JSON.parse(data);
     return new Response(data,{status:response.status,headers:{'content-type':'application/json'}});
   }});
const score=output.answers?.escalate?.probability;
const result={scope:'actual SDK classifier -> existing D1, NO owner/admission/handoff/approval',sdk,
  seconds:(performance.now()-started)/1000,wirePayload:payload,responseStatus,
  rawAnswers:raw?.answers,rawUsage:raw?.usage,nativeOutput:output,
  validUncalibratedScore:output.stopReason==='stop'&&typeof score==='number'&&Number.isFinite(score)&&score>=0&&score<=1,
  proposedLifecycleAction:false,resourcesBefore,resourcesAfter:await resources()};
await writeFile(join(root,'native-d1.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify(result));
