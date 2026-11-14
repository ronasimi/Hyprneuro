// Inspect only public process identity of our random private fixture workspace.
import { readFile,readlink,readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { processIdentity } from '../../extensions/tool-harness/owned-stdio.mjs';
const scripts=['../../extensions/tool-harness/stdio-anchor.mjs','./mcp-provider.mjs','./mcp-descendant.mjs'].map(p=>fileURLToPath(new URL(p,import.meta.url)));
export async function ownedProcesses(root) {
  const found=[];
  for(const pid of await readdir('/proc'))if(/^\d+$/.test(pid)) {
    const cwd=await readlink(`/proc/${pid}/cwd`).catch(()=> '');if(cwd!==root&&!cwd.startsWith(root+'/'))continue;
    const cmd=await readFile(`/proc/${pid}/cmdline`).catch(()=>Buffer.alloc(0));
    if(!scripts.some(p=>cmd.includes(Buffer.from(p))))continue;
    const info=processIdentity(Number(pid));if(info&&!['Z','X'].includes(info.state))found.push(info);
  }
  return found;
}
