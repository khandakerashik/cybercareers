/* Browser-DOM regression checks for Archived Jobs and Applied Jobs.
 * Requires jsdom@26; no websites, accounts or browser rendering are used.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const ROOT=path.resolve(__dirname,'..');
let checks=0;
const eq=(a,b,message)=>{assert.equal(a,b,message);checks++;};
const ok=(value,message)=>{assert.ok(value,message);checks++;};
const listing=(id,deadline,more={})=>({id,title:'SOC Analyst '+id,company:'Example Bank PLC',company_sector:'Banking',category:'SOC & Threat Detection',region:'Bangladesh',location:'Dhaka',workplace:'On-site',employment_type:'Full-time',source:'Official employer',source_url:`https://careers.example/jobs/${id}`,apply_url:`https://careers.example/jobs/${id}`,deadline,posted_at:'2026-11-01',vacancy_status:'unverified',description:'A genuine cybersecurity position.',skills:['SIEM'],...more});

async function boot({saved={},uid='account-a',jobs}={}){
  const dom=new JSDOM(fs.readFileSync(path.join(ROOT,'index.html'),'utf8'),{url:'https://dashboard.example/careers/',runScripts:'outside-only',pretendToBeVisual:true});
  const w=dom.window;
  w.structuredClone=structuredClone;w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.scrollTo=()=>{};w.confirm=()=>true;
  w.errors=[];w.console={...console,error:(...args)=>w.errors.push(args.map(String).join(' ')),warn:()=>{}};
  w.intervals=[];w.setInterval=(fn,ms)=>{w.intervals.push({fn,ms});return w.intervals.length;};
  w.userUid=uid;
  w.eval("globalThis.testNow='2026-11-22T11:00:00Z';const NativeDate=Date;globalThis.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[globalThis.testNow]));}static now(){return NativeDate.parse(globalThis.testNow);}};");
  for(const [key,value] of Object.entries(saved))w.localStorage.setItem(key,value);
  const values={'jobs.json':{jobs:jobs||[listing('yesterday','2026-11-21'),listing('today','2026-11-22'),listing('future','2026-12-05'),listing('old-undated','',{posted_at:'2023-01-01',vacancy_status:'older_unverified'}),listing('source-closed','2026-12-05',{vacancy_status:'closed'}),listing('global-expired','2026-11-18',{region:'International'}),listing('invalid-date','2026-02-30')]},'sources.json':[],'status.json':{},'progress.json':{},'source_health.json':{sources:{}},'search_queries.json':[]};
  const read=name=>w.JSON.parse(JSON.stringify(values[name]));
  w.fakeAuth={vaultMode:()=>true,currentUser:()=>({uid:w.userUid,name:w.userUid}),restoreSession:async()=>true,loadJSON:async name=>read(name),refreshPublishedSession:async()=>({changed:false}),logout:()=>{}};
  w.fetch=async()=>({ok:false,status:404});
  const module=fs.readFileSync(path.join(ROOT,'applications.js'),'utf8').replace(/^export /gm,'');
  const app=fs.readFileSync(path.join(ROOT,'app.js'),'utf8').replace(/^import[^\n]+\n/gm,'').replace(/init\(\);\s*$/,'globalThis.ready=init();');
  w.eval('const auth=globalThis.fakeAuth;\n'+module+'\n'+app+'\nglobalThis.inspect={state,renderAll,renderJobViews,ensureApplications,refreshDeadlineViews,route,applicationsCsv,resolveJob,jobIsOpen,getStore:()=>applicationStore};');
  await w.ready;
  return {dom,w,values};
}
const input=(w,id,value)=>{const el=w.document.getElementById(id);el.value=value;el.dispatchEvent(new w.Event('input',{bubbles:true}));};
const click=(w,selector)=>{const el=w.document.querySelector(selector);assert.ok(el,'Missing control: '+selector);el.click();};
const savedStorage=w=>Object.fromEntries(Array.from({length:w.localStorage.length},(_,i)=>{const key=w.localStorage.key(i);return [key,w.localStorage.getItem(key)];}));

(async()=>{
  const {dom,w}=await boot();
  eq(w.errors.length,0,'Startup must be clean');
  eq(w.document.querySelectorAll('#jobsGrid .job-card').length,4,'Active jobs exclude expired and explicitly closed jobs');
  eq(w.document.querySelectorAll('#archivedGrid .job-card').length,3,'Archive contains both regions and explicit closures');
  eq(w.document.querySelector('#navArchivedCount').textContent,'3');
  ok(w.document.querySelector('#jobsGrid [data-card="today"]'),'Deadline today stays active');
  ok(w.document.querySelector('#jobsGrid [data-card="old-undated"]'),'An old posting without a deadline is not archived');
  ok(w.document.querySelector('#jobsGrid [data-card="invalid-date"]'),'An invalid date is unknown, not an expired date');
  eq(w.inspect.jobIsOpen({deadline:'2026-11-21T20:00:00Z'}),true,'A timestamp is interpreted by its Bangladesh date');
  eq(w.inspect.jobIsOpen({deadline:'2026-11-21T17:59:59Z'}),false);
  eq(w.inspect.jobIsOpen({deadline:'2026-02-30T10:00:00Z'}),true,'An impossible timestamp date is not expiry evidence');
  eq(w.inspect.jobIsOpen({deadline:'2026-12-05',vacancy_status:'expired'}),true,'An extended deadline supersedes stale derived expiry');
  eq(w.document.getElementById('includeExpired'),null,'Expired jobs are in their own section');
  w.location.hash='archived';w.inspect.route();
  eq(w.document.getElementById('page-archived').hidden,false);
  input(w,'archiveSearch','global-expired');
  eq(w.document.querySelectorAll('#archivedGrid .job-card').length,1,'Archive search filters rendered cards');
  input(w,'archiveSearch','');
  click(w,'#jobsGrid [data-card="today"] [data-action="mark-applied"]');
  eq(w.inspect.getStore().list().length,1);
  eq(w.document.getElementById('navAppliedCount').textContent,'1');
  eq(w.document.getElementById('applicationNote').maxLength,1000);
  eq(w.document.querySelector('#jobsGrid [data-card="today"] .track-button').textContent.trim(),'Applied · Add note');
  eq(w.inspect.getStore().list()[0].applied_date,'2026-11-22');
  const note='Applied through the portal.\nFollow up with HR next week. <img src=x onerror=alert(1)>';
  input(w,'applicationNote',note);
  eq(w.document.getElementById('applicationNoteStatus').textContent,'Unsaved changes');
  w.inspect.renderJobViews();
  eq(w.document.getElementById('applicationNote').value,note,'Hourly rendering must retain an unsaved draft');
  click(w,'[data-action="save-note"]');
  eq(w.inspect.getStore().list()[0].note,note);
  ok(w.document.querySelector('#appliedGrid .application-note-preview').textContent.includes(note),'Note is visible as text');
  eq(w.document.querySelectorAll('#appliedGrid .application-note-preview img').length,0,'Notes cannot insert HTML');
  input(w,'appliedSearch','follow up');
  eq(w.document.querySelectorAll('#appliedGrid .application-card').length,1,'Notes are searchable');
  input(w,'appliedSearch','unmatched term');
  eq(w.document.querySelectorAll('#appliedGrid .application-card').length,0);
  input(w,'appliedSearch','');

  const record=w.inspect.getStore().list()[0],key=w.inspect.getStore().storageKey;
  w.testNow='2026-11-22T18:00:01Z';w.inspect.refreshDeadlineViews();
  eq(w.document.querySelector('#jobsGrid [data-card="today"]'),null,'BDT midnight moves a passed deadline out of active jobs');
  ok(w.document.querySelector('#archivedGrid [data-card="today"]'));
  eq(w.inspect.getStore().list()[0].note,note,'Expiry does not remove an application or its notes');
  ok(w.document.querySelector('#appliedGrid').textContent.includes('Deadline passed'));

  w.inspect.state.jobs=w.inspect.state.jobs.filter(j=>j.id!=='today');w.inspect.renderJobViews();
  eq(w.document.querySelectorAll('#appliedGrid .application-card').length,1,'Removed feed listings retain a personal application record');
  click(w,'#appliedGrid [data-action="application-notes"]');
  eq(w.document.getElementById('applicationNote').value,note,'Notes remain editable for a removed listing');
  input(w,'applicationNote','=Reminder, "quoted"\nSecond line');click(w,'[data-action="save-note"]');
  ok(w.inspect.applicationsCsv().includes('"\'=Reminder, ""quoted""\nSecond line"'),'CSV escapes formulas, quotes and multiline notes');

  const checkpoint=savedStorage(w),reloaded=await boot({saved:checkpoint});
  eq(reloaded.w.document.getElementById('navAppliedCount').textContent,'1','Applied records survive a page reload');
  eq(reloaded.w.inspect.getStore().list()[0].note,'=Reminder, "quoted"\nSecond line');
  const other=await boot({saved:checkpoint,uid:'account-b'});
  eq(other.w.document.getElementById('navAppliedCount').textContent,'0','A different user does not see these records');
  w.userUid='account-b';w.inspect.ensureApplications();
  ok(!w.document.getElementById('appliedGrid').textContent.includes('Reminder'),'Old account notes are cleared before any network reload');
  eq(w.document.getElementById('drawerBody').textContent,'','Hidden drawer notes are cleared on account switch');
  w.inspect.renderAll();
  eq(w.inspect.getStore().list().length,0,'Account switch reinitializes the scoped store');
  w.userUid='account-a';w.inspect.ensureApplications();w.inspect.renderAll();
  eq(w.inspect.getStore().list().length,1,'Original account data remains intact');

  // Simulate a different tab changing this account's existing note.
  const envelope=JSON.parse(w.localStorage.getItem(key));envelope.records[0].note='Updated in another tab';envelope.revision++;
  w.localStorage.setItem(key,JSON.stringify(envelope));
  w.dispatchEvent(new w.StorageEvent('storage',{key,newValue:JSON.stringify(envelope)}));
  eq(w.inspect.getStore().list()[0].note,'Updated in another tab');
  click(w,'#appliedGrid [data-action="application-notes"]');input(w,'applicationNote','Keep my draft');
  const latest=JSON.parse(w.localStorage.getItem(key));latest.records[0].note='A newer saved note';latest.revision++;
  w.localStorage.setItem(key,JSON.stringify(latest));w.confirm=()=>false;click(w,'[data-action="save-note"]');
  eq(JSON.parse(w.localStorage.getItem(key)).records[0].note,'A newer saved note','A conflicting note is not overwritten without confirmation');
  eq(w.document.getElementById('applicationNote').value,'Keep my draft');
  w.confirm=()=>true;click(w,'[data-action="save-note"]');
  eq(w.inspect.getStore().list()[0].note,'Keep my draft');

  // A denied write must leave both the visible saved note and persisted record intact.
  const originalSet=w.Storage.prototype.setItem;
  w.Storage.prototype.setItem=function(){throw new w.DOMException('full','QuotaExceededError');};
  input(w,'applicationNote','Not saved');click(w,'[data-action="save-note"]');
  eq(w.inspect.getStore().list()[0].note,'Keep my draft');
  ok(w.document.getElementById('applicationNoteStatus').textContent.startsWith('Not saved'));
  eq(w.document.getElementById('applicationStorageError').hidden,false);
  w.Storage.prototype.setItem=originalSet;
  input(w,'applicationNote','Keep my draft');click(w,'[data-action="save-note"]');
  click(w,'#appliedGrid [data-action="remove-applied"]');
  eq(w.inspect.getStore().list().length,0,'Applied mark and note can be removed');
  eq(w.document.getElementById('navAppliedCount').textContent,'0');
  eq(w.errors.length,0,'No frontend exceptions');
  dom.window.close();reloaded.dom.window.close();other.dom.window.close();
  console.log(`${checks} archive and application workspace DOM assertions passed.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
