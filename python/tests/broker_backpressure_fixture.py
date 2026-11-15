"""Watchdog-owned private registered broker; undrained FIFO, no production data."""
import asyncio,fcntl,os,tempfile
from pathlib import Path
from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.trusted_consent import ConsentJournal,TrustedConsent
from hyprneuro.trusted_control import GrantControlServer,read_frame,send_frame
import hyprneuro.trusted_control as transport
async def main():
 with tempfile.TemporaryDirectory() as directory:
  root=Path(directory);store=SidecarStore(':memory:');journal=ConsentJournal(root/'audit.jsonl');core=TrustedConsent(store,journal)
  binding=dict(owner_root=str(root),owner_pid=os.getpid(),owner_start='fixture',owner_session='fixture',control_generation='fixture',descriptor_sha256='a'*64,task_id='test',app_id='fixture',workspace=str(root/'workspace'),read_policy_sha256='b'*64,ops=['read'])
  class Verifier:
   async def ui(self,pid):return {'pid':pid}
   def child(self,ui,pid,start):return {'pid':pid,'start':start}
   async def owner(self,path):return {'root':str(root)},{'pid':os.getpid()}
   def registration(self,*args):return binding
  handler=GrantControlServer(core,Verifier());server=await asyncio.start_unix_server(handler.handle,str(root/'broker.sock'))
  reader,writer=await asyncio.open_unix_connection(str(root/'broker.sock'))
  challenge=await read_frame(reader);await send_frame(writer,dict(op='launch',nonce=challenge['nonce'],child_pid=os.getpid(),child_start='fixture'));await read_frame(reader)
  await send_frame(writer,dict(op='owner_challenge',root=str(root)));await read_frame(reader)
  await send_frame(writer,dict(op='register',proof={}));reg=(await read_frame(reader))['registration'];record=core.registrations[reg]
  await send_frame(writer,dict(op='request',kind='grant_create',scope=dict(task_id='test',app_id='fixture',file_prefix=binding['workspace'],ops=['read']),generation='fixture',native_call_id='fixture',consent_id='fixture',arguments_sha256='c'*64));pending=await read_frame(reader)
  # Synthetic consent in PRIVATE in-memory DB only; exercise actual owned CAS release.
  core.decide(reg,**pending,allowed=True)
  assert core.slots and core.eligible('test',store.auth_list()[0])
  original_log=transport.diagnostic_rejection
  def checked_log(*args):
   assert not record.live and not core.eligible('test',store.auth_list()[0]),'Diagnostic I/O preceded invalidation'
   original_log(*args)
  if os.environ.get('CHECK_INVALIDATION_FIRST','1')=='1':transport.diagnostic_rejection=checked_log
  r,w=os.pipe2(os.O_NONBLOCK)
  try:
   while True:
    try:os.write(w,b'x'*4096)
    except BlockingIOError:break
   os.set_blocking(w,True);os.dup2(w,2);os.close(w);w=-1
   flags=fcntl.fcntl(2,fcntl.F_GETFL);assert not flags&os.O_NONBLOCK
   print('REGISTERED full-undrained stderr; rejection begins',flush=True)
   await send_frame(writer,{'op':'invalid'})
   assert 'error' in await read_frame(reader)
   for _ in range(100):
    if not handler.handlers:break
    await asyncio.sleep(.005)
   assert not handler.handlers and not record.live and not core.slots and not core.pending and all(row['status']=='revoked' for row in store.auth_list())
   assert not core.eligible('test',store.auth_list()[0])
   assert fcntl.fcntl(2,fcntl.F_GETFL)==flags,'Original shared file-description flags changed'
   print('PASS invalidated, owned cleanup empty, handler terminated WITHOUT draining stderr; original fd flags unchanged',flush=True)
  finally:
   os.close(r)
   if w>=0:os.close(w)
   writer.close();await writer.wait_closed();server.close();await server.wait_closed();journal.close();store.close()
asyncio.run(main())
