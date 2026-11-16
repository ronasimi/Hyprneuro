"""Private descriptor replacement/loss AFTER actual nonce await, BEFORE MAC.
No keys/nonces are recorded; writer instrumentation only detects forbidden MAC.
"""
import asyncio
import json
from pathlib import Path

def install(root,case):
    root=Path(root);descriptor=root/'owner/owner.json';fired=False
    read=asyncio.StreamReader.readexactly;write=asyncio.StreamWriter.write
    async def readexactly(reader,n):
        nonlocal fired
        data=await read(reader,n)
        if n==32 and not fired:
            fired=True;before=descriptor.lstat();raw=descriptor.read_bytes()
            (root/'descriptor-before.json').write_bytes(raw)
            if case=='descriptor-replace':
                replacement=descriptor.with_name('replacement.json')
                replacement.write_bytes(raw);replacement.chmod(0o600);replacement.replace(descriptor)
                after=descriptor.lstat().st_ino
                if after==before.st_ino:raise AssertionError('Descriptor inode must differ')
            else:descriptor.unlink();after=None  # owned config, NOT consent/replay marker
            (root/'descriptor-fault.json').write_text(json.dumps(dict(case=case,before_inode=before.st_ino,after_inode=after,
                after_actual_nonce_await=True,before_control_mac=True,identical_bytes=case=='descriptor-replace')))
            (root/'fault-injected').write_text(case)
        return data
    def checked_write(writer,data):
        if fired and len(data)==33 and data[:1] in {b'C',b'T'}:
            (root/'FORBIDDEN-mac').write_text('BUG: MAC consumer acted after descriptor loss/replacement')
            raise AssertionError('Descriptor guard bypass')
        return write(writer,data)
    asyncio.StreamReader.readexactly=readexactly;asyncio.StreamWriter.write=checked_write
