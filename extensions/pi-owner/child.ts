// Loaded ONLY by the dedicated Durable child's explicit launcher. No UI or lease
// capability is inherited. Child has no file/shell permissions; ask/report remain
// native Durable protocol tools. All local inference requires the original owner.
import * as sdk from '@earendil-works/pi-coding-agent';
// Pi1.5's extension loader aliases the pi-ai root; subpath API imports do
// not resolve through that alias. Its official API factory avoids the alias bug.
import { lazyStream, openAICompletionsApi } from '@earendil-works/pi-ai';
import { readFile } from 'node:fs/promises';
import { guardedStream, admit } from '../tool-harness/residency.mjs';

const { streamSimple } = openAICompletionsApi();

export default function(pi:sdk.ExtensionAPI) {
  const stamp=process.env.HYPRNEURO_PI_OWNER_ID??'';
  async function acquire(role:string) {
    const [pid,start]=stamp.split(':');
    if(!/^[1-9][0-9]*$/.test(pid??'')||!start)throw new Error('No original Pi owner identity');
    const stat=await readFile(`/proc/${pid}/stat`,'utf8');
    if(stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s+/)[19]!==start)throw new Error('Pi owner ended; child inference closed');
    return admit(role);
  }
  pi.registerProvider('hyprneuro-local',{api:'openai-completions',apiKey:'local-no-credential',
    streamSimple:(model,context,options)=>guardedStream({lazyStream,streamSimple},model,context,options,undefined,acquire),
    models:[{id:'lfm-text',name:'lfm-text',baseUrl:'http://127.0.0.1:8081/v1',contextWindow:131072,maxTokens:2048,
      reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
      compat:{supportsDeveloperRole:false,supportsStore:false,maxTokensField:'max_tokens'}}]});
  pi.on('tool_call',event=>{
    if(!['ask','report'].includes(event.toolName))return {block:true,reason:'No inherited child IO/delegation permissions',terminate:true};
  });
}
