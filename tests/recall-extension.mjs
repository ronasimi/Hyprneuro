// Uses existing Pi runtime dependencies only; no Pi session or model is started.
import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:net';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const root = process.env.PI_NODE_MODULES;
if (!root) throw Error('Set PI_NODE_MODULES to the existing Pi release node_modules');
const {createJiti} = require(join(root, 'jiti'));
const jiti = createJiti(import.meta.url, {alias:{typebox:join(root,'typebox/build/index.mjs')}});
const ext = await jiti.import('../extensions/recall-browser.ts', {default:true});
const tools=[];
ext({registerTool: tool=>tools.push(tool)});
const search=tools.find(t=>t.name==='recall_search');
assert(search.parameters.properties.start_ms);
assert(search.parameters.properties.end_ms);
assert(search.parameters.properties.match);
const dir=mkdtempSync(join(tmpdir(),'hyprneuro-extension-'));
process.env.XDG_RUNTIME_DIR=dir;
mkdirSync(join(dir,'hyprharness'));
let received;
const server=createServer(socket=>socket.on('data', data=>{
  received=JSON.parse(data);
  socket.end(JSON.stringify({ok:true,result:[]})+'\n');
}));
try {
  await new Promise(resolve=>server.listen(join(dir,'hyprharness/sidecar.sock'),resolve));
  await search.execute('test', {period:'yesterday',start_ms:1000,end_ms:2000,order:'relevance',match:'phrase'}, undefined);
  assert.equal(received.start_ms,1000);
  assert.equal(received.end_ms,2000);
  assert.equal(received.order,'relevance');
  assert.equal(received.match,'phrase');
  console.log('PASS extension registration and exact-time RPC forwarding');
} finally {
  await new Promise(resolve=>server.close(resolve));
  rmSync(dir,{recursive:true,force:true});
}
