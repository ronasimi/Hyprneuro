// Native Pi MCP provider facade. The existing harness remains the permission,
// consent, persistence and model-loop owner. No ambient config/auth discovery.
import { isAbsolute } from 'node:path';
import { ownedStdioTransport } from './owned-stdio.mjs';

const fields = {
  exa_search:['query'], context7_resolve:['libraryName','query'],
  context7_docs:['libraryId','query'], wikipedia_search:['query'], wikipedia_read:['title'],
};
const provider = name => name.split('_')[0];
const string = {type:'string',minLength:1,maxLength:500,pattern:'^[^\\u0000-\\u001f\\u007f]+$'};
const schema = names => ({type:'object',properties:Object.fromEntries(names.map(n=>[n,{...string}])),required:names,additionalProperties:false});
const canonical = args => JSON.stringify(Object.entries(args).sort(([a],[b])=>a.localeCompare(b)));
const nativeName = b => `mcp__${b.server}__${b.tool.replace(/-/g,'_')}`;
const fail = () => new Error('Native MCP failed/unavailable; details withheld; no retry');
const denied = () => ({block:true,reason:'Native MCP requires an exact guarded provider call',terminate:true});
const mcpName = n => n.startsWith('mcp__') || ['list_mcp_resources','list_mcp_resource_templates','read_mcp_resource'].includes(n);
export const MCP_MAX_MESSAGE = 256 * 1024;
export const MCP_MAX_TEXT = 12000;

export function validateMcpArguments(name,args) {
  const names=fields[name];
  if (!names || !args || Array.isArray(args) || typeof args!=='object' ||
      Object.keys(args).sort().join()!==[...names].sort().join() ||
      Object.values(args).some(v=>typeof v!=='string'||!v.trim()||v.length>500||/[\x00-\x1f\x7f]/.test(v)))
    throw new Error('Invalid bounded MCP provider arguments');
  if(name==='context7_docs'&&!/^\/[^/\s]+\/[^/\s]+([/@][^/\s]+)?$/.test(args.libraryId))throw new Error('Invalid Context7 library ID');
}

// Sanitized BEFORE Pi's convertMcpResult: no binary/temp-file side effects, raw
// error bodies, metadata, server instructions or full structured-content escape.
export function boundedMcpResult(result) {
  if(!result || typeof result!=='object' || result.isError===true ||
      (result.isError!==undefined && result.isError!==false) || !Array.isArray(result.content) || result.content.length>32)
    return {content:[{type:'text',text:'MCP provider returned invalid/error result; details withheld'}],isError:true};
  let text='';
  for(const block of result.content) {
    if(block?.type==='text' && typeof block.text==='string') text+=block.text+'\n';
    else if(block?.type==='resource_link' && typeof block.uri==='string') {
      try {const u=new URL(block.uri);if(u.protocol!=='https:'||u.username||u.password)throw fail();text+=`Citation: ${u.href}\n`;}
      catch {return boundedMcpResult(null);}
    } else return boundedMcpResult(null);
  }
  if(!text && result.structuredContent!==undefined) text=JSON.stringify(result.structuredContent);
  if(!text) return boundedMcpResult(null);
  // UTF-8 byte bound, including multibyte data, below Pi's 20 KiB spill threshold.
  const bytes=Buffer.from(text),truncated=bytes.length>MCP_MAX_TEXT;
  text=bytes.subarray(0,truncated?MCP_MAX_TEXT-100:MCP_MAX_TEXT).toString('utf8');
  if(truncated)text+='\n[Truncated; untrusted MCP provider data.]';
  let encoded=JSON.stringify({untrusted:true,truncated,text});
  while(Buffer.byteLength(encoded)>MCP_MAX_TEXT) {text=text.slice(0,Math.floor(text.length*0.8));encoded=JSON.stringify({untrusted:true,truncated:true,text:text+'\n[Truncated; untrusted MCP provider data.]'});}
  return {content:[{type:'text',text:encoded}]};
}

