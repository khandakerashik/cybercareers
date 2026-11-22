/* Dependency-free scanner + real WebCrypto regressions: node tests/github_scan.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {webcrypto} = require('node:crypto');
const {gzipSync} = require('node:zlib');
let assertions = 0;
const eq = (a,b,message) => {assert.deepEqual(a,b,message);assertions++;};
const check = (condition,message) => {assert.ok(condition,message);assertions++;};
const rejects = async (fn,code) => {await assert.rejects(fn,error=>error.code===code);assertions++;};
const moduleFrom = file => import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync(path.resolve(__dirname,'..',file),'utf8')).toString('base64'));
const TOKEN = 'github_pat_synthetic_fixture_only';
const REPOSITORY = 'Example/CyberCareers';
const SHA = 'a'.repeat(40);
const NOW = Date.parse('2026-11-22T16:00:00Z');
const json = (body,status=200,headers={}) => new Response(status===204?null:JSON.stringify(body),{status,headers:{'Content-Type':'application/json',...headers}});
const run = (id=100,overrides={}) => ({id,run_attempt:1,workflow_id:10,head_branch:'main',head_sha:SHA,
  status:'in_progress',conclusion:null,event:'workflow_dispatch',repository:{full_name:REPOSITORY},
  created_at:new Date(NOW).toISOString(),updated_at:new Date(NOW).toISOString(),...overrides});
const envelope = (id='100',attempt=1) => ({format:'CCLIVE1',repository:REPOSITORY,workflow_run_id:id,run_attempt:attempt,
  generated_at:new Date(NOW).toISOString(),iv:'unused',ct:'unused',users:{}});
const output = payload => 'CCLIVE1\n'+Buffer.from(JSON.stringify(payload)).toString('base64');
const progressCheck = (id=700,overrides={}) => ({id,name:'CyberCareers live collection',external_id:'CCLIVE1:100:1',head_sha:SHA,
  output:{text:output(envelope())},...overrides});

class FixtureAPI {
  constructor() {this.requests=[];this.runs=[];this.checks=[];this.dispatchMode='details';this.nextId=100;this.workflowState='active';this.fail=null;this.defaultBranch='main';}
  fetch = async (url,options) => {
    const parsed=new URL(url);this.requests.push({url,options});
    assert.equal(parsed.origin,'https://api.github.com');
    assert.equal(options.redirect,'error');assert.equal(options.credentials,'omit');
    assert.equal(options.headers.Authorization,'Bearer '+TOKEN);
    if(this.fail){const failure=this.fail;this.fail=null;return failure;}
    const route=parsed.pathname.replace('/repos/'+REPOSITORY,'');
    if(route==='')return json({full_name:REPOSITORY,default_branch:this.defaultBranch});
    if(route==='/actions/workflows/pages.yml')return json({id:10,state:this.workflowState});
    if(route==='/actions/workflows/pages.yml/runs'){
      let selected=this.runs.filter(item=>item.head_branch===parsed.searchParams.get('branch'));
      if(parsed.searchParams.has('status'))selected=selected.filter(item=>item.status===parsed.searchParams.get('status'));
      if(parsed.searchParams.has('event'))selected=selected.filter(item=>item.event===parsed.searchParams.get('event'));
      return json({workflow_runs:selected.slice(0,Number(parsed.searchParams.get('per_page')))});
    }
    if(route==='/actions/workflows/pages.yml/dispatches'){
      if(this.dispatchMode==='forbidden')return json({message:'private diagnostic '+TOKEN},403);
      if(this.dispatchMode==='redirect')return json({},302,{Location:'https://untrusted.example'});
      if(this.dispatchMode==='lost')throw new Error('Synthetic network failure that includes '+TOKEN);
      const created=run(this.nextId++,{head_branch:JSON.parse(options.body).ref});this.runs.unshift(created);
      if(this.dispatchMode==='accepted_lost')throw new Error('accepted, network failed');
      if(this.dispatchMode==='empty')return json(null,204);
      if(this.dispatchMode==='accepted_error')return json({},502);
      return json({workflow_run_id:created.id,run_url:'https://untrusted.example/must-not-follow',html_url:'https://untrusted.example/must-not-use'});
    }
    if(/^\/actions\/runs\/\d+$/.test(route)){
      if(this.failRun)return json({},503);
      return json(this.runs.find(item=>String(item.id)===route.split('/').at(-1))||{},this.runs.some(item=>String(item.id)===route.split('/').at(-1))?200:404);
    }
    if(route==='/commits/'+SHA+'/check-runs'){
      if(this.checkFailure)return json({},this.checkFailure);
      assert.equal(parsed.searchParams.get('filter'),'all');
      assert.equal(parsed.searchParams.get('check_name'),'CyberCareers live collection');
      const page=Number(parsed.searchParams.get('page'));
      return json({total_count:this.checks.length,check_runs:this.checks.slice((page-1)*100,page*100)});
    }
    if(/^\/check-runs\/\d+$/.test(route))return json(this.checks.find(item=>String(item.id)===route.split('/').at(-1))||{});
    throw new Error('Unexpected fixture request '+route);
  };
  get posts(){return this.requests.filter(item=>item.options.method==='POST');}
}

(async()=>{
  const {createGitHubScanner,GitHubScanError}=await moduleFrom('github-scan.js');
  check(new GitHubScanError('example','safe message') instanceof Error);
  const scannerFor=(api,extra={})=>createGitHubScanner({repository:REPOSITORY,workflow:'pages.yml',ref:'main',fetchImpl:api.fetch,now:()=>NOW,...extra});
  assert.throws(()=>createGitHubScanner({repository:'https://evil.example/a',ref:'main'}),error=>error.code==='invalid_configuration');assertions++;
  assert.throws(()=>createGitHubScanner({repository:REPOSITORY,workflow:'../other.yml',ref:'main'}),error=>error.code==='invalid_configuration');assertions++;
  const defaultAPI=new FixtureAPI();defaultAPI.defaultBranch='release/default';
  const defaults=scannerFor(defaultAPI,{ref:''});
  eq((await defaults.connect(TOKEN)).ref,'release/default','An omitted branch is discovered from validated repository metadata');
  eq((await defaults.requestScan()).state,'dispatched');
  eq(JSON.parse(defaultAPI.posts[0].options.body).ref,'release/default','Default branch discovery does not guess main');
  defaults.disconnect();defaultAPI.defaultBranch='';
  await rejects(()=>defaults.connect(TOKEN),'invalid_response');eq(defaults.isConnected(),false);

  const api=new FixtureAPI(),scanner=scannerFor(api);
  eq(scanner.isConnected(),false);
  await rejects(()=>scanner.requestScan(),'disconnected');
  await rejects(()=>scanner.connect('bad\r\nheader'),'invalid_token');
  eq(await scanner.connect(TOKEN),{repository:REPOSITORY,workflow:'pages.yml',ref:'main',connected:true});
  eq(scanner.isConnected(),true);eq(await scanner.latestRun(),null);
  const p1=scanner.requestScan(),p2=scanner.requestScan();eq(p1,p2,'Concurrent clicks share one dispatch operation');
  const dispatched=await p1;
  eq(dispatched.state,'dispatched');eq(dispatched.run.id,'100');eq(dispatched.run.active,true);
  eq(dispatched.run.htmlUrl,'https://github.com/'+REPOSITORY+'/actions/runs/100','Provider links are not trusted for navigation');
  eq(api.posts.length,1);
  eq(JSON.parse(api.posts[0].options.body),{ref:'main',inputs:{collect:true},return_run_details:true});
  check(api.requests.every(item=>!item.url.includes(TOKEN)),'Token never enters request URLs');
  check(!JSON.stringify(scanner).includes(TOKEN),'Token is not exposed by the scanner object');
  eq((await scanner.getRun()).progressStatus,'pending');
  api.checks=[progressCheck()];
  const live=await scanner.getRun();eq(live.progressStatus,'available');eq(live.progressEnvelope,envelope());
  const previousCount=api.requests.length;
  eq((await scanner.getRun()).progressStatus,'available');
  eq(api.requests.length-previousCount,2,'Progress polls reuse the exact matching check ID');
  check(api.requests.at(-1).url.endsWith('/check-runs/700'));
  eq((await scanner.requestScan()).state,'attached');eq(api.posts.length,1,'An active run is attached without another dispatch');
  api.runs[0].status='completed';api.runs[0].conclusion='failure';
  const completed=await scanner.getRun();eq(completed.run.active,false);eq(completed.run.conclusion,'failure');
  scanner.disconnect();eq(scanner.isConnected(),false);
  await rejects(()=>scanner.getRun(),'disconnected');

  for(const activeStatus of ['queued','waiting','pending','requested']){
    const activeAPI=new FixtureAPI();activeAPI.runs=[run(200,{status:activeStatus,event:'schedule'})];
    const activeScanner=scannerFor(activeAPI);await activeScanner.connect(TOKEN);
    const attached=await activeScanner.requestScan();eq(attached.state,'attached');eq(attached.run.status,activeStatus);eq(activeAPI.posts.length,0);
  }
  for(const mode of ['empty','accepted_lost','accepted_error']){
    const lostAPI=new FixtureAPI();lostAPI.dispatchMode=mode;
    const lostScanner=scannerFor(lostAPI);await lostScanner.connect(TOKEN);
    const accepted=await lostScanner.requestScan();eq(accepted.state,'dispatched');eq(accepted.run.id,'100');eq(lostAPI.posts.length,1);
  }
  const unconfirmedAPI=new FixtureAPI();unconfirmedAPI.dispatchMode='lost';
  const uncertain=scannerFor(unconfirmedAPI);await uncertain.connect(TOKEN);
  eq((await uncertain.requestScan()).state,'dispatch_unconfirmed');
  eq((await uncertain.requestScan()).state,'dispatch_unconfirmed');eq(unconfirmedAPI.posts.length,1,'Lost dispatch responses must never trigger automatic redispatch');
  eq((await uncertain.getRun()).run,null);
  unconfirmedAPI.runs=[run(300),run(301)];
  eq((await uncertain.requestScan()).state,'dispatch_unconfirmed','Ambiguous concurrent manual runs are not attributed to one request');
  unconfirmedAPI.runs=[run(300)];
  eq((await uncertain.getRun()).run.id,'300');eq(unconfirmedAPI.posts.length,1);

  const delayedAPI=new FixtureAPI();delayedAPI.failRun=true;
  const delayed=scannerFor(delayedAPI);await delayed.connect(TOKEN);
  const accepted=await delayed.requestScan();eq(accepted.state,'dispatched');eq(accepted.run.status,'unknown');eq(accepted.run.active,false);
  delayedAPI.failRun=false;eq((await delayed.getRun()).run.active,true);eq(delayedAPI.posts.length,1);

  const forbiddenAPI=new FixtureAPI();forbiddenAPI.dispatchMode='forbidden';
  const forbidden=scannerFor(forbiddenAPI);await forbidden.connect(TOKEN);
  await rejects(()=>forbidden.requestScan(),'forbidden');eq(forbiddenAPI.posts.length,1);
  const redirectsAPI=new FixtureAPI();redirectsAPI.dispatchMode='redirect';
  const redirects=scannerFor(redirectsAPI);await redirects.connect(TOKEN);
  eq((await redirects.requestScan()).state,'dispatch_unconfirmed');eq(redirectsAPI.posts.length,1);
  check(redirectsAPI.requests.every(item=>item.url.startsWith('https://api.github.com/')));

  const checkAPI=new FixtureAPI();checkAPI.runs=[run()];
  checkAPI.checks=Array.from({length:100},(_,i)=>progressCheck(i+1,{external_id:'CCLIVE1:99:1'}));
  checkAPI.checks.push(progressCheck());
  const checksScanner=scannerFor(checkAPI);await checksScanner.connect(TOKEN);
  eq((await checksScanner.getRun('100')).progressStatus,'available','Checks are paginated for repeated runs on the same SHA');
  checkAPI.checks[100]=progressCheck(700,{output:{text:output(envelope('99'))}});
  const mismatch=await checksScanner.getRun('100');eq(mismatch.progressStatus,'invalid');eq(mismatch.run.id,'100');eq(mismatch.progressEnvelope,null);
  checkAPI.runs[0].run_attempt=2;checkAPI.checks=[progressCheck()];
  eq((await checksScanner.getRun('100')).progressStatus,'pending','A previous attempt must not supply this attempt\'s progress');
  checkAPI.checkFailure=403;
  const denied=await checksScanner.getRun('100');eq(denied.progressStatus,'unavailable');eq(denied.run.active,true);
  checkAPI.checkFailure=null;checkAPI.checks=[progressCheck(800,{external_id:'CCLIVE1:100:2',output:{text:'CCLIVE1\n'+'A'.repeat(65000)}})];
  eq((await checksScanner.getRun('100')).progressStatus,'invalid','Oversized progress is rejected before decoding');
  checkAPI.runs[0].workflow_id=999;
  await rejects(()=>checksScanner.getRun('100'),'invalid_response');

  let time=NOW;const limitAPI=new FixtureAPI(),limited=scannerFor(limitAPI,{now:()=>time});await limited.connect(TOKEN);
  limitAPI.fail=json({},429,{'Retry-After':'30'});
  await rejects(()=>limited.latestRun(),'rate_limited');const beforeRetry=limitAPI.requests.length;
  await rejects(()=>limited.latestRun(),'rate_limited');eq(limitAPI.requests.length,beforeRetry,'Rate limit cooldown prevents repeated requests');
  time+=31000;eq(await limited.latestRun(),null);
  const disabledAPI=new FixtureAPI();disabledAPI.workflowState='disabled_manually';const disabled=scannerFor(disabledAPI);
  await rejects(()=>disabled.connect(TOKEN),'workflow_disabled');eq(disabled.isConnected(),false);
  const unreachable=createGitHubScanner({repository:REPOSITORY,ref:'main',fetchImpl:async()=>{throw new Error(TOKEN);}});
  try{await unreachable.connect(TOKEN);assert.fail('Expected rejection');}catch(error){eq(error.code,'network_error');check(!error.message.includes(TOKEN),'Transport error diagnostics cannot echo a token');}
  const timeout=createGitHubScanner({repository:REPOSITORY,ref:'main',timeoutMs:50,fetchImpl:async(_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))))});
  await rejects(()=>timeout.connect(TOKEN),'timeout');eq(timeout.isConnected(),false);

  // Disconnect while a response body is being read must not resurrect a session.
  let release;const waitBody=new Promise(resolve=>{release=resolve;});
  const cancelled=createGitHubScanner({repository:REPOSITORY,ref:'main',fetchImpl:async()=>({ok:true,status:200,headers:new Headers(),json:()=>waitBody})});
  const connecting=cancelled.connect(TOKEN);await Promise.resolve();cancelled.disconnect();release({id:10,state:'active'});
  await rejects(()=>connecting,'disconnected');eq(cancelled.isConnected(),false);

  // Real PBKDF2 + AES-GCM + gzip: live keys never replace the snapshot data key.
  class Storage{constructor(){this.values=new Map();}getItem(key){return this.values.get(key)||null;}setItem(key,value){this.values.set(key,String(value));}removeItem(key){this.values.delete(key);}}
  globalThis.crypto=webcrypto;globalThis.CC_CONFIG={mode:'vault',vault:'encrypted/'};
  globalThis.sessionStorage=new Storage();globalThis.localStorage=new Storage();
  const auth=await moduleFrom('auth.js');
  const uid=await auth.userId('fixture-user'),password='Synthetic password for regression only';
  const bytes=value=>Buffer.from(value).toString('base64');
  const random=length=>webcrypto.getRandomValues(new Uint8Array(length));
  const salt=random(16),iterations=600000;
  const base=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);
  const kek=new Uint8Array(await webcrypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt,iterations},base,256));
  const seal=async(key,plain,aad)=>{
    const iv=random(12),aes=await webcrypto.subtle.importKey('raw',key,'AES-GCM',false,['encrypt']);
    const ct=await webcrypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode(aad)},aes,plain);
    return {iv:bytes(iv),ct:bytes(ct)};
  };
  const mainKey=random(32),keyBox=await seal(kek,mainKey,'cc-dek:'+uid);
  const snapshot={jobs:[{id:'original-data-key'}]};const fileBox=await seal(mainKey,gzipSync(JSON.stringify(snapshot)),'cc-file:jobs.json');
  const ring={sealed_at:new Date(NOW).toISOString(),users:{[uid]:{salt:bytes(salt),iterations,...keyBox}},files:{'jobs.json':{path:'jobs.bin'}}};
  const blob=Buffer.concat([Buffer.from('CCV1'),Buffer.from(fileBox.iv,'base64'),Buffer.from(fileBox.ct,'base64')]);
  globalThis.fetch=async url=>String(url).includes('keyring.json')?json(ring):new Response(blob);
  await auth.login('fixture-user',password);eq(auth.currentUser().uid,uid);eq(await auth.loadJSON('jobs.json'),snapshot);
  const livePayload={running:true,status:'running',completed_sources:3,total_sources:10,sources:[{name:'Example',state:'running'}]};
  const makeLive=async(payload=livePayload,raw=null)=>{
    const liveKey=random(32),context=REPOSITORY+':100:1';
    const wrapped=await seal(kek,liveKey,'cc-live-key:'+context+':'+uid);
    const content=await seal(liveKey,gzipSync(raw??JSON.stringify(payload)),'cc-live:'+context);
    return {format:'CCLIVE1',repository:REPOSITORY,workflow_run_id:'100',run_attempt:1,generated_at:new Date(NOW).toISOString(),...content,users:{[uid]:wrapped}};
  };
  const liveEnvelope=await makeLive(),binding={repository:REPOSITORY,runId:'100',runAttempt:1};
  eq(await auth.decryptLiveProgress(liveEnvelope,binding),livePayload);
  eq(await auth.decryptLiveProgress(liveEnvelope,{...binding,repository:REPOSITORY.toLowerCase()}),livePayload,'GitHub repository casing does not change identity; AAD keeps producer casing');
  eq(await auth.loadJSON('jobs.json'),snapshot,'Live decryption never replaces the published snapshot data key');
  await rejects(()=>auth.decryptLiveProgress(liveEnvelope,{...binding,runId:'101'}),'invalid_progress');
  await rejects(()=>auth.decryptLiveProgress(liveEnvelope,{...binding,runAttempt:2}),'invalid_progress');
  await rejects(()=>auth.decryptLiveProgress(liveEnvelope,{...binding,repository:'Other/Repository'}),'invalid_progress');
  const wrongRecipient={...liveEnvelope,users:{['a'.repeat(64)]:liveEnvelope.users[uid]}};
  await rejects(()=>auth.decryptLiveProgress(wrongRecipient,binding),'progress_access');
  const tampered={...liveEnvelope,ct:'A'+liveEnvelope.ct.slice(1)};if(tampered.ct===liveEnvelope.ct)tampered.ct='B'+liveEnvelope.ct.slice(1);
  await rejects(()=>auth.decryptLiveProgress(tampered,binding),'progress_decryption');
  await rejects(()=>auth.decryptLiveProgress({...liveEnvelope,iv:'invalid!'},binding),'invalid_progress');
  const corruptedWrapper={...liveEnvelope,users:{[uid]:{...liveEnvelope.users[uid],ct:'AA=='}}};
  await rejects(()=>auth.decryptLiveProgress(corruptedWrapper,binding),'invalid_progress');
  const bomb=await makeLive(null,JSON.stringify({value:'x'.repeat(1024*1024)}));
  await rejects(()=>auth.decryptLiveProgress(bomb,binding),'invalid_progress');
  const notObject=await makeLive([]);
  await rejects(()=>auth.decryptLiveProgress(notObject,binding),'progress_decryption');
  sessionStorage.values.clear();localStorage.values.clear();
  eq(await auth.decryptLiveProgress(liveEnvelope,binding),livePayload,'The unlocked account supports live progress when browser storage is blocked');
  auth.logout(false);
  await rejects(()=>auth.decryptLiveProgress(liveEnvelope,binding),'locked');eq(auth.currentUser(),null);
  console.log(`GitHub scan and live encryption regressions passed (${assertions} assertions).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
