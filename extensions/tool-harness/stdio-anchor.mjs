// Fixed trusted process-group anchor, not an MCP server or command interface.
// Only the host's already validated argv/cwd/environment reach this helper.
import { spawn } from 'node:child_process';
import { closeSync,readFileSync } from 'node:fs';
const selfKill=()=>{
  const fields=readFileSync(`/proc/${process.pid}/stat`,'utf8').split(') ').at(-1).split(' ');
  if(Number(fields[2])===process.pid&&Number(fields[3])===process.pid)process.kill(-process.pid,'SIGKILL');
};
process.on('SIGTERM',()=>{}); // Remain pinned through the host's TERM grace.
process.on('SIGINT',()=>{});
process.on('disconnect',selfKill); // Host death must not leave a perpetual anchor.
process.on('uncaughtException',selfKill);
process.on('unhandledRejection',selfKill);
if(!process.connected)selfKill();
const [command,...args]=process.argv.slice(2);
const child=spawn(command,args,{stdio:'inherit',shell:false});
const notify=value=>{if(process.connected)process.send(value,error=>{if(error)selfKill();});else selfKill();};
child.once('error',()=>notify({type:'server_exit',failed:true}));
child.once('exit',()=>notify({type:'server_exit'}));
// Server (and its children) own their inherited copies; EOF does not depend on
// this anchor exiting. The private IPC channel carries lifecycle metadata only.
for(const fd of [0,1,2])closeSync(fd);
notify({type:'ready'});
