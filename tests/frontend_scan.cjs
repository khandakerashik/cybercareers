/* Scan controls and per-source DOM integration. Requires jsdom@26.
 * No real credentials, external API requests or rendered-browser claims.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const ROOT=path.resolve(__dirname,'..');
let assertions=0;
const eq=(actual,expected,message)=>{assert.equal(actual,expected,message);assertions++;};
const ok=(value,message)=>{assert.ok(value,message);assertions++;};
const PREVIOUS='2026-11-22T10:12:45Z';
const NOW='2026-11-22T11:30:00Z';
const TOKEN='synthetic-token-for-dom-test-only';
const run=(more={})=>({id:'700',attempt:1,status:'in_progress',active:true,conclusion:null,htmlUrl:'https://github.com/example/cybercareers/actions/runs/700',createdAt:'2026-11-22T11:29:00Z',...more});
const progress=(more={})=>({run_id:'synthetic-run',running:true,phase:'employers',started_at:'2026-11-22T11:29:00Z',updated_at:'2026-11-22T11:29:50Z',last_completed_at:PREVIOUS,total:5,checked:3,remaining:2,succeeded:1,failed:1,partial:0,skipped:1,new_jobs:2,active_sources:[{id:'a',name:'Bank Alpha'},{id:'b',name:'Bank Beta'}],sources:[
  {id:'a',name:'Bank Alpha',sector:'Banking',mode:'career-page',state:'running',started_at:'2026-11-22T11:29:40Z'},
  {id:'b',name:'Bank Beta',sector:'Banking',mode:'career-page',state:'running',started_at:'2026-11-22T11:29:45Z'},
  {id:'c',name:'Completed employer',state:'success',jobs_found:3,new_jobs:2,duration_seconds:4,finished_at:'2026-11-22T11:29:30Z'},
  {id:'d',name:'Cached feed',state:'skipped',message:'Publisher minimum interval',jobs_found:0,new_jobs:0},
  {id:'e',name:'<img src=x onerror=alert(1)>',state:'failed',message:'<script>unsafe()</script>',duration_seconds:2,jobs_found:0,new_jobs:0}
],...more});
const previous={running:false,phase:'completed',last_completed_at:PREVIOUS,finished_at:PREVIOUS,completion_status:'completed',total:1,checked:1,succeeded:1,sources:[],schedule:{enabled:true,interval_minutes:60,next_scheduled_at:'2026-11-22T12:12:00Z'}};

async function boot({local=false,scannerOptions={}}={}){
  const dom=new JSDOM(fs.readFileSync(path.join(ROOT,'index.html'),'utf8'),{url:'https://dashboard.example/careers/',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window;
  w.structuredClone=structuredClone;w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.scrollTo=()=>{};w.confirm=()=>true;
  w.errors=[];w.console={...console,error:(...args)=>w.errors.push(args.map(String).join(' ')),warn:()=>{}};
  let timerId=0;w.timers=new Map();w.intervals=[];
  w.setTimeout=(fn,ms)=>{const id=++timerId;w.timers.set(id,{fn,ms});return id;};w.clearTimeout=id=>w.timers.delete(id);
  w.setInterval=(fn,ms)=>{w.intervals.push({fn,ms});return ++timerId;};w.clearInterval=()=>{};
  w.testNow=NOW;w.userUid='account-a';w.logoutCalls=0;w.snapshotChecks=0;
  w.eval("const NativeDate=Date;globalThis.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[globalThis.testNow]));}static now(){return NativeDate.parse(globalThis.testNow);}};");
  const copy=value=>w.JSON.parse(JSON.stringify(value));
  const values={'jobs.json':{jobs:[]},'sources.json':[],'status.json':{last_completed_at:PREVIOUS},'progress.json':previous,'source_health.json':{sources:{}},'search_queries.json':[]};
  const transport={requests:[],report:{running:false,progress:previous},post:async()=>({status:202,body:{running:true,progress:progress()}}),statusFailure:false};
  w.fetch=async(url,options={})=>{
    transport.requests.push({url:String(url),options});const pathname=new URL(url,w.location.href).pathname;
    let status=200,body;
    if(pathname==='/api/health')body={ok:local,mode:local?'local':'static'};
    else if(pathname==='/api/refresh/status'){if(transport.statusFailure)throw new Error('Synthetic offline state');body=transport.readStatus?await transport.readStatus():transport.report;}
    else if(pathname==='/api/refresh'){const result=await transport.post();status=result.status;body=result.body;}
    else if(pathname.includes('/data/')){const name=pathname.split('/').at(-1);body=transport.readData?await transport.readData(name):values[name];}
    else{status=404;body={};}
    return {ok:status>=200&&status<300,status,json:async()=>copy(body)};
  };
  const scanner={connected:false,settings:null,connections:[],dispatches:0,disconnects:0,latest:null,report:{run:null,progressStatus:'pending'},requestResult:{state:'dispatched',run:run({status:'queued'})},...scannerOptions};
  scanner.isConnected=()=>scanner.connected;
  scanner.connect=async token=>{scanner.connections.push(token);if(scanner.connectWait)await scanner.connectWait;scanner.connected=true;return {repository:'example/cybercareers',workflow:'pages.yml',ref:'release/default',connected:true};};
  scanner.requestScan=async()=>{scanner.dispatches++;return copy(scanner.requestResult);};
  scanner.getRun=async id=>{if(scanner.error)throw scanner.error;return copy(scanner.readRun?await scanner.readRun(id):scanner.report);};
  scanner.latestRun=async()=>scanner.latest;
  scanner.disconnect=()=>{scanner.connected=false;scanner.disconnects++;};
  w.createScanner=settings=>{scanner.settings=settings;return scanner;};
  w.CC_CONFIG={github:{repository:'example/cybercareers',workflow:'pages.yml',ref:''}};
  w.fakeAuth={vaultMode:()=>!local,currentUser:()=>({uid:w.userUid,name:w.userUid}),restoreSession:async()=>true,loadJSON:async name=>copy(values[name]),refreshPublishedSession:async()=>{w.snapshotChecks++;return {changed:false};},logout:()=>{w.logoutCalls++;},decryptLiveProgress:async envelope=>copy(envelope.fixture)};
  const module=fs.readFileSync(path.join(ROOT,'applications.js'),'utf8').replace(/^export /gm,'');
  const app=fs.readFileSync(path.join(ROOT,'app.js'),'utf8').replace(/^import[^\n]+\n/gm,'').replace(/init\(\);\s*$/,'globalThis.ready=init();');
  w.eval('const auth=globalThis.fakeAuth;const createGitHubScanner=globalThis.createScanner;\n'+module+'\n'+app+'\nglobalThis.inspect={state,triggerScan,pollLocalRefresh,pollGitHubScan,connectGitHubScanner,disconnectGitHubScanner,closeScanConnection,ensureApplications,renderProgress,displayedProgress,getSettings:()=>githubScanSettings};');
  await w.ready;
  return {dom,w,values,transport,scanner};
}
const $=(w,id)=>w.document.getElementById(id);
const text=(w,id)=>$(w,id).textContent;
const input=(w,id,value,event='input')=>{const el=$(w,id);el.value=value;el.dispatchEvent(new w.Event(event,{bubbles:true}));};
const posts=transport=>transport.requests.filter(item=>item.options.method==='POST');
const storage=w=>JSON.stringify([Object.fromEntries(Object.entries(w.localStorage)),Object.fromEntries(Object.entries(w.sessionStorage))]);
const liveReport=(p=progress(),r=run())=>({run:r,progressStatus:'available',progressEnvelope:{generated_at:'2026-11-22T11:29:55Z',fixture:p}});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const pollTimers=(w,name)=>[...w.timers.entries()].filter(([,timer])=>timer.fn.name===name);
function firePoll(w,name){
  const entries=pollTimers(w,name);assert.equal(entries.length,1,`Expected one scheduled ${name}`);
  const [id,timer]=entries[0];w.timers.delete(id);return timer.fn();
}
const localStatusRequests=transport=>transport.requests.filter(item=>new URL(item.url,'https://dashboard.example').pathname==='/api/refresh/status').length;
const minuteSync=env=>env.w.intervals.find(timer=>timer.ms===60000).fn;
async function connectAndScan(env){await env.w.inspect.triggerScan();input(env.w,'scanToken',TOKEN);await env.w.inspect.connectGitHubScanner({preventDefault(){}});}

(async()=>{
  const local=await boot({local:true}),{w,transport}=local;
  eq(w.errors.length,0,'Local startup is clean');eq($(w,'scanNowButton').hidden,false,'Scan now is visible locally');
  eq(text(w,'scanConnectionState'),'Local collector connected');eq($(w,'scanConnectionButton').hidden,true);
  const lastCompleted=text(w,'scanLastCompleted');let release;
  transport.post=()=>new Promise(resolve=>{release=resolve;});
  const first=w.inspect.triggerScan();await w.inspect.triggerScan();
  eq(posts(transport).length,1,'Rapid repeated clicks send one local request');eq($(w,'scanNowButton').disabled,true);
  eq(posts(transport)[0].options.headers['X-CyberCareers-Action'],'refresh','Manual trigger uses the server action header');
  release({status:202,body:{running:true,progress:progress()}});await first;
  eq($(w,'sourceProgressPanel').open,true);eq(text(w,'progressPercent'),'60%');
  eq(text(w,'progressCurrent'),'Bank Alpha · Bank Beta','Parallel active sources are visible together');
  eq(w.document.querySelectorAll('.source-progress-row.running').length,2);
  eq(text(w,'scanLastCompleted'),lastCompleted,'Starting a scan preserves the previous completed timestamp');
  ok(text(w,'sourceProgressList').includes('3 / +2'),'Per-source found and new counts are shown');
  ok(text(w,'sourceProgressList').includes('Cached / deferred'));eq(w.document.querySelectorAll('#sourceProgressList img,#sourceProgressList script').length,0,'Source names and messages are escaped');
  const cached=w.document.querySelector('.source-progress-row.skipped');eq(cached.querySelector('.source-progress-duration').textContent,'—','Cached source has no fabricated duration');
  input(w,'sourceProgressSearch','Bank Beta');eq(w.document.querySelectorAll('.source-progress-row').length,1);
  input(w,'sourceProgressSearch','');input(w,'sourceProgressFilter','issues','change');eq(w.document.querySelectorAll('.source-progress-row').length,1);
  input(w,'sourceProgressFilter','all','change');
  transport.statusFailure=true;await w.inspect.pollLocalRefresh();
  eq($(w,'scanNowButton').disabled,true,'A status outage does not allow another scan');ok(text(w,'scanRunMessage').includes('temporarily unavailable'));
  eq(posts(transport).length,1,'Polling failure never reposts');transport.statusFailure=false;
  const finished=progress({running:false,phase:'completed',last_completed_at:'2026-11-22T11:30:00Z',finished_at:NOW,checked:5,remaining:0,active_sources:[],sources:[]});
  transport.report={running:false,progress:finished,last_result:{jobs_count:3,new_candidates:2}};local.values['progress.json']=finished;
  await w.inspect.pollLocalRefresh();eq($(w,'scanNowButton').disabled,false);ok(text(w,'scanLastCompleted').includes('17:30:00 BDT'),'A completed local scan advances the timestamp');

  const uncertain=await boot({local:true});uncertain.transport.post=async()=>{throw new Error('Response lost');};
  await uncertain.w.inspect.triggerScan();eq(uncertain.w.inspect.state.localRequestUnconfirmed,true);eq($(uncertain.w,'scanNowButton').disabled,true);
  uncertain.transport.report={running:true,progress:progress()};await uncertain.w.inspect.pollLocalRefresh();
  eq(uncertain.w.inspect.state.localRequestUnconfirmed,false,'Status confirms a scan after the POST response was lost');eq(posts(uncertain.transport).length,1);
  const rejected=await boot({local:true});rejected.transport.post=async()=>({status:403,body:{}});await rejected.w.inspect.triggerScan();
  eq($(rejected.w,'scanNowButton').disabled,false);ok(text(rejected.w,'scanRunMessage').includes('rejected'),'Definitive rejection is shown');

  // A minute synchronization must not start a second polling chain while the
  // current status request is in flight and its timer has already fired.
  const overlapping=await boot({local:true});await overlapping.w.inspect.triggerScan();
  const statusEntered=deferred(),statusReply=deferred();
  overlapping.transport.readStatus=()=>{statusEntered.resolve();return statusReply.promise;};
  const beforeStatusRequests=localStatusRequests(overlapping.transport);
  const activePoll=firePoll(overlapping.w,'pollLocalRefresh');await statusEntered.promise;
  const duplicatePoll=overlapping.w.inspect.pollLocalRefresh(),periodicPoll=minuteSync(overlapping)();
  eq(localStatusRequests(overlapping.transport)-beforeStatusRequests,1,'In-flight local poll excludes duplicate polls and minute synchronization');
  statusReply.resolve({running:true,progress:progress()});await Promise.all([activePoll,duplicatePoll,periodicPoll]);
  eq(pollTimers(overlapping.w,'pollLocalRefresh').length,1,'Overlapping callers leave one local polling timer');
  eq(pollTimers(overlapping.w,'pollLocalRefresh')[0][1].ms,2000,'The single active local polling loop retains its two-second interval');
  delete overlapping.transport.readStatus;overlapping.transport.report={running:true,progress:progress()};
  await firePoll(overlapping.w,'pollLocalRefresh');
  eq(localStatusRequests(overlapping.transport)-beforeStatusRequests,2,'The next timer performs exactly one further local status request');
  eq(pollTimers(overlapping.w,'pollLocalRefresh').length,1,'The next local poll does not accumulate timers');

  // A minute-sync response started while idle may arrive after a manual scan.
  const staleLocal=await boot({local:true}),idleEntered=deferred(),idleReply=deferred();
  staleLocal.transport.readStatus=()=>{idleEntered.resolve();return idleReply.promise;};
  const idleSync=minuteSync(staleLocal)();await idleEntered.promise;
  staleLocal.transport.post=async()=>({status:202,body:{running:true,progress:progress({run_id:'new-local-attempt'})}});
  await staleLocal.w.inspect.triggerScan();idleReply.resolve({running:false,progress:previous});await idleSync;
  eq(staleLocal.w.inspect.state.progress.run_id,'new-local-attempt','Late idle status cannot replace the manually started attempt');
  eq(staleLocal.w.inspect.state.localRefreshing,true);eq($(staleLocal.w,'scanNowButton').disabled,true,'Late idle status cannot enable a duplicate scan');
  eq(pollTimers(staleLocal.w,'pollLocalRefresh').length,1,'Ignoring an old idle response retains live local polling');

  // Early worker failures can leave the previous completed progress on disk.
  // The controller is authoritative for the new failed attempt after reload.
  const failedLocal=await boot({local:true});await failedLocal.w.inspect.triggerScan();
  const failedProgress=progress({run_id:'failed-local-attempt',running:false,phase:'error',completion_status:'failed',finished_at:NOW,active_sources:[],sources:[]});
  failedLocal.transport.report={running:false,progress:failedProgress,last_error:'Job collection failed. See the local terminal for details.'};
  await firePoll(failedLocal.w,'pollLocalRefresh');
  eq(failedLocal.values['progress.json'].phase,'completed','Regression fixture keeps the previous completed disk snapshot');
  eq(failedLocal.w.inspect.state.progress.run_id,'failed-local-attempt','Dataset reload preserves authoritative controller progress');
  eq(text(failedLocal.w,'scanResult'),'Interrupted / failed','A stale disk snapshot cannot turn a failed attempt into a completed attempt');
  eq(text(failedLocal.w,'progressPhase'),' · Last scan interrupted');
  eq($(failedLocal.w,'scanLastCompleted').getAttribute('datetime'),PREVIOUS,'A failed attempt retains the legitimate previous completion timestamp');
  eq($(failedLocal.w,'scanNowButton').disabled,false,'A terminal failed local attempt permits a new manual scan');

  // A new manual request may start while the terminal poll reloads job files.
  // Late files from that older attempt must not erase the new scan's progress.
  const reloadRace=await boot({local:true});await reloadRace.w.inspect.triggerScan();
  reloadRace.transport.report={running:false,progress:failedProgress};
  const dataEntered=deferred(),dataReply=deferred();
  reloadRace.transport.readData=name=>{if(name==='jobs.json'){dataEntered.resolve();return dataReply.promise;}return reloadRace.values[name];};
  const terminalReload=firePoll(reloadRace.w,'pollLocalRefresh');await dataEntered.promise;
  reloadRace.transport.post=async()=>({status:202,body:{running:true,progress:progress({run_id:'after-reload-started'})}});
  await reloadRace.w.inspect.triggerScan();dataReply.resolve(reloadRace.values['jobs.json']);await terminalReload;
  eq(reloadRace.w.inspect.state.progress.run_id,'after-reload-started','A delayed terminal dataset reload cannot overwrite a newer manual scan');
  eq($(reloadRace.w,'scanNowButton').disabled,true);eq(pollTimers(reloadRace.w,'pollLocalRefresh').length,1,'The new scan retains its status timer after discarding stale dataset files');

  const remote=await boot();eq($(remote.w,'scanNowButton').hidden,false,'Scan now is visible on Pages');
  await remote.w.inspect.triggerScan();eq($(remote.w,'scanConnectionDialog').open,true);eq($(remote.w,'scanRepository').readOnly,true);
  eq($(remote.w,'scanBranch').value,'','An omitted branch can be discovered');ok($(remote.w,'scanWorkflowLink').href.endsWith('/actions/workflows/pages.yml'));
  input(remote.w,'scanToken',TOKEN);const connecting=remote.w.inspect.connectGitHubScanner({preventDefault(){}});
  eq($(remote.w,'scanToken').value,'','Token input clears before the network operation completes');await connecting;
  eq(remote.scanner.dispatches,1);eq(remote.w.inspect.getSettings().ref,'release/default','The actual connected branch is retained');
  eq($(remote.w,'scanConnectionDialog').open,false);eq($(remote.w,'scanNowButton').disabled,true);eq(text(remote.w,'progressPercent'),'Preparing…','Queued workflow has no invented source percentage');
  ok(!storage(remote.w).includes(TOKEN),'GitHub token is absent from local and session storage');
  await remote.w.inspect.triggerScan();eq(remote.scanner.dispatches,1,'An active remote run is not dispatched again');
  remote.scanner.report=liveReport();await remote.w.inspect.pollGitHubScan();
  eq(text(remote.w,'progressCurrent'),'Bank Alpha · Bank Beta');eq(text(remote.w,'progressPercent'),'60%');
  ok(text(remote.w,'sourceProgressNote').includes('15 seconds'));ok(text(remote.w,'scanRunMessage').includes('encrypted live source updates'));
  eq(text(remote.w,'scanLastCompleted'),lastCompleted,'Live source reports do not advance the published completion time');
  remote.scanner.report={run:run(),progressStatus:'unavailable',message:'Checks read is unavailable.',retryAfter:120};await remote.w.inspect.pollGitHubScan();
  eq($(remote.w,'scanNowButton').disabled,true,'Missing Checks permission preserves valid workflow status');
  ok(text(remote.w,'sourceProgressNote').includes('unavailable with this connection'));
  eq([...remote.w.timers.values()].find(timer=>timer.fn.name==='pollGitHubScan').ms,120000,'Retry-After seconds are honored as milliseconds');
  remote.scanner.report=liveReport(progress(),run({status:'completed',conclusion:'cancelled',active:false}));await remote.w.inspect.pollGitHubScan();
  eq(remote.w.document.querySelectorAll('.source-progress-row.running').length,0,'An ended workflow cannot keep active source markers');
  eq(remote.w.document.querySelectorAll('.source-progress-row.interrupted').length,2);
  eq(text(remote.w,'progressPhase'),' · Incomplete run');eq(text(remote.w,'scanLastCompleted'),lastCompleted);
  ok(text(remote.w,'scanRunMessage').includes('cancelled'));eq($(remote.w,'scanNowButton').disabled,false);
  eq(remote.w.snapshotChecks,1,'Workflow completion checks for a newly published snapshot');
  remote.w.document.getElementById('logoutButton').click();eq(remote.scanner.connected,false);eq(remote.w.logoutCalls,1);eq(remote.w.inspect.state.remoteRun,null);
  ok(!storage(remote.w).includes(TOKEN));

  // A completed-run GET already in flight must not roll a newly accepted scan
  // back to the old run. Its busy flag must also release without losing polls.
  const remoteRace=await boot();await connectAndScan(remoteRace);
  const oldRun=run({status:'completed',active:false,conclusion:'success'});
  remoteRace.scanner.report={run:oldRun,progressStatus:'unavailable'};await firePoll(remoteRace.w,'pollGitHubScan');
  remoteRace.scanner.latest=oldRun;
  const runEntered=deferred(),runReply=deferred();
  remoteRace.scanner.readRun=()=>{runEntered.resolve();return runReply.promise;};
  const oldRunPoll=firePoll(remoteRace.w,'pollGitHubScan');await runEntered.promise;
  const freshRun=run({id:'701',status:'queued',htmlUrl:'https://github.com/example/cybercareers/actions/runs/701'});
  remoteRace.scanner.requestResult={state:'dispatched',run:freshRun};
  const disconnectsBefore=remoteRace.scanner.disconnects;
  await remoteRace.w.inspect.triggerScan();
  eq(remoteRace.w.inspect.state.remoteRun.id,'701','The new GitHub request is accepted before the older GET completes');
  await firePoll(remoteRace.w,'pollGitHubScan');
  runReply.resolve({run:oldRun,progressStatus:'unavailable'});await oldRunPoll;
  eq(remoteRace.w.inspect.state.remoteRun.id,'701','An older GitHub GET cannot replace the newly accepted run');
  eq($(remoteRace.w,'scanNowButton').disabled,true,'The stale completed run cannot re-enable the scan button');
  eq(text(remoteRace.w,'progressPercent'),'Preparing…','The new queued run retains its own progress state');
  eq(remoteRace.scanner.connected,true);eq(remoteRace.scanner.disconnects,disconnectsBefore,'Request epoch changes preserve the current GitHub connection');
  eq(pollTimers(remoteRace.w,'pollGitHubScan').length,1,'A timer firing during the old busy poll does not stop GitHub monitoring');
  eq(pollTimers(remoteRace.w,'pollGitHubScan')[0][1].ms,1500,'Discarding the stale poll schedules a prompt follow-up');
  delete remoteRace.scanner.readRun;
  remoteRace.scanner.report=liveReport(progress({run_id:'new-remote-attempt'}),{...freshRun,status:'in_progress'});
  await firePoll(remoteRace.w,'pollGitHubScan');
  eq(remoteRace.w.inspect.state.remoteProgress.run_id,'new-remote-attempt','The follow-up receives live details for the new run');
  eq(remoteRace.scanner.dispatches,2,'Polling races never dispatch an extra GitHub workflow');

  const unknown=await boot({scannerOptions:{requestResult:{state:'dispatched',run:run({status:'unknown',active:false})}}});
  await connectAndScan(unknown);eq(unknown.w.inspect.state.remotePending,true);eq($(unknown.w,'scanNowButton').disabled,true);
  ok(text(unknown.w,'scanResult').includes('Requesting'),'Confirmed ID with unknown status is not labeled finished');
  unknown.scanner.report={run:null,progressStatus:'pending'};await unknown.w.inspect.pollGitHubScan();
  eq($(unknown.w,'scanNowButton').disabled,true);eq(unknown.scanner.dispatches,1);
  unknown.w.inspect.disconnectGitHubScanner({quiet:true});eq(unknown.scanner.connected,false);eq($(unknown.w,'scanNowButton').disabled,false);

  let resolveConnect;const pending=await boot({scannerOptions:{connectWait:new Promise(resolve=>{resolveConnect=resolve;})}});
  await pending.w.inspect.triggerScan();input(pending.w,'scanToken',TOKEN);const delayed=pending.w.inspect.connectGitHubScanner({preventDefault(){}});
  pending.w.inspect.closeScanConnection();resolveConnect();await delayed;
  eq(pending.scanner.connected,false,'Closing the dialog invalidates a late connection response');eq(pending.scanner.dispatches,0,'Cancelled connection cannot start a scan');
  eq($(pending.w,'scanToken').value,'');

  const switched=await boot();await connectAndScan(switched);switched.w.userUid='account-b';switched.w.inspect.ensureApplications();
  eq(switched.scanner.connected,false,'Account switching clears scanner credentials');eq(switched.w.inspect.state.remoteRun,null);
  const hidden=await boot();await connectAndScan(hidden);hidden.w.dispatchEvent(new hidden.w.Event('pagehide'));
  eq(hidden.scanner.connected,false,'Leaving or caching the page clears the in-memory connection');
  for(const env of [local,uncertain,rejected,overlapping,staleLocal,failedLocal,reloadRace,remote,remoteRace,unknown,pending,switched,hidden]){eq(env.w.errors.length,0,'No frontend exceptions');env.dom.window.close();}
  console.log(`${assertions} manual scan and source progress DOM assertions passed.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
