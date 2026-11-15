// MOCK controller metadata for SDK unit fixtures with MOCK broker RPC only.
// Not a capability, authenticated channel, real grant, or human proof. Genuine
// SDK/broker/channel coverage lives in test_trusted_consent_sdk.py.
import { randomUUID } from 'node:crypto';
export async function mockConsent(owner,event,allowed=true,{grant,release}={}) {
  if(event.type==='grant_release') {
    try {await release?.(event);owner.releaseDone(event.id,true);}
    catch {owner.releaseDone(event.id,false);}
    return;
  }
  if(event.type!=='consent')return;
  if(!event.audit)return owner.consent(event.id,allowed);
  try {
    if(allowed&&event.audit.kind!=='read_decision')await grant?.(event.audit);
    owner.consent(event.id,allowed,{consent_id:event.id,request:randomUUID(),body_hash:'a'.repeat(64),
      arguments_sha256:event.audit.arguments_sha256});
  }catch {owner.consent(event.id,false);} // no forged negative mutation receipt
}
