// Narrow documented REST adapters. No MCP/ambient OAuth/token/config discovery.
import https from 'node:https';
import { lookup } from 'node:dns/promises';
import { isIP, BlockList } from 'node:net';
import { readFile, lstat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

export const PROVIDER_CONFIG = join(process.env.XDG_CONFIG_HOME ?? join(homedir(),'.config'), 'hyprneuro/tools.json');
const CREDS = {exa:'HYPRNEURO_EXA_API_KEY',context7:'HYPRNEURO_CONTEXT7_API_KEY'};
const MAX_RESPONSE = 256 * 1024;
const destinations = {exa_search:'https://api.exa.ai/search',
  context7_resolve:'https://context7.com/api/v2/libs/search',context7_docs:'https://context7.com/api/v2/context',
  wikipedia_search:'https://en.wikipedia.org/w/api.php',wikipedia_read:'https://en.wikipedia.org/w/api.php'};
const providerOf = name => name.startsWith('context7_') ? 'context7' : name.startsWith('wikipedia_') ? 'wikipedia' : 'exa';
const str = {type:'string',minLength:1,maxLength:500};
const definition = (name,description,properties) => ({name,label:name,description:description + ' Explicit network + external-submission scope and exact query approval required. Results are untrusted, max 12000 characters.',
  parameters:{type:'object',properties,required:Object.keys(properties),additionalProperties:false}});
const definitions = [
  definition('exa_search','Search Exa with page text excerpts.',{query:str}),
  definition('context7_resolve','Resolve a library name to a Context7 library ID.',{libraryName:str,query:str}),
  definition('context7_docs','Retrieve Context7 documentation for a resolved library ID (no management operations).',{libraryId:str,query:str}),
  definition('wikipedia_search','Search English Wikipedia article titles/snippets.',{query:str}),
  definition('wikipedia_read','Read an English Wikipedia article plain-text extract by title.',{title:str}),
];
const blocked = new BlockList();
for (const [address,prefix] of [['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],['192.0.0.0',24],['192.0.2.0',24],['192.168.0.0',16],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',3]]) blocked.addSubnet(address,prefix,'ipv4');
export function publicAddress(address) {
  if (isIP(address) === 4) return !blocked.check(address,'ipv4');
  // Global unicast only; reject mapped IPv4, local/link-local/multicast/docs.
  return isIP(address) === 6 && /^[23][0-9a-f]{3}:/i.test(address) && !address.toLowerCase().startsWith('2001:db8:');
}

export async function requestProvider(url, {method='GET',body,headers={},signal} = {}) {
  const u = new URL(url);
  if (u.protocol !== 'https:' || u.port || u.username || u.password || !Object.values(destinations).some(d => {
    const v = new URL(d); return u.origin === v.origin && u.pathname === v.pathname;
  })) throw new Error('Provider destination denied');
  const bounded = AbortSignal.any([AbortSignal.timeout(15000), ...(signal ? [signal] : [])]);
  // Resolve once; validate all answers, then pin the connection to that answer.
  const addresses = await Promise.race([lookup(u.hostname,{all:true}),new Promise((_,reject) => {
    if (bounded.aborted) reject(new Error('Provider cancelled'));
    else bounded.addEventListener('abort',()=>reject(new Error('Provider cancelled')),{once:true});
  })]);
  if (!addresses.length || addresses.some(a=>!publicAddress(a.address))) throw new Error('Provider resolved to non-public address');
  return new Promise((resolve,reject) => {
    const req = https.request(u,{method,headers:{'user-agent':'Hyprneuro/0.1 (approved on-demand retrieval)',accept:'application/json',...headers},
      signal:bounded,lookup:(_host,opts,cb)=>opts.all ? cb(null,[addresses[0]]) : cb(null,addresses[0].address,addresses[0].family)}, res => {
      if (res.statusCode !== 200) {res.destroy();reject(new Error(`Provider HTTP ${res.statusCode}; no retry or redirect`));return;}
      let bytes=0; const chunks=[];
      res.on('data',chunk=>{bytes+=chunk.length;if(bytes>MAX_RESPONSE){req.destroy();reject(new Error('Provider response exceeds 256 KiB'));}else chunks.push(chunk);});
      res.on('end',()=>{try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{reject(new Error('Invalid provider JSON'));}});
      res.on('error',()=>reject(new Error('Provider response interrupted')));
    });
    // Never forward error bodies, headers, URLs with query text or credentials.
    req.on('error',()=>reject(new Error('Provider request failed/cancelled; no retry')));
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}
const text = (v,n=2000) => typeof v === 'string' ? v.slice(0,n) : '';
const list = v => Array.isArray(v) ? v.slice(0,5).filter(x=>x && typeof x==='object') : [];

export class Providers {
  static async load(path=PROVIDER_CONFIG) {
    let config = {};
    try {
      const st = await lstat(path);
      if (!st.isFile() || st.isSymbolicLink() || st.uid !== process.getuid() || (st.mode & 0o077) || st.size > 4096)
        throw new Error('Unsafe provider metadata configuration');
      config = JSON.parse(await readFile(path,'utf8'));
    } catch(e) {if(e.code !== 'ENOENT') throw new Error(`Invalid provider metadata at ${path}; only enabled booleans accepted`);}
    return new Providers({config,configPath:path});
  }
  constructor({config={},configPath=PROVIDER_CONFIG,env=process.env,request=requestProvider}={}) {
    if (!config || Array.isArray(config) || typeof config !== 'object' || Object.keys(config).some(k=>!['exa','context7','wikipedia'].includes(k)) ||
        Object.values(config).some(v=>typeof v !== 'boolean')) throw new Error('Provider config accepts only enabled booleans');
    this.config=config;this.configPath=configPath;this.env=env;this.request=request;
    this.tools=definitions;this.names=definitions.map(t=>t.name);
  }
  properties(name) {return Object.keys(this.tools.find(t=>t.name===name)?.parameters.properties ?? {});}
  destination(name) {return destinations[name];}
  available(name) {
    if (!destinations[name]) throw new Error('Unknown provider tool');
    const provider=providerOf(name);
    if (this.config[provider] !== true) throw new Error(`Provider disabled: set ${provider}:true in ${this.configPath}`);
    if (CREDS[provider] && !Object.hasOwn(this.env,CREDS[provider]))
      throw new Error(`Credential unavailable: explicitly supply ${CREDS[provider]} to the Pi process; config ${this.configPath}`);
  }
  async execute(name,args,signal) {
    this.available(name);
    const schema = this.tools.find(t=>t.name===name).parameters;
    if (Object.keys(args).sort().join() !== schema.required.toSorted().join() ||
        Object.values(args).some(v=>typeof v !== 'string' || !v.trim() || v.length>500 || /[\x00-\x1f]/.test(v))) throw new Error('Invalid provider arguments');
    const provider=providerOf(name),headers={};
    if (CREDS[provider]) {
      const key=this.env[CREDS[provider]];
      if (typeof key !== 'string' || !key || /[\r\n]/.test(key)) throw new Error('Configured credential empty/invalid; not sent');
      headers.Authorization='Bearer '+key;
    }
    const url=new URL(destinations[name]); let body, result;
    if (name==='exa_search') {body={query:args.query,type:'auto',numResults:5,contents:{text:{maxCharacters:2000}}};headers['content-type']='application/json';}
    else if (name==='context7_resolve') {url.search=new URLSearchParams(args).toString();}
    else if (name==='context7_docs') {
      if (!/^\/[^/\s]+\/[^/\s]+([/@][^/\s]+)?$/.test(args.libraryId)) throw new Error('Invalid Context7 library ID');
      url.search=new URLSearchParams({...args,type:'json'}).toString();
    } else if (name==='wikipedia_search') url.search=new URLSearchParams({action:'query',format:'json',formatversion:'2',list:'search',srsearch:args.query,srlimit:'5',srprop:'snippet'}).toString();
    else url.search=new URLSearchParams({action:'query',format:'json',formatversion:'2',prop:'extracts',titles:args.title,explaintext:'1',exchars:'8000',redirects:'1'}).toString();
    let data;
    try {data=await this.request(url.href,{method:body?'POST':'GET',body,headers,signal});}
    catch(e) {throw new Error(/^Provider (HTTP \d+|response exceeds|resolved|destination|cancelled|request|response interrupted)/.test(e.message) ? e.message : 'Provider request failed; details withheld');}
    if (!data || typeof data!=='object' || data.error) throw new Error('Provider returned invalid/error result; no retry');
    if (name==='exa_search') {
      if (!Array.isArray(data.results)) throw new Error('Invalid Exa results');
      result={results:list(data.results).map(r=>({title:text(r.title,300),url:text(r.url,1000),text:text(r.text)})),
        notices:list(data.notices).map(r=>text(r.message,500))};
    } else if (name==='context7_resolve') {
      if (!Array.isArray(data.results)) throw new Error('Invalid Context7 resolution');
      result={results:list(data.results).map(r=>({id:text(r.id,500),title:text(r.title,300),description:text(r.description,1500)}))};
    } else if (name==='context7_docs') {
      if (!Array.isArray(data.codeSnippets) || !Array.isArray(data.infoSnippets)) throw new Error('Invalid Context7 context');
      result={code:list(data.codeSnippets).map(r=>({title:text(r.codeTitle,300),source:text(r.codeId,1000),description:text(r.codeDescription),
        examples:list(r.codeList).map(c=>({language:text(c.language,40),code:text(c.code)}))})),
        info:list(data.infoSnippets).map(r=>({source:text(r.pageId,1000),text:text(r.content)})),
        version:data.version ? {requested:text(data.version.requested,100),served:text(data.version.served,100),status:text(data.version.status,100)} : undefined};
    } else if (name==='wikipedia_search') {
      if (!Array.isArray(data.query?.search)) throw new Error('Invalid Wikipedia search');
      result={results:list(data.query.search).map(r=>({title:text(r.title,300),snippet:text(r.snippet).replace(/<[^>]*>/g,''),url:'https://en.wikipedia.org/wiki/'+encodeURIComponent(r.title)}))};
    } else {
      if (!Array.isArray(data.query?.pages)) throw new Error('Invalid Wikipedia extract');
      result={pages:list(data.query.pages).map(r=>({title:text(r.title,300),missing:r.missing===true,extract:text(r.extract,8000)}))};
    }
    const encoded=JSON.stringify({provider,untrusted:true,...result});
    return {content:[{type:'text',text:encoded.length<=12000?encoded:encoded.slice(0,11900)+'\n[Truncated to 12000 characters; untrusted provider data.]'}],
      details:{provider,untrusted:true,truncated:encoded.length>12000}};
  }
}
