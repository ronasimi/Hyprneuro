// Linux-only IO adapter for Pi's standard tools. No replacement agent/tool loop.
import { constants as C } from 'node:fs';
import { open, mkdir, realpath, lstat } from 'node:fs/promises';
import { resolve, relative, isAbsolute, sep } from 'node:path';

export const MAX_FILE = 4 * 1024 * 1024;
export const MAX_WRITE = 1024 * 1024;

export class Workspace {
  static async create(root) {
    if (process.platform !== 'linux' || !isAbsolute(root) || root !== await realpath(root))
      throw new Error('Use a canonical absolute Linux workspace path');
    return new Workspace(root, await open(root, C.O_RDONLY | C.O_DIRECTORY | C.O_NOFOLLOW));
  }
  constructor(root, handle) { this.root = root; this.handle = handle; }
  async close() { await this.handle.close(); }
  target(path) {
    if (typeof path !== 'string' || !path || path.includes('\0') || path.split('/').includes('..'))
      throw new Error('Invalid workspace path');
    const full = resolve(this.root, path.startsWith('@') ? path.slice(1) : path);
    const rel = relative(this.root, full);
    if (!rel || rel === '..' || rel.startsWith('..' + sep) || isAbsolute(rel))
      throw new Error('Path outside workspace');
    if (rel.split(sep).some(n => n.startsWith('.env') || ['.git', '.ssh', '.gnupg', '.aws'].includes(n) || /\.(pem|key)$/.test(n)))
      throw new Error('Sensitive path excluded');
    return full;
  }
  async parent(path, create, operation) {
    const parts = relative(this.root, this.target(path)).split(sep);
    let parent = this.handle;
    const opened = [];
    try {
      for (const part of parts.slice(0, -1)) {
        const next = `/proc/self/fd/${parent.fd}/${part}`;
        if (create) await mkdir(next, { mode: 0o700 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
        parent = await open(next, C.O_RDONLY | C.O_DIRECTORY | C.O_NOFOLLOW);
        opened.push(parent);
      }
      return await operation(`/proc/self/fd/${parent.fd}/${parts.at(-1)}`);
    } finally { for (const h of opened.reverse()) await h.close(); }
  }
  async file(path, flags, operation, create = false) {
    return this.parent(path, create, async p => {
      const file = await open(p, flags | C.O_NOFOLLOW | C.O_NONBLOCK, 0o600);
      try {
        const st = await file.stat();
        if (!st.isFile() || st.nlink !== 1) throw new Error('Only regular single-link files allowed');
        return await operation(file, st);
      } finally { await file.close(); }
    });
  }
  async read(path) {
    return this.file(path, C.O_RDONLY, async (file, st) => {
      if (st.size > MAX_FILE) throw new Error('File exceeds 4 MiB input bound');
      const data = Buffer.alloc(Math.min(st.size + 1, MAX_FILE + 1));
      let used = 0;
      while (used < data.length) {
        const { bytesRead } = await file.read(data, used, data.length - used);
        if (!bytesRead) break;
        used += bytesRead;
      }
      if (used > MAX_FILE) throw new Error('File exceeds input bound');
      return data.subarray(0, used);
    });
  }
  async write(path, content) {
    if (Buffer.byteLength(content) > MAX_WRITE) throw new Error('Write exceeds 1 MiB');
    return this.file(path, C.O_WRONLY | C.O_CREAT, async file => {
      await file.truncate(0);
      await file.writeFile(content, 'utf8');
      await file.sync();
    }, true);
  }
  async access(path) { await this.file(path, C.O_RDONLY, async () => {}); }
  async mkdir(path) {
    // Pi write asks to create its parent before calling writeFile.
    await this.parent(resolve(path, '.hn-parent-check'), true, async () => {});
  }
}

export function exactEdits(buffer, edits) {
  const original = buffer.toString('utf8');
  if (!Array.isArray(edits) || !edits.length || edits.length > 64) throw new Error('Invalid edits');
  const ranges = edits.map(e => {
    if (!e || Object.keys(e).sort().join() !== 'newText,oldText' || typeof e.oldText !== 'string' || typeof e.newText !== 'string')
      throw new Error('Invalid edit object');
    const start = original.indexOf(e.oldText);
    if (!e.oldText || start < 0 || original.indexOf(e.oldText, start + 1) >= 0)
      throw new Error('oldText must exactly and uniquely match original');
    return [start, start + e.oldText.length];
  }).sort((a,b) => a[0]-b[0]);
  if (ranges.some((r,i) => i && ranges[i-1][1] > r[0])) throw new Error('Overlapping edits');
  return buffer;
}
