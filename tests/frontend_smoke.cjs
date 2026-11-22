/** Optional DOM/crypto smoke tests. Install jsdom@26 for this developer check.
 * Does not fetch websites or launch a browser; use a browser for visual QA.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {webcrypto}=require('node:crypto');
const {gzipSync}=require('node:zlib');
const {JSDOM}=require('jsdom');
const ROOT=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(ROOT,'index.html'),'utf8');
const applicationCode=fs.readFileSync(path.join(ROOT,'applications.js'),'utf8').replace(/^export /gm,'');
function makeDom(){
 const dom=new JSDOM(html,{url:'https://dashboard.example/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window;
 w.structuredClone=structuredClone;w.scrollTo=()=>{};w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;
 w.Response=Response;w.Blob=Blob;w.DecompressionStream=DecompressionStream;
 Object.defineProperty(w,'crypto',{value:webcrypto});
 w.console={...console,error:(...args)=>{w.errors.push(args.map(String).join(' '));},warn:()=>{}};
 w.errors=[];w.intervals=[];w.setInterval=(fn,ms)=>{w.intervals.push({fn,ms});return w.intervals.length;};
 return dom;
}
async function frontend(){
 const dom=makeDom(),w=dom.window;
 const stamp='2026-11-22T08:30:15+00:00';
 const values={
  'jobs.json':JSON.parse(fs.readFileSync(path.join(ROOT,'tests/fixtures/seed_jobs.json'),'utf8')),
  'sources.json':JSON.parse(fs.readFileSync(path.join(ROOT,'data/sources.json'),'utf8')),
  'search_queries.json':JSON.parse(fs.readFileSync(path.join(ROOT,'data/search_queries.json'),'utf8')),
  'source_health.json':{sources:{}},
  'status.json':{updated_at:stamp,last_completed_at:stamp,completion_status:'completed_with_issues',source_health:[],source_coverage:{scheduled_employers:151,link_only_sources:36},detection:{prior_records_quarantined:3}},
  'progress.json':{running:false,phase:'completed',completion_status:'completed_with_issues',last_completed_at:stamp,finished_at:stamp,checked:160,total:160,succeeded:140,failed:10,partial:5,skipped:5,duration_seconds:240,schedule:{enabled:true,mode:'github_actions',interval_minutes:60,next_scheduled_at:'2026-11-22T09:12:00Z'}}
 };
 w.fetch=async filename=>{const name=new URL(filename,w.location.href).pathname.split('/').at(-1);return {ok:!!values[name],status:values[name]?200:404,json:async()=>w.JSON.parse(JSON.stringify(values[name]))};};
 const stub="const auth={vaultMode:()=>false,currentUser:()=>null};\n";
 let code=fs.readFileSync(path.join(ROOT,'app.js'),'utf8').replace(/^import[^\n]+\n/gm,'').replace(/init\(\);\s*$/,'globalThis.ready=init();');
 w.eval(stub+applicationCode+'\n'+code+'\nglobalThis.inspect={state,renderProgress,renderCompletion,renderAll};');
 await w.ready;
 assert.deepEqual(w.errors,[],'frontend startup errors');
 assert.equal(w.document.querySelector('#scanLastCompleted').textContent,'22 Nov 2026, 14:30:15 BDT');
 assert.equal(w.document.querySelector('#scanResult').textContent,'Completed with source issues');
 assert.match(w.document.querySelector('#coverageSummary').textContent,/36 directory/);
 assert.ok(w.document.querySelectorAll('.job-card').length);
 w.document.querySelector('[data-action=details]').click();
 assert.equal(w.document.querySelector('#jobDrawer').getAttribute('aria-hidden'),'false');
 w.inspect.state.progress={...w.inspect.state.progress,phase:'error',completion_status:'failed',finished_at:'2026-11-22T09:05:00Z'};
 w.inspect.renderProgress();
 assert.equal(w.document.querySelector('#scanLastCompleted').getAttribute('datetime'),stamp);
 assert.equal(w.document.querySelector('#scanResult').textContent,'Interrupted / failed');
 w.inspect.state.progress.schedule={mode:'local',enabled:false};w.inspect.renderCompletion();
 assert.equal(w.document.querySelector('#scanNextExpected').textContent,'Automatic checks disabled');
 assert.equal(w.document.querySelector('#sideEngine').textContent,'MANUAL / ON DEMAND');
 assert.deepEqual(w.errors,[]);
 dom.window.close();
 return 9;
}
async function freshLocalInstall(){
 const dom=makeDom(),w=dom.window;
 const values={
  'sources.json':JSON.parse(fs.readFileSync(path.join(ROOT,'data/sources.json'),'utf8')),
  'search_queries.json':[]
 };
 w.fetch=async filename=>{
  const pathname=new URL(filename,w.location.href).pathname;
  if(pathname==='/api/health')return {ok:true,json:async()=>({ok:true,mode:'local'})};
  if(pathname==='/api/refresh/status')return {ok:true,json:async()=>({running:false,progress:{running:false,phase:'idle',schedule:{mode:'local',enabled:true,interval_minutes:60}}})};
  const name=pathname.split('/').at(-1);return {ok:!!values[name],status:values[name]?200:404,json:async()=>w.JSON.parse(JSON.stringify(values[name]))};
 };
 const code=fs.readFileSync(path.join(ROOT,'app.js'),'utf8').replace(/^import[^\n]+\n/gm,'').replace(/init\(\);\s*$/,'globalThis.ready=init();');
 w.eval("const auth={vaultMode:()=>false,currentUser:()=>null};\n"+applicationCode+"\n"+code);
 await w.ready;
 assert.deepEqual(w.errors,[]);
 assert.equal(w.document.querySelector('#scanNowButton').hidden,false);
 assert.equal(w.document.querySelector('#scanLastCompleted').textContent,'No completed fetch recorded');
 dom.window.close();return 3;
}
const b64=bytes=>Buffer.from(bytes).toString('base64');
async function authCrypto(){
 const dom=makeDom(),w=dom.window;
 w.CC_CONFIG={mode:'vault',vault:'encrypted/'};
 const password='Synthetic test passphrase 2026!',username='test-user';
 const salt=webcrypto.getRandomValues(new Uint8Array(16));
 const base=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);
 const bits=await webcrypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt,iterations:600000},base,256);
 const uid=Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode('cybercareers:v1:'+username))).toString('hex');
 let generation=0,ring,blob;
 async function nextSnapshot(){
  generation++;
  const data=webcrypto.getRandomValues(new Uint8Array(32));
  const kek=await webcrypto.subtle.importKey('raw',bits,{name:'AES-GCM'},false,['encrypt']);
  const dataKey=await webcrypto.subtle.importKey('raw',data,{name:'AES-GCM'},false,['encrypt']);
  const iv=webcrypto.getRandomValues(new Uint8Array(12)),fiv=webcrypto.getRandomValues(new Uint8Array(12));
  const wrapped=await webcrypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('cc-dek:'+uid)},kek,data);
  const encrypted=await webcrypto.subtle.encrypt({name:'AES-GCM',iv:fiv,additionalData:new TextEncoder().encode('cc-file:jobs.json')},dataKey,gzipSync(JSON.stringify({generation})));
  blob=Buffer.concat([Buffer.from('CCV1'),Buffer.from(fiv),Buffer.from(encrypted)]);
  // Same seal time/fingerprint deliberately tests re-encryption within a second.
  ring={sealed_at:'2026-11-22T08:30:15Z',fingerprints:{'jobs.json':'test'},files:{'jobs.json':{path:'jobs.bin'}},users:{[uid]:{salt:b64(salt),iterations:600000,iv:b64(iv),ct:b64(wrapped)}}};
 }
 await nextSnapshot();
 w.fetch=async u=>({ok:true,json:async()=>structuredClone(ring),arrayBuffer:async()=>blob.buffer.slice(blob.byteOffset,blob.byteOffset+blob.byteLength)});
 const code=fs.readFileSync(path.join(ROOT,'auth.js'),'utf8').replace(/^export /gm,'');
 w.eval(code+'\nglobalThis.testAuth={login,loadJSON,refreshPublishedSession,requireLogin};');
 await w.testAuth.login(username,password);
 assert.equal((await w.testAuth.loadJSON('jobs.json')).generation,1);
 await nextSnapshot();
 assert.equal((await w.testAuth.refreshPublishedSession()).changed,true);
 assert.equal((await w.testAuth.loadJSON('jobs.json')).generation,2);
 assert.equal((await w.testAuth.refreshPublishedSession()).changed,false);
 w.document.querySelector('#authGate').classList.add('auth-gate-leave');
 const promise=w.testAuth.requireLogin();
 assert.equal(w.document.querySelector('#authGate').classList.contains('auth-gate-leave'),false);
 assert.equal(w.testAuth.requireLogin(),promise,'a second call reuses the active login gate');
 dom.window.close();
 return 6;
}
(async()=>{const count=await frontend()+await freshLocalInstall()+await authCrypto();console.log(`${count} frontend DOM and WebCrypto assertions passed (no visual browser rendering).`);})().catch(e=>{console.error(e);process.exitCode=1;});
