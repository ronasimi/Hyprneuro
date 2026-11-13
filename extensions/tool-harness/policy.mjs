import { connect } from 'node:net';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { open } from 'node:fs/promises';

export function sidecar(message, signal, socketPath = join(process.env.XDG_RUNTIME_DIR ?? '/nonexistent', 'hyprharness/sidecar.sock')) {
  return new Promise((resolve, reject) => {
    const sock = connect(socketPath);
    let data = Buffer.alloc(0), finished = false;
    const done = (error, result) => {
      if (finished) return;
      finished = true; signal?.removeEventListener('abort', abort); sock.destroy();
      error ? reject(error) : resolve(result);
    };
    const abort = () => done(new Error('Sidecar query cancelled'));
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort', abort, { once: true });
    sock.setTimeout(8000, () => done(new Error('Sidecar timeout')));
    sock.on('connect', () => sock.write(JSON.stringify(message) + '\n'));
    sock.on('error', () => done(new Error('Sidecar unavailable')));
    sock.on('end', () => done(new Error('Sidecar disconnected')));
    sock.on('data', chunk => {
      data = Buffer.concat([data, chunk]);
      if (data.length > 262144) return done(new Error('Sidecar reply exceeds bound'));
      const end = data.indexOf(10);
      if (end < 0) return;
      try {
        const packet = JSON.parse(data.subarray(0,end));
        packet.ok ? done(null, packet.result) : done(new Error('Sidecar rejected policy request'));
      } catch { done(new Error('Invalid sidecar response')); }
    });
  });
}

export const RECORD = 'hyprneuro.tool-call/1';
export class Outcomes {
  constructor(pi, ctx) {
    this.pi = pi; this.ctx = ctx; this.calls = new Map();
    // All branches: rewinding the conversation must not undo a real side effect.
    for (const e of ctx.sessionManager.getEntries())
      if (e.type === 'custom' && e.customType === RECORD) this.calls.set(e.data.id, e.data);
  }
  async record(value) {
    this.pi.appendEntry(RECORD, value);
    const path = this.ctx.sessionManager.getSessionFile();
    if (!path) throw new Error('Persistent Pi session required for tool execution');
    const file = await open(path, 'r+');
    try { await file.sync(); } finally { await file.close(); }
    this.calls.set(value.id, value);
  }
  key(name, args) {
    const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
      ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
    return createHash('sha256').update(JSON.stringify([name, canonical(args)])).digest('hex');
  }
  existing(id, key, sideEffect) {
    const old = this.calls.get(id);
    if (old) {
      if (old.key !== key) throw new Error('Tool ID conflict');
      if (old.status === 'completed') return old.result;
      throw new Error('Outcome unknown: manual review required; never replay');
    }
    if (sideEffect && [...this.calls.values()].some(c => c.key === key))
      throw new Error('Duplicate side effect blocked; manual review required');
  }
}

export async function checkBroker(rpc, taskId, appId, op, path, signal) {
  const result = await rpc({action:'auth_check', task_id:taskId, app_id:appId, op, path}, signal);
  if (result.allowed !== true) throw new Error('Permission broker denied: ' + result.reason);
}
