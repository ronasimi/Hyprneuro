// Private, inert descendant; identity is recorded only after TERM policy is set.
import { appendFileSync,readFileSync } from 'node:fs';
const [record,resistant]=process.argv.slice(2);
if(resistant==='yes')process.on('SIGTERM',()=>{});
const fields=readFileSync(`/proc/${process.pid}/stat`,'utf8').split(') ').at(-1).split(' ');
appendFileSync(record,JSON.stringify({child:process.pid,start:fields[19],group:Number(fields[2]),ready:true})+'\n');
process.send?.('ready');
setInterval(()=>{},1000);
