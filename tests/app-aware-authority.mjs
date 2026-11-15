// Real extension registration + disposable Unix RPC fixture, no model/service.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdtemp, mkdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:net';

const root = process.env.PI_NODE_MODULES;
if (!root) throw Error('Set PI_NODE_MODULES to the existing Pi release node_modules');
const require = createRequire(import.meta.url);
const {createJiti} = require(join(root, 'jiti'));
const jiti = createJiti(import.meta.url, {alias:{typebox:join(root,'typebox/build/index.mjs')}, fsCache:false});
const extension = await jiti.import('../extensions/app-aware.ts', {default:true});
const tools = [];
extension({registerTool: tool => tools.push(tool)});
const auth = tools.find(tool => tool.name === 'hyprneuro_auth');

test('model authorization is inspection-only even without schema validation', async () => {
  assert.deepEqual(auth.parameters.properties.action.anyOf.map(value => value.const), ['check', 'list']);
  assert.equal(auth.parameters.properties.approved, undefined);
  assert.equal(auth.parameters.properties.ops, undefined);
  for (const action of ['create', 'expand', 'revoke', 'auth_create', 'anything']) {
    await assert.rejects(auth.execute('model', {action, approved:true, ops:['desktop_control']}), /inspection only/);
  }
  await assert.rejects(auth.execute('model', {action:'list', approved:true}), /inspection only/);
});

test('inspection forwards only bounded policy queries over disposable RPC', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'hn-authority-'));
  const previous = process.env.XDG_RUNTIME_DIR;
  process.env.XDG_RUNTIME_DIR = dir;
  await mkdir(join(dir, 'hyprharness'));
  const received = [];
  const server = createServer(socket => socket.on('data', data => {
    const message = JSON.parse(data.toString());
    received.push(message);
    socket.end(JSON.stringify({ok:true, result:{allowed:false, reason:'no_authorization'}}) + '\n');
  }));
  try {
    await new Promise(resolve => server.listen(join(dir, 'hyprharness/sidecar.sock'), resolve));
    await auth.execute('check', {action:'check', task_id:'owner', op:'read', app_id:'kitty', path:'/fixture/exact.txt'});
    await auth.execute('list', {action:'list'});
    assert.deepEqual(received, [
      {action:'auth_check', task_id:'owner', op:'read', app_id:'kitty', path:'/fixture/exact.txt'},
      {action:'auth_list'},
    ]);
    await assert.rejects(auth.execute('grant', {action:'create', approved:true}), /inspection only/);
    assert.equal(received.length, 2);
  } finally {
    await new Promise(resolve => server.close(resolve));
    previous === undefined ? delete process.env.XDG_RUNTIME_DIR : process.env.XDG_RUNTIME_DIR = previous;
    await rm(dir, {recursive:true, force:true});
  }
});