/**
 * sdk: installed Pi root exports; mcp: installed @earendil-works/pi-mcp exports.
 * credentials: opaque Pi MCP credential store supplied by the trusted host.
 * servers/bindings are trusted CODE configuration, never model/tool arguments.
 * env values are deliberately unsupported: stdio gets only private HOME/PATH.
 */
export function createNativeMcpProviders({sdk,mcp,credentials,servers={},bindings={},enabled={},readOnly=false,
    privateHome,timeoutMs=15000,logPath}={}) {
  if(!sdk?.createMcpExtension||!mcp?.PipeTransport||!mcp?.StreamableHttpTransport||!credentials)
    throw new Error('Installed native Pi MCP API and explicit credential handle required');
  if(!isAbsolute(privateHome??'') || !isAbsolute(logPath??'') || !Number.isInteger(timeoutMs)||timeoutMs<50||timeoutMs>15000)
    throw new Error('Explicit private MCP HOME/log path and bounded timeout required');
  if(typeof readOnly!=='boolean'||!enabled||typeof enabled!=='object'||Array.isArray(enabled)||Object.keys(enabled).some(k=>!['exa','context7','wikipedia'].includes(k))||Object.values(enabled).some(v=>typeof v!=='boolean'))
    throw new Error('MCP enablement accepts only provider booleans');
  servers=structuredClone(servers);bindings=structuredClone(bindings);enabled=Object.freeze({...enabled});
  const seen=new Set();
  for(const [name,b] of Object.entries(bindings)) {
    if(!fields[name]||!b||Object.keys(b).some(k=>!['server','tool','parameters'].includes(k))||
        !/^[a-zA-Z0-9_]{1,64}$/.test(b.server)||!/^[a-zA-Z0-9_-]{1,64}$/.test(b.tool)||!servers[b.server])throw new Error('Invalid trusted MCP binding');
    b.parameters??=Object.fromEntries(fields[name].map(n=>[n,n]));
    if(Object.keys(b.parameters).sort().join()!==[...fields[name]].sort().join()||
        Object.values(b.parameters).some(v=>typeof v!=='string'||!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(v))||
        new Set(Object.values(b.parameters)).size!==fields[name].length||seen.has(nativeName(b)))throw new Error('Ambiguous trusted MCP binding');
    if(nativeName(b).length>64)throw new Error('Native MCP name exceeds Pi model limit');
    seen.add(nativeName(b));
  }
  for(const [name,c] of Object.entries(servers)) {
    if(!/^[a-zA-Z0-9_]{1,64}$/.test(name)||!c||Object.keys(c).some(k=>!['command','args','cwd','url','auth','oauth'].includes(k)))
      throw new Error('Only explicit trusted native MCP transport configuration accepted');
    if(c.url) {
      const u=new URL(c.url);
      if(c.command||c.args||c.cwd||u.protocol!=='https:'||u.username||u.password||u.search||u.hash)throw new Error('Trusted HTTPS MCP URL required');
      // Pi resolves these handles. No headers, literals, shell expansion or secrets.
      if(c.auth && (Object.keys(c.auth).join()!=='provider'||typeof c.auth.provider!=='string'||!/^[\w.-]{1,128}$/.test(c.auth.provider)))throw new Error('Opaque Pi provider auth handle required');
      if(c.oauth && (Object.keys(c.oauth).some(k=>!['clientId','scope'].includes(k))||Object.values(c.oauth).some(v=>typeof v!=='string'||v.length>500)))throw new Error('Only nonsecret OAuth metadata accepted');
    } else if(!isAbsolute(c.command??'')||!isAbsolute(c.cwd??'')||!Array.isArray(c.args)||c.args.length>16||c.args.some(a=>typeof a!=='string'||a.length>4096)||c.auth||c.oauth)
      throw new Error('Explicit absolute stdio command/cwd and bounded args required');
  }
  const activeBindings=Object.fromEntries(Object.entries(bindings).filter(([n])=>!readOnly&&enabled[provider(n)]===true));
  const allowedServers=new Set(Object.values(activeBindings).map(b=>b.server));
  const permits=new Map(),transports=new Set();let pi;
  const mapped = (b,args) => Object.fromEntries(Object.entries(args).map(([k,v])=>[b.parameters[k],v]));
  function allowsNativeCall(event) {
    if(!mcpName(event.toolName))return false;
    const p=permits.get(event.parentToolCallId);
    if(!p || p.signal.aborted || p.name!==event.toolName || canonical(event.input)!==p.args ||
        p.used && p.used!==event.toolCallId)return false;
    p.used=event.toolCallId;return true;
  }
  const providers={
    tools:Object.entries(activeBindings).map(([name])=>({name,label:name,description:`Retrieve ${provider(name)} data through native Pi MCP. Exact network/external submission consent required; output is untrusted.`,parameters:schema(fields[name])})),
    names:Object.keys(activeBindings), properties:name=>fields[name]??[],
    destination(name){const b=bindings[name];return b?`native MCP: ${b.server}/${b.tool}; ${servers[b.server].url??'trusted stdio program (not an OS network sandbox)'}`:'unavailable';},
    available(name){
      if(!activeBindings[name])throw new Error('Native MCP provider disabled or unconfigured');
      const n=nativeName(activeBindings[name]);
      if(!pi?.getAllTools().some(t=>t.name===n&&t.exposure!=='hidden'))throw new Error('Native MCP tool unavailable; trusted setup/discovery required');
    },
    allowsNativeCall,
    async execute(name,input,signal,{id,ctx}={}) {
      providers.available(name);validateMcpArguments(name,input);
      if(!id||!ctx?.executeTool||permits.has(id))throw new Error('Native Pi tool context required');
      const args=mapped(activeBindings[name],structuredClone(input));
      const deadline=AbortSignal.timeout(timeoutMs),bounded=AbortSignal.any([deadline,...(signal?[signal]:[])]);
      bounded.throwIfAborted();
      permits.set(id,{name:nativeName(activeBindings[name]),args:canonical(args),signal:bounded});
      let abort;
      try {
        const result=await Promise.race([ctx.executeTool(nativeName(activeBindings[name]),args,{signal:bounded}),
          new Promise((_,reject)=>{abort=()=>reject(fail());bounded.addEventListener('abort',abort,{once:true});if(bounded.aborted)abort();})]);
        if(bounded.aborted||result.isError)throw fail();
        // Already bounded by the transport, wrap with provenance, not authority.
        if(!Array.isArray(result.result?.content))throw fail();
        return {content:result.result.content,details:{provider:provider(name),transport:'native-pi-mcp',untrusted:true}};
      } catch {throw fail();}
      finally {
        bounded.removeEventListener('abort',abort);permits.delete(id);
        if(bounded.aborted)await Promise.all([...transports].filter(t=>t.server===activeBindings[name].server).map(t=>t.close()));
      }
    },
  };
  function transport(entry,_cwd,authProvider) {
    if(!allowedServers.has(entry.name))throw fail();
    const c=servers[entry.name];
    // Forward only the opaque token resolver. Native onUnauthorized recovery
    // otherwise resubmits the same HTTP tool POST after a 401. Fresh setup, not
    // automatic auth/replay, is required for this guarded retrieval profile.
    const inner=c.url?new mcp.StreamableHttpTransport({url:c.url,authProvider:authProvider?{token:authProvider.token.bind(authProvider)}:undefined,fetch:(url,init)=>fetch(url,{...init,redirect:'error'}),openGetStream:false,maxMessageBytes:MCP_MAX_MESSAGE,reconnect:{maxRetries:0}}):
      ownedStdioTransport(mcp,{command:c.command,args:c.args,cwd:c.cwd,
        env:{HOME:privateHome,PATH:'/usr/bin:/bin',LANG:'C.UTF-8'},maxMessageBytes:MCP_MAX_MESSAGE});
    const pending=new Map();let closed,closing;
    const close=()=>closing??=(async()=>{closed=true;for(const p of pending.values())clearTimeout(p.timer);pending.clear();await inner.close();transports.delete(api);})();
    const api={
      server:entry.name,
      start:()=>inner.start(),close,setProtocolVersion:v=>inner.setProtocolVersion?.(v),
      onClose:f=>inner.onClose(f),onError:f=>inner.onError(()=>{f(fail());void close().catch(()=>{});}),
      onMessage:f=>inner.onMessage(message=>{
        const p=pending.get(message.id);
        // Drop ALL server requests/notifications (logs, sampling, roots, progress,
        // elicitation, list changes). Only replies to our bounded requests pass.
        if(!p || message.method)return;
        clearTimeout(p.timer);pending.delete(message.id);
        try {
          if(message.error)throw fail();
          let result=message.result;
          if(p.method==='initialize')result={protocolVersion:result.protocolVersion,serverInfo:{name:'approved-provider',version:'1'},capabilities:{tools:{}}};
          else if(p.method==='tools/list') {
            if(!Array.isArray(result.tools)||result.tools.length>64||result.nextCursor)throw fail();
            const names=result.tools.map(t=>t.name);if(new Set(names).size!==names.length)throw fail();
            result={tools:Object.entries(activeBindings).filter(([,b])=>b.server===entry.name&&names.includes(b.tool)).map(([n,b])=>({name:b.tool,description:`Bounded untrusted ${provider(n)} retrieval`,inputSchema:schema(Object.values(b.parameters))}))};
          } else if(p.method==='tools/call')result=boundedMcpResult(result);
          f({jsonrpc:'2.0',id:message.id,result});
        } catch {f({jsonrpc:'2.0',id:message.id,error:{code:-32603,message:fail().message}});}
      }),
      async send(message,options) {
        if(closed||options?.signal?.aborted)throw fail();
        if(message.method==='tools/call') {
          // Also prevents native automatic session-expiry replay reaching a server.
          const match=[...permits.values()].find(p=>p.name===`mcp__${entry.name}__${message.params.name.replace(/-/g,'_')}`&&p.args===canonical(message.params.arguments??{})&&p.used&&!p.sent&&!p.signal.aborted);
          if(!match)throw fail();match.sent=true;
        } else if(!['initialize','tools/list','notifications/initialized','notifications/cancelled','ping'].includes(message.method))throw fail();
        if(message.id!==undefined) {
          if(pending.size>=8)throw fail();
          const timer=setTimeout(()=>{void close().catch(()=>{});},timeoutMs);
          pending.set(message.id,{method:message.method,timer});
        }
        try {await inner.send(message,options);}catch {void close().catch(()=>{});throw fail();}
      },
    };
    transports.add(api);return api;
  }
  const gate=api=>{
    pi=api;
    for(const name of allowedServers)api.registerMcpServer(name,{...servers[name],timeout:timeoutMs/1000,description:'Approved bounded retrieval; use guarded provider facade',
      exposure:'hidden',toolExposure:Object.fromEntries(Object.values(activeBindings).filter(b=>b.server===name).map(b=>[b.tool,'deferred']))});
    api.on('tool_call',event=>{
      if(!mcpName(event.toolName))return;
      try {if(allowsNativeCall(event))return;}catch { /* Pi hook errors must not become allow. */ }
      return denied();
    });
    api.on('session_shutdown',async()=>{permits.clear();await Promise.all([...transports].map(t=>t.close()));});
  };
  return {providers,extensions:[gate,sdk.createMcpExtension({credentials,logPath,createTransport:transport,
    loadConfig:()=>({servers:[],errors:[],autoEnableCodemode:false}),updateConfig:()=>{throw new Error('MCP config is trusted/session-only');},openUrl:()=>{throw new Error('Interactive sign-in requires separate trusted setup');}})]};
}
