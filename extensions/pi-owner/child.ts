// Loaded ONLY by the dedicated Durable child's explicit launcher. No UI or lease
// capability is inherited. Default child has no file/shell permissions; ask/report remain
// native Durable protocol tools. All local inference requires the original owner.
import * as sdk from '@earendil-works/pi-coding-agent';
// Pi1.5's extension loader aliases the pi-ai root; subpath API imports do
// not resolve through that alias. Its official API factory avoids the alias bug.
import { lazyStream, openAICompletionsApi } from '@earendil-works/pi-ai';
import { readFile } from 'node:fs/promises';
import { nativeCalls } from '../tool-harness/native-calls.mjs';
import { childRead } from './read-bridge.mjs';
import { guardedStream, admit } from '../tool-harness/residency.mjs';

const { streamSimple } = openAICompletionsApi();

export default function(pi:sdk.ExtensionAPI) {
  const validated=nativeCalls(pi);
  const readRoot=process.env.HYPRNEURO_PI_CHILD_READ_DIR;
  const normalOnly=process.env.HYPRNEURO_PI_NORMAL_ONLY==='1';
  const textUrl=process.env.HYPRNEURO_PI_TEXT_URL??'http://127.0.0.1:8081/v1';
  if(!/^http:\/\/127\.0\.0\.1:\d+\/v1$/.test(textUrl))throw new Error('Pinned loopback text endpoint required');
  const stamp=process.env.HYPRNEURO_PI_OWNER_ID??'';
  async function acquire(role:string) {
    const [pid,start]=stamp.split(':');
    if(!/^[1-9][0-9]*$/.test(pid??'')||!start)throw new Error('No original Pi owner identity');
    const stat=await readFile(`/proc/${pid}/stat`,'utf8');
    if(stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s+/)[19]!==start)throw new Error('Pi owner ended; child inference closed');
    if(normalOnly){if(role!=='text')throw new Error('Normal-only child permits existing text only, no exclusive admission');return async()=>{};}
    return admit(role);
  }
  pi.registerProvider('hyprneuro-local',{api:'openai-completions',apiKey:'local-no-credential',
    streamSimple:(model,context,options)=>guardedStream({lazyStream,streamSimple},model,context,options,undefined,acquire),
    models:[{id:'lfm-text',name:'lfm-text',baseUrl:textUrl,contextWindow:131072,maxTokens:2048,
      reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
      compat:{supportsDeveloperRole:false,supportsStore:false,maxTokensField:'max_tokens'}}]});
  if(readRoot) {
    const definition=sdk.createReadToolDefinition(process.cwd());
    pi.registerTool({...definition,executionMode:'sequential',execute:async(id,args,signal)=>{
      if(!validated(id))throw new Error('Incomplete native child read');
      return childRead(readRoot,{call:process.env.DSA_CALL,exec:process.env.DSA_EXEC,tool_id:id,args},signal);
    }});
  }
  pi.on('tool_call',event=>{
    if(event.toolName==='read'&&readRoot&&validated(event.toolCallId))return;
    if(!['ask','report'].includes(event.toolName))return {block:true,reason:'No inherited child IO/delegation permissions',terminate:true};
  });
}
