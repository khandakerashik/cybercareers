/* CyberCareers BD — dependency-free static frontend; client-side profile scoring.
   In vault mode (GitHub Pages) all data is decrypted locally after login — see auth.js. */
import * as auth from './auth.js?v=5.3.0';
import {createApplicationStore, NOTE_LIMIT} from './applications.js?v=5.3.0';
const ICONS = {
  globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 0 0 18M12 3a15 15 0 0 1 0 18"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  bookmark:'<path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16l-7-5-7 5Z"/>',
  archive:'<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v12h14V8M9 12h6"/>',
  radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18 6M12 2v2M2 12h2"/>',
  sliders:'<path d="M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M2 14h4m4-6h4m4 8h4"/>',
  shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  chevron:'<path d="m6 9 6 6 6-6"/>',
  briefcase:'<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  building:'<rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-5h6v5M8 6h2m4 0h2M8 10h2m4 0h2M8 14h2m4 0h2"/>',
  info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6M12 7h.01"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  external:'<path d="M14 4h6v6M20 4l-9 9"/><path d="M20 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  map:'<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15m6-12v15"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  close:'<path d="M5 5 19 19M19 5 5 19"/>',
  lock:'<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3"/>',
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
  copy:'<rect x="7" y="7" width="14" height="14" rx="2"/><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/>',
  activity:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  alert:'<path d="m12 3 10 18H2L12 3Zm0 6v5m0 4h.01"/>',
};
function icons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{const path=ICONS[el.dataset.icon];if(path&&!el.querySelector('svg'))el.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;});root.querySelectorAll('.company-mark img[data-fallback]').forEach(img=>{img.addEventListener('error',()=>{if(img.parentNode)img.parentNode.textContent=img.dataset.fallback||'?';},{once:true});});}
const $=s=>document.querySelector(s);
const $$=s=>Array.from(document.querySelectorAll(s));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl=u=>{try{const x=new URL(String(u),location.href);return ['https:','http:'].includes(x.protocol)?x.href:'';}catch{return '';}};
// Original source and application destination may be on different domains.
// Keep the source platform (e.g. LinkedIn, Himalayas) distinct from the
// publisher website, especially when a job feed links directly to an ATS.
function jobSourceDomain(job){
  if(job.source_domain)return String(job.source_domain).toLowerCase().replace(/^www\./,'');
  try{return new URL(String(job.source_url||job.apply_url)).hostname.toLowerCase().replace(/^www\./,'');}
  catch{return 'Unknown source website';}
}
function jobSourceLabel(job){
  if(job.source_name)return String(job.source_name);
  const source=String(job.source||'Unknown source');
  const simple={'LinkedIn index':'LinkedIn','Bdjobs index':'Bdjobs','Indeed index':'Indeed',
    'Glassdoor index':'Glassdoor','Dohaj index':'Dohaj','Job Lagbe index':'Job Lagbe'};
  if(simple[source])return simple[source];
  if(source.startsWith('Official PDF'))return `${job.company} · recruitment circular`;
  if(source.startsWith('Official employer RSS'))return `${job.company} · official jobs RSS`;
  if(source.startsWith('Official employer'))return `${job.company} · official careers`;
  if(source.endsWith(' public API'))return `${source.replace(' public API','')} · ${job.company}`;
  return source;
}
function jobSourceRow(job){
  const link=safeUrl(job.source_url);
  const label=jobSourceLabel(job);
  const domain=jobSourceDomain(job);
  return `<div class="job-source-row" title="Collected from ${esc(label)} — ${esc(domain)}"><span class="job-source-prefix">COLLECTED FROM</span>${link?`<a href="${esc(link)}" target="_blank" rel="noopener noreferrer" class="job-source-link" aria-label="Original listing on ${esc(label)}">${esc(label)} ${svg('external')}</a>`:`<strong class="job-source-link">${esc(label)}</strong>`}<span class="job-source-domain">${esc(domain)}</span></div>`;
}
const CATEGORIES=['All roles','Application Security','SOC & Threat Detection','Network & Cloud Security','GRC & Security Operations','Security Leadership','AI & LLM Security','General Cybersecurity'];
const FOCUS=['Application Security','SOC & Threat Detection','Network & Cloud Security','GRC & Security Operations','Security Leadership','AI & LLM Security'];
const SECTORS=['Banking','Fintech','Telecom','Multinational','Tech / consulting','NBFI / financial services','International employer','Other'];
const DEFAULT_PROFILE={title:'Cybersecurity Analyst / Manager',years:'',skills:'Web Security, API Security, Mobile Security, LLM Security, Penetration Testing, Vulnerability Assessment, OWASP, Burp Suite, Cybersecurity Management',certs:'',categories:['Application Security','AI & LLM Security','Security Leadership'],sectors:['Banking','Fintech']};
const state={jobs:[],sources:[],status:{},sourceHealth:{sources:{}},progress:{},discoveryQueries:[],healthQuery:'',healthSector:'all',healthFilter:'all',healthLimit:70,queryGroup:'all',queryLimit:12,profile:loadProfile(),saved:loadSaved(),intlQuery:'',intlEligibility:'all',intlSource:'all',intlSourceSite:'all',intlSort:'match',intlLimit:30,filters:{category:'All roles',q:'',sector:'all',location:'all',workplace:'all',source:'all',sourceSite:'all',sort:'match',minMatch:0,recent:false,deadline:false,verified:false},archiveQuery:'',archiveRegion:'all',archiveSort:'deadline',archiveSavedOnly:false,archiveLimit:30,appliedQuery:'',appliedStatus:'all',appliedSort:'newest',appliedLimit:30,page:'jobs',sourceQuery:'',sourceSector:'all',sourceLimit:50,drawerId:null,localServer:false,localRefreshing:false};
let toastTimer;
let applicationStore=null,applicationScope='',applicationIssue='';
const applicationDrafts=new Map();

function loadProfile(){try{const p=JSON.parse(localStorage.getItem('ccbd-profile')||'null');return p&&typeof p==='object'?{...DEFAULT_PROFILE,...p}:structuredClone(DEFAULT_PROFILE);}catch{return {...DEFAULT_PROFILE};}}
function loadSaved(){try{const a=JSON.parse(localStorage.getItem('ccbd-saved')||'[]');return new Set(Array.isArray(a)?a:[]);}catch{return new Set();}}
function saveProfile(){localStorage.setItem('ccbd-profile',JSON.stringify(state.profile));}
function saveSaved(){localStorage.setItem('ccbd-saved',JSON.stringify([...state.saved]));}
function bdToday(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Dhaka',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function calendarDate(value){
  const text=String(value||''),day=text.slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return '';
  const midnight=new Date(day+'T00:00:00Z');if(!Number.isFinite(+midnight)||midnight.toISOString().slice(0,10)!==day)return '';
  if(text===day)return day;
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})$/i.test(text))return '';
  const date=new Date(text);return Number.isFinite(+date)?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Dhaka',year:'numeric',month:'2-digit',day:'2-digit'}).format(date):'';
}
function daysDelta(value){const day=calendarDate(value);return day?Math.round((Date.parse(day+'T00:00:00Z')-Date.parse(bdToday()+'T00:00:00Z'))/86400000):null;}
function dateFmt(s){const day=calendarDate(s);return day?new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T12:00:00Z')):'Not stated';}
function shortDate(s){const day=calendarDate(s);return day?new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(day+'T12:00:00Z')):'Date not stated';}
function formatBDTimestamp(value,compact=false){const d=new Date(value);if(!value||Number.isNaN(+d))return 'Not recorded';return new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dhaka',day:'2-digit',month:'short',...(compact?{}:{year:'numeric'}),hour:'2-digit',minute:'2-digit',...(compact?{}:{second:'2-digit'}),hourCycle:'h23'}).format(d)+' BDT';}
function completionStamp(){const p=state.progress||{},s=state.status||{};return p.last_completed_at||s.last_completed_at||(p.phase==='completed'?p.finished_at:null)||(!Object.hasOwn(s,'last_completed_at')?s.updated_at:null)||null;}
function relativeTimestamp(value){const stamp=Date.parse(value);if(!Number.isFinite(stamp))return 'No completion timestamp available';const minutes=Math.max(0,Math.floor((Date.now()-stamp)/60000));if(minutes<1)return 'Just completed';if(minutes<60)return `${minutes} minute${minutes===1?'':'s'} ago`;const hours=Math.floor(minutes/60);return hours<48?`${hours} hour${hours===1?'':'s'} ${minutes%60} min ago`:`${Math.floor(hours/24)} days ago`;}
function renderCompletion(){
  const p=state.progress||{},s=state.status||{},stamp=completionStamp(),plan=p.schedule||s.schedule||{},box=$('.scan-completion');if(!box)return;
  const active=Boolean(p.running),result=p.completion_status||s.completion_status||(p.phase==='completed'?'completed':p.phase==='error'?'failed':'idle');
  const resultLabels={running:'Fetching sources…',completed:'Completed',completed_with_issues:'Completed with source issues',incomplete:'Some targets not processed',failed:'Interrupted / failed',interrupted:'Previous run interrupted',idle:'Awaiting first fetch'};
  const last=$('#scanLastCompleted');last.textContent=stamp?formatBDTimestamp(stamp):'No completed fetch recorded';if(stamp)last.dateTime=stamp;else last.removeAttribute('datetime');
  $('#scanLastCompletedAge').textContent=stamp?relativeTimestamp(stamp):'A start time is not a completed fetch.';
  $('#scanResult').textContent=active?'Fetching sources…':(resultLabels[result]||'Awaiting collection');
  let seconds=active&&p.started_at?Math.max(0,(Date.now()-Date.parse(p.started_at))/1000):(p.duration_seconds??s.duration_seconds);
  $('#scanDuration').textContent=Number.isFinite(seconds)?`${active?'Elapsed':'Duration'}: ${Math.floor(seconds/60)} min ${Math.round(seconds%60)} sec`:'Duration not recorded';
  const next=$('#scanNextExpected'),nextAt=plan.next_scheduled_at;
  next.textContent=plan.enabled?(nextAt?formatBDTimestamp(nextAt):'Next scheduled run'):(plan.mode?'Automatic checks disabled':'Schedule not recorded');
  if(nextAt)next.dateTime=nextAt;else next.removeAttribute('datetime');
  $('#scanScheduleNote').textContent=(plan.note||'All timestamps use Bangladesh time (BDT).')+(auth.vaultMode()?' Last published snapshot.':'');
  const overdue=Boolean(plan.enabled&&!active&&nextAt&&Date.now()>Date.parse(nextAt)+15*60000);
  const stale=Boolean(plan.enabled&&stamp&&!active&&Date.now()-Date.parse(stamp)>(Number(plan.interval_minutes)||60)*60000+35*60000);
  box.classList.toggle('is-stale',overdue||stale);box.classList.toggle('has-issues',['completed_with_issues','incomplete','failed','interrupted'].includes(result));
  if(overdue||stale)$('#scanLastCompletedAge').textContent=(stamp?relativeTimestamp(stamp)+' · ':'')+'A newer completed fetch has not been published.';
  $('#topStatusText').textContent=active?'Fetching sources…':stamp?`Fetched ${formatBDTimestamp(stamp,true)}`:'No completed fetch';
  $('#topStatusText').title=stamp?formatBDTimestamp(stamp):'No completed fetch recorded';
  $('#sideUpdated').textContent=stamp?formatBDTimestamp(stamp,true):'Not yet run';
  $('#sideEngine').textContent=plan.enabled?`${Number(plan.interval_minutes)||60} MIN / SCHEDULED`:(plan.mode?'MANUAL / ON DEMAND':'SCHEDULE UNCONFIRMED');
}
function renderCoverage(){
  const el=$('#coverageSummary');if(!el)return;const s=state.status||{},c=s.source_coverage||{},li=s.linkedin_coverage||{};
  const links=c.link_only_sources??state.sources.filter(isLinkOnly).length;
  const scheduled=c.scheduled_employers??s.official_career_targets_checked??0;
  const optional=(s.source_health||[]).filter(h=>['api:brave','email:alerts','api:jooble'].includes(h.source_id));
  const detail=optional.map(h=>`${h.name}: ${h.message||h.state}`).join(' · ');
  const alertEnabled=li.alerts_configured??c.alert_mailbox_configured,searchEnabled=li.search_configured??c.search_index_configured;
  const configured=Boolean(alertEnabled||searchEnabled);
  const linked=li.listings_retained??state.jobs.filter(j=>/linkedin/i.test(j.source||'')).length;
  el.innerHTML=`<div class="coverage-card"><h2>Collection scope</h2><p><strong>${Number(scheduled)} employer sources scheduled</strong> · ${Number(links)} directory / manual-link sources.</p><p>Directory entries are separate from attempted fetch failures. ${Number(s.detection?.prior_records_quarantined||0)} earlier records removed from the dashboard by the updated checks.</p></div><div class="coverage-card"><h2>LinkedIn discovery · partial coverage</h2><p><strong>${Number(linked)} retained leads</strong> · Alerts ${alertEnabled?'connected':'not configured'} · Search index ${searchEnabled?'connected':'not configured'}.</p><p>${esc(configured?'New email alerts arrive daily or weekly; the fetch schedule is shown above. Indexed results and alert subscriptions do not cover every LinkedIn vacancy.':'Configure your subscribed job-alert mailbox or search index to enable automatic LinkedIn discovery. Public employer sources work independently.')}</p>${detail?`<p class="coverage-action">${esc(detail)}</p>`:''}</div>`;
}
function normalize(s){return String(s||'').toLowerCase().replace(/\b(web app(?:lication)? pentesting|web application security)\b/g,'web security').replace(/\b(pen testing|pentest|vapt)\b/g,'penetration testing').replace(/\b(llm\/ai security|ai\/llm security)\b/g,'llm security').replace(/[^a-z0-9]+/g,' ').trim();}
function profileSkills(){return new Set((state.profile.skills+','+state.profile.certs).split(/[,\n;]+/).map(normalize).filter(Boolean));}
function match(job){
  const user=profileSkills();const expected=Array.isArray(job.skills)?job.skills:[];
  const matched=expected.filter(s=>user.has(normalize(s)));
  const missing=expected.filter(s=>!user.has(normalize(s)));
  const skill=expected.length?matched.length/expected.length:.5;
  const expVal=state.profile.years===''||state.profile.years===null?null:Number(state.profile.years);
  const min=job.min_years===null||job.min_years===undefined?null:Number(job.min_years);
  let experience=.65;
  if(expVal!==null&&Number.isFinite(expVal)&&min!==null&&Number.isFinite(min)) experience=expVal>=min?1:Math.max(.12,expVal/(min||1));
  if(expVal!==null&&Number.isFinite(expVal)&&min===null)experience=.72;
  const cats=state.profile.categories||[];const sectors=state.profile.sectors||[];
  const focus=!cats.length?.72:(cats.includes(job.category)?1:.50);
  const sector=!sectors.length?.72:(sectors.includes(job.company_sector)?1:.65);
  const breakdown={skills:Math.round(skill*100),experience:Math.round(experience*100),focus:Math.round(focus*100),sector:Math.round(sector*100)};
  const score=Math.max(0,Math.min(100,Math.round(skill*.63*100+experience*.20*100+focus*.12*100+sector*.05*100)));
  return {score,matched,missing,breakdown,confidence:expected.length>=4?'Listed-skill based':expected.length?'Limited listing skills':'Insufficient job skill data'};
}
function jobIsOpen(job){if(job.vacancy_status==='closed')return false;const left=daysDelta(job.deadline);return left!==null?left>=0:job.vacancy_status!=='expired';}
function ensureApplications(){
  const uid=auth.vaultMode()?auth.currentUser()?.uid:'local';
  if(!uid)return;
  const scope=new URL('.',location.href).href+'|user:'+uid;
  if(scope===applicationScope&&applicationStore)return;
  const changedAccount=Boolean(applicationScope&&scope!==applicationScope);
  if(scope!==applicationScope){applicationDrafts.clear();applicationStore=null;applicationIssue='';clearApplicationDOM();state.appliedQuery='';state.appliedStatus='all';state.appliedSort='newest';state.appliedLimit=30;$('#appliedSearch').value='';$('#appliedStatus').value='all';$('#appliedSort').value='newest';}
  applicationScope=scope;
  try{applicationStore=createApplicationStore({storage:window.localStorage,scope});applicationIssue='';}
  catch(e){applicationStore=null;applicationIssue=e.message||'Browser storage is unavailable.';}
  if(changedAccount)renderJobViews();
}
function clearApplicationDOM(){closeDrawer();$('#drawerBody').replaceChildren();$('#drawerFooter').replaceChildren();$('#appliedGrid').replaceChildren();$('#navAppliedCount').textContent='0';$('#appliedSummary').textContent='Loading your applications…';for(const button of $$('.track-button')){button.dataset.action='mark-applied';button.classList.remove('is-applied');button.innerHTML=`${svg('check')} Mark as applied`;}icons();}
function applicationRecord(jobOrId){try{return applicationStore?.get(jobOrId?._applicationId||jobOrId)||null;}catch(e){applicationIssue=e.message;return null;}}
function applicationRecords(){try{return applicationStore?.list()||[];}catch(e){applicationIssue=e.message;return [];}}
function liveApplicationJob(record){return state.jobs.find(j=>j.id===record.job.id&&applicationRecord(j)?.id===record.id)||state.jobs.find(j=>applicationRecord(j)?.id===record.id)||null;}
function resolveJob(id){
  const live=state.jobs.find(j=>j.id===id);if(live)return live;
  const record=applicationRecord(id);if(!record)return null;
  return liveApplicationJob(record)||{...record.job,id:record.id,skills:[],description:'Saved application record. This listing is no longer in the current collected dataset. Open the original source to check its current status.',employment_type:'Not recorded',workplace:'Not recorded',seniority:'Not recorded',_applicationSnapshot:true,_applicationId:record.id};
}
function archiveLabel(job){return daysDelta(job.deadline)!==null&&daysDelta(job.deadline)<0?'Deadline passed':'Source marked closed / expired';}
function renderApplicationStorage(){
  const info=$('#applicationStorageInfo'),error=$('#applicationStorageError');
  if(info)info.textContent=auth.vaultMode()?'Applications and notes are saved for your signed-in account in this browser. They do not sync between devices. Export a copy before clearing site data.':'Applications and notes are saved in this browser. They do not sync between devices. Export a copy before clearing site data.';
  if(error){error.hidden=!applicationIssue;error.textContent=applicationIssue?'Application tracker: '+applicationIssue+' Existing stored data has not been overwritten.':'';}
  if($('#exportApplications'))$('#exportApplications').disabled=!applicationRecords().length;
}
function renderJobViews(){renderMetrics();renderJobs();renderInternational();renderSaved();renderArchived();renderApplied();if(state.drawerId){const job=resolveJob(state.drawerId);if(job)renderDrawerContent(job);else closeDrawer();}}
function markApplied(id){
  ensureApplications();const job=resolveJob(id);if(!job)return;
  try{if(!applicationStore)throw Error(applicationIssue||'Browser storage is unavailable.');const record=applicationStore.mark(job);applicationIssue='';renderJobViews();openDrawer(job.id);$('#applicationNote')?.focus();toast('Marked as applied · add a short note below.');return record;}
  catch(e){applicationIssue=e.message;renderApplicationStorage();toast('Could not save application · '+e.message);}
}
function saveApplicationNote(id){
  const field=$('#applicationNote');if(!field||!applicationStore)return;
  try{
    applicationStore.reload();const current=applicationRecord(id),draft=applicationDrafts.get(id);
    if(!current)throw Error('This application was removed in another tab. Mark it as applied again before saving.');
    if(draft&&draft.baseNote!==current.note&&draft.note!==current.note&&!window.confirm('This note changed in another tab. Replace it with your current draft?'))return;
    applicationStore.saveNote(id,field.value);applicationDrafts.delete(id);applicationIssue='';renderApplied();
    const job=resolveJob(state.drawerId);if(job)renderDrawerContent(job);toast('Note saved in this browser.');
  }catch(e){applicationIssue=e.message;renderApplicationStorage();const status=$('#applicationNoteStatus');if(status)status.textContent='Not saved · '+e.message;toast('Note was not saved · '+e.message);}
}
function removeApplication(id){
  const record=applicationRecord(id);if(!record)return;
  if(!window.confirm(`Remove the applied record and note for “${record.job.title}”? This does not withdraw an application from the employer.`))return;
  try{applicationStore.remove(id);applicationDrafts.delete(id);applicationIssue='';renderJobViews();toast('Removed from Applied Jobs.');}
  catch(e){applicationIssue=e.message;renderApplicationStorage();toast('Could not remove application · '+e.message);}
}
function applicationPanel(job){
  const record=applicationRecord(job);
  if(!record)return `<section class="application-panel"><div class="application-panel-heading"><span data-icon="check"></span><h3>Track your application</h3></div><p>Already submitted an application? Mark it here and keep a short follow-up note.</p><button type="button" class="button button-outline" data-action="mark-applied" data-id="${esc(job.id)}">${svg('check')} Mark as applied</button></section>`;
  const draft=applicationDrafts.get(record.id),note=draft?.note??record.note;
  return `<section class="application-panel" id="applicationPanel"><div class="application-panel-heading"><span data-icon="check"></span><h3>Applied ${esc(dateFmt(record.applied_date))}</h3><span class="mini-badge applied">APPLIED</span></div><label for="applicationNote">Your short note</label><textarea id="applicationNote" data-application-id="${esc(record.id)}" maxlength="${NOTE_LIMIT}" rows="4" placeholder="Example: Applied through the company portal. Follow up next week." aria-describedby="applicationNoteStatus applicationNoteCount">${esc(note)}</textarea><div class="application-note-meta"><span id="applicationNoteStatus" role="status" aria-live="polite">${draft?'Unsaved changes':record.note?'Saved in this browser':'Add a note, then choose Save note.'}</span><span id="applicationNoteCount">${note.length} / ${NOTE_LIMIT}</span></div><div class="application-panel-actions"><button type="button" class="button button-green" data-action="save-note" data-id="${esc(record.id)}">Save note ${svg('check')}</button><button type="button" class="ghost-button" data-action="remove-applied" data-id="${esc(record.id)}">Remove applied mark</button></div></section>`;
}
function getJobs(){const f=state.filters;const query=f.q.trim().toLowerCase();let list=state.jobs.filter(job=>{
    if(!jobIsOpen(job)||job.region==='International')return false;
    if(f.category!=='All roles'&&job.category!==f.category)return false;
    if(f.sector!=='all'&&job.company_sector!==f.sector)return false;
    if(f.location!=='all'){const t=(job.location+' '+job.workplace).toLowerCase();if(f.location==='Remote'){if(!(/remote|anywhere|bangladesh.wide/i.test(t)))return false;}else if(!t.includes(f.location.toLowerCase()))return false;}
    if(f.workplace!=='all'&&job.workplace!==f.workplace)return false;
    if(f.source!=='all'&&job.source!==f.source)return false;
    if(f.sourceSite!=='all'&&jobSourceDomain(job)!==f.sourceSite)return false;
    if(f.recent&&!(typeof daysDelta(job.posted_at)==='number'&&daysDelta(job.posted_at)>=-7&&daysDelta(job.posted_at)<=0))return false;
    if(f.deadline&&!job.deadline)return false;
    if(f.verified&&!['Official structured data','Official page parsed','Official PDF circular','Published ATS API','Publisher public API','Publisher page verified','Editorially checked'].includes(job.verification_level))return false;
    if(match(job).score<f.minMatch)return false;
    if(query&&!([job.title,job.company,job.description,job.location,job.category,job.company_sector,(job.skills||[]).join(' ')].join(' ').toLowerCase().includes(query)))return false;
    return true;
  });
  list.sort((a,b)=>{if(f.sort==='newest')return (b.posted_at||'').localeCompare(a.posted_at||'');if(f.sort==='deadline')return (a.deadline||'9999-99-99').localeCompare(b.deadline||'9999-99-99');if(f.sort==='company')return a.company.localeCompare(b.company);return match(b).score-match(a).score || (b.posted_at||'').localeCompare(a.posted_at||'');});return list;
}
function initials(name){const p=String(name||'?').split(/\s+/).filter(w=>!['ltd.','limited','plc','group','the','bank'].includes(w.toLowerCase()));return (p.length>=2?p.slice(0,2).map(w=>w[0]).join(''):p[0]?.slice(0,2)||'?').toUpperCase();}
function mark(job){const url=safeUrl(job.company_logo_url);return `<div class="company-mark">${url?`<img loading="lazy" alt="" data-fallback="${esc(initials(job.company))}" src="${esc(url)}">`:esc(initials(job.company))}</div>`;}
function svg(name){return `<span data-icon="${esc(name)}"></span>`;}
function card(job){
  const m=match(job),left=daysDelta(job.deadline),age=daysDelta(job.posted_at),isNew=age!==null&&age>=-3&&age<=0;
  const applied=applicationRecord(job);
  const tone=m.score>=70?'#94f7aa':m.score>=45?'#d1e5a4':'#b2bfa7';
  const chips=m.matched.slice(0,3).map(s=>`<span class="skill-chip">${esc(s)} ✓</span>`).join('')+m.missing.slice(0,2).map(s=>`<span class="skill-chip missing">${esc(s)}</span>`).join('')+(job.skills?.length>5?`<span class="skill-chip more">+${Math.max(0,job.skills.length-5)} skills</span>`:'');
  return `<article class="job-card" data-card="${esc(job.id)}">
    <div class="job-card-head"><div class="company-profile">${mark(job)}<div class="company-data"><div class="company-name" title="${esc(job.company)}">${esc(job.company)}</div><div class="company-sector">${esc(job.company_sector)}</div></div></div><div class="match-score" title="Estimated fit—not a hiring prediction"><div class="score-ring" style="--ring-color:${tone};--ring-pct:${m.score}%"><strong>${m.score}%</strong></div><span class="match-label">SKILL FIT</span></div></div>
    <div class="job-badges"><span class="mini-badge industry-tag">${esc(job.company_sector||'Industry not specified')}</span>${job.region==='International'?`<span class="mini-badge region-tag">${esc((job.eligibility||'Verify eligibility').replace(' / Bangladesh eligible',''))}</span>`:''}${isNew?'<span class="mini-badge new">NEW</span>':''}${!jobIsOpen(job)?`<span class="mini-badge expired">${daysDelta(job.deadline)!==null&&daysDelta(job.deadline)<0?'DEADLINE PASSED':'CLOSED / EXPIRED'} · ARCHIVE</span>`:job.vacancy_status==='older_unverified'?'<span class="mini-badge archived">OLDER · VERIFY</span>':''}${job.region==='International'&&job.eligibility_confidence==='unconfirmed'?'<span class="mini-badge archived">ELIGIBILITY UNKNOWN</span>':''}<span class="mini-badge">${esc(job.category)}</span>${/volunteer/i.test(job.employment_type||'')?'<span class="mini-badge volunteer">UNPAID VOLUNTEER</span>':''}${job.workplace==='Remote'?'<span class="mini-badge remote">REMOTE</span>':''}${left!==null&&left>=0&&left<=5?`<span class="mini-badge deadline">${left===0?'ENDS TODAY':left+'D LEFT'}</span>`:''}</div>
    <h3 class="job-title"><a href="#jobs" data-action="details" data-id="${esc(job.id)}">${esc(job.title)}</a></h3><p class="job-description">${esc(job.description||'Open the source listing for full job information and requirements.')}</p>
    <div class="job-skills">${chips||'<span class="skill-chip missing">Requirements: see original</span>'}</div><div class="job-spacer"></div>
    ${jobSourceRow(job)}
    <div class="job-meta"><span title="${esc(job.location)}">${svg('map')} ${esc(job.location)}</span><span>${svg('clock')} ${esc(job.posted_at?'Posted '+shortDate(job.posted_at):'Posted date unavailable')}</span>${job.deadline?`<span class="${left!==null&&left<=5?'ends-soon':''}">${svg('calendar')} Due ${esc(shortDate(job.deadline))}</span>`:`<span>${svg('calendar')} Deadline not stated</span>`}</div>
    <div class="job-track-row"><button type="button" class="track-button ${applied?'is-applied':''}" data-action="${applied?'application-notes':'mark-applied'}" data-id="${esc(job.id)}" aria-label="${applied?'Edit application note for':'Mark as applied:'} ${esc(job.title)}">${svg('check')} ${applied?(applied.note?'Applied · Edit note':'Applied · Add note'):'Mark as applied'}</button>${!jobIsOpen(job)?`<span>${esc(archiveLabel(job))}</span>`:''}</div>
    <div class="job-footer"><button class="button button-outline" data-action="details" data-id="${esc(job.id)}">View role details ${svg('arrow')}</button><a class="button button-green" href="${esc(safeUrl(job.apply_url)||safeUrl(job.source_url)||'#')}" target="_blank" rel="noopener noreferrer" aria-label="Open posting or application for ${esc(job.title)}">${jobIsOpen(job)?'Apply / source':'Check archive'} ${svg('external')}</a><button class="icon-button ${state.saved.has(job.id)?'is-saved':''}" data-action="save" data-id="${esc(job.id)}" aria-label="${state.saved.has(job.id)?'Remove saved job':'Save job'}" title="${state.saved.has(job.id)?'Remove saved job':'Save job'}">${svg('bookmark')}</button></div>
  </article>`;
}
function emptyState(message='No openings match these filters.',hint='Try resetting filters or reducing your minimum match score.',showReset=true){return `<div class="empty-state"><span class="sidebar-mini-icon">${svg('search')}</span><h3>${esc(message)}</h3><p>${esc(hint)}</p>${showReset?'<button class="button button-outline" data-action="reset-filters">Reset filters</button>':''}</div>`;}
function renderJobs(){const data=getJobs();$('#jobsGrid').innerHTML=data.length?data.map(card).join(''):emptyState();$('#resultsCount').textContent=`${data.length} results`;$('#filterSummary').textContent=`${data.length} ${data.length===1?'role':'roles'} matching your filters`;$('#resultsFoot').textContent=data.length?`Showing ${data.length} matched job postings · Confirm availability before applying`:'';icons($('#jobsGrid'));}
function internationalJobs(){
  const q=state.intlQuery.trim().toLowerCase();const eligibility=state.intlEligibility;
  const jobs=state.jobs.filter(j=>{
    if(j.region!=='International'||!jobIsOpen(j))return false;
    if(eligibility!=='all'&&(j.eligibility_confidence||'unconfirmed')!==eligibility)return false;
    if(state.intlSource!=='all'&&j.source!==state.intlSource)return false;
    if(state.intlSourceSite!=='all'&&jobSourceDomain(j)!==state.intlSourceSite)return false;
    if(q&&!([j.title,j.company,j.description,j.location,j.category,j.company_sector,j.eligibility,(j.skills||[]).join(' ')].join(' ').toLowerCase().includes(q)))return false;
    return true;
  });
  jobs.sort((a,b)=>state.intlSort==='newest'?String(b.posted_at||'').localeCompare(a.posted_at||''):
    (match(b).score-match(a).score||String(b.posted_at||'').localeCompare(a.posted_at||'')));
  return jobs;
}
function renderFeedHealth(){
  const pane=$('#intlFeedHealth');if(!pane)return;
  const providers=['Himalayas','Remotive','Remote OK','Jobicy'];
  const rows=(state.status.source_health||[]).filter(s=>s.mode==='Free publisher feed');
  const lookup=Object.fromEntries(rows.map(s=>[s.name,s]));
  pane.innerHTML=providers.map(name=>{
    const p=lookup[name];const status=p?.state||'not run';
    const label=status==='ok'?'Updated':status==='cached'?'Scheduled / cached':status==='error'?'Connection error':'Awaiting first scan';
    const summary=!p?'No collection attempt recorded yet.':status==='cached'?`Last successful run: ${p.last_found??'?'} candidate jobs · Next: ${(p.next_check||'').replace('T',' ').slice(0,16)} UTC`:
      status==='error'?`Issue: ${p.message||'Feed failed'} · Raw received: ${p.raw_jobs||0}`:
      `${p.jobs_found||0} relevant candidates · ${p.raw_jobs||0} raw records · ${p.requests||0} request(s)`;
    return `<div class="provider-diagnostic"><div class="provider-title"><span class="health-light ${esc(status)}"></span><strong>${esc(name)}</strong><span>${esc(label)}</span></div><p>${esc(summary)}</p></div>`;
  }).join('');
}
function renderInternational(){
  const all=state.jobs.filter(j=>j.region==='International'&&jobIsOpen(j));
  const list=internationalJobs();
  const shown=list.slice(0,state.intlLimit);
  $('#intlJobsGrid').innerHTML=shown.length?shown.map(card).join(''):emptyState(
    'No eligible international vacancies in this dataset yet.',
    'Free publisher feeds run at startup and are checked periodically. Try adjusting the search or check back after the next hourly refresh.',false);
  $('#intlHeroCount').textContent=all.filter(j=>j.eligibility_confidence==='confirmed').length;
  $('#intlHeroMatch').textContent=all.filter(j=>match(j).score>=70).length;
  $('#intlResultsCount').textContent=`${list.length} opportunities · ${all.length} non-expired in dataset`;
  $('#navInternationalCount').textContent=all.length;
  $('#intlMore').hidden=shown.length>=list.length;
  renderFeedHealth();
  icons($('#intlJobsGrid'));
}
function renderSaved(){const data=state.jobs.filter(j=>state.saved.has(j.id)&&jobIsOpen(j)).sort((a,b)=>match(b).score-match(a).score),archived=state.jobs.filter(j=>state.saved.has(j.id)&&!jobIsOpen(j)).length;$('#savedGrid').innerHTML=data.length?data.map(card).join(''):emptyState('No active saved roles.','Bookmark a job to add it to your shortlist. Past-deadline saved jobs are in Archived Jobs.',false);$('#savedSummary').innerHTML=`${data.length} active saved ${data.length===1?'role':'roles'}${archived?` · <a href="#archived" data-action="saved-archive">${archived} archived</a>`:''}`;$('#navSavedCount').textContent=data.length;icons($('#savedGrid'));}
function archivedJobs(){
  const query=state.archiveQuery.trim().toLowerCase();
  return state.jobs.filter(job=>!jobIsOpen(job)&&(state.archiveRegion==='all'||(job.region==='International'?'International':'Bangladesh')===state.archiveRegion)&&(!state.archiveSavedOnly||state.saved.has(job.id))&&(!query||[job.title,job.company,job.description,job.location,job.category,(job.skills||[]).join(' ')].join(' ').toLowerCase().includes(query))).sort((a,b)=>state.archiveSort==='company'?String(a.company).localeCompare(String(b.company)):state.archiveSort==='match'?match(b).score-match(a).score:String(b.deadline||'').localeCompare(String(a.deadline||''))||String(b.posted_at||'').localeCompare(String(a.posted_at||'')));
}
function renderArchived(){
  const jobs=archivedJobs(),total=state.jobs.filter(j=>!jobIsOpen(j)).length,shown=jobs.slice(0,state.archiveLimit);
  $('#navArchivedCount').textContent=total;$('#archiveSummary').textContent=`${jobs.length} of ${total} archived ${total===1?'job':'jobs'}`;
  $('#archivedGrid').innerHTML=shown.length?shown.map(card).join(''):emptyState(total?'No archived jobs match these filters.':'No past-deadline jobs yet.',total?'Change the search, region or saved-jobs filter.':'Jobs appear here when their deadline passes or a source marks them closed.',false);
  $('#archiveMore').hidden=shown.length>=jobs.length;icons($('#archivedGrid'));
}
function appliedJobs(){
  const query=state.appliedQuery.trim().toLowerCase();
  return applicationRecords().map(record=>{const live=liveApplicationJob(record);return {record,live,job:live||record.job};}).filter(({record,live,job})=>{
    if(state.appliedStatus==='active'&&(!live||!jobIsOpen(job)))return false;
    if(state.appliedStatus==='archived'&&jobIsOpen(job))return false;
    if(state.appliedStatus==='unlisted'&&live)return false;
    return !query||[job.title,job.company,job.location,record.note].join(' ').toLowerCase().includes(query);
  }).sort((a,b)=>state.appliedSort==='company'?String(a.job.company).localeCompare(String(b.job.company)):state.appliedSort==='updated'?String(b.record.updated_at).localeCompare(String(a.record.updated_at)):String(b.record.applied_at).localeCompare(String(a.record.applied_at)));
}
function appliedCard({record,live,job}){
  const expired=!jobIsOpen(job),status=expired?(live?archiveLabel(job):'Recorded deadline / status expired'):live?'Active listing · verify availability':'No longer in current feed';
  return `<article class="job-card application-card" data-application="${esc(record.id)}"><div class="application-card-top"><div class="company-profile">${mark(job)}<div class="company-data"><div class="company-name">${esc(job.company)}</div><div class="company-sector">${esc(job.company_sector||'Industry not recorded')}</div></div></div><span class="mini-badge applied">APPLIED</span></div><h3 class="job-title"><a href="#applied" data-action="details" data-id="${esc(record.id)}">${esc(job.title)}</a></h3><div class="application-dates"><span>${svg('check')} Applied ${esc(dateFmt(record.applied_date))}</span><span class="${expired?'is-archived':''}">${svg(expired?'archive':'info')} ${esc(status)}</span>${job.deadline?`<span>${svg('calendar')} Deadline ${esc(dateFmt(job.deadline))}</span>`:''}</div><div class="application-note-preview"><span>YOUR NOTE</span><p class="${record.note?'':'is-empty'}">${esc(record.note||'No note yet. Add a reminder or follow-up detail.')}</p></div><div class="application-card-actions"><button type="button" class="button button-outline" data-action="application-notes" data-id="${esc(record.id)}">${record.note?'Edit note':'Add note'} ${svg('arrow')}</button><a class="button button-muted" href="${esc(safeUrl(job.apply_url)||safeUrl(job.source_url)||'#')}" target="_blank" rel="noopener noreferrer">View source ${svg('external')}</a><button type="button" class="icon-button" data-action="remove-applied" data-id="${esc(record.id)}" aria-label="Remove applied mark for ${esc(job.title)}" title="Remove applied mark">${svg('close')}</button></div></article>`;
}
function renderApplied(){
  const records=appliedJobs(),total=applicationRecords().length,shown=records.slice(0,state.appliedLimit);
  $('#navAppliedCount').textContent=total;$('#appliedSummary').textContent=`${records.length} of ${total} ${total===1?'application':'applications'}`;
  $('#appliedGrid').innerHTML=shown.length?shown.map(appliedCard).join(''):emptyState(total?'No applications match these filters.':'Your next step starts here.',total?'Search a different job, employer or note, or choose All applications.':'After submitting an application, choose Mark as applied on its job card. You can then add a short note.',false);
  $('#appliedMore').hidden=shown.length>=records.length;renderApplicationStorage();icons($('#appliedGrid'));
}
function renderMetrics(){const open=state.jobs.filter(j=>jobIsOpen(j)&&j.region!=='International');$('#metricTotal').textContent=open.length;$('#metricMatch').textContent=open.filter(j=>match(j).score>=70).length;$('#metricCompanies').textContent=new Set(open.map(j=>j.company.toLowerCase())).size;$('#metricSources').textContent=state.sources.length;$('#navJobsCount').textContent=open.length;$('#navSourcesCount').textContent=state.sources.length;$('#sideSourceCount').textContent=state.sources.length;$('#sideUpdated').textContent=completionStamp()?formatBDTimestamp(completionStamp(),true):'Not yet run';$('#sideEngine').textContent='FREE / HOURLY';$('#sourceTotal').textContent=state.sources.length;$('#sourceBanking').textContent=state.sources.filter(s=>s.sector==='Banking').length;$('#sourcePortals').textContent=state.sources.filter(s=>s.sector==='Job portal').length;$('#sourceChecked').textContent=state.status.official_career_targets_checked||'0';const stamp=completionStamp();$('#topStatusText').textContent=stamp?`Fetched ${formatBDTimestamp(stamp,true)}`:'No completed fetch';
  const banner=$('#dataBanner');banner.classList.remove('warning');
  const providers=(state.status.source_health||[]).filter(x=>x.mode==='Free publisher feed');
  const published=providers.filter(x=>x.state==='ok').length;
  const feedErrors=providers.filter(x=>x.state==='error').length;
  const checked=Number(state.status.official_career_targets_checked||0);
  banner.innerHTML=`${svg('info')}<span><strong>Cybersecurity vacancy intelligence.</strong> ${open.length} non-expired Bangladesh leads · ${(state.status.archived_expired||0)} expired records retained in archive · ${published} feeds updated · ${feedErrors} feed errors · ${checked} employer pages checked. ${stamp?`Last collection <strong>${esc(formatBDTimestamp(stamp))}</strong>.`:(auth.vaultMode()?'First collection runs at the next hourly GitHub Actions publish.':'First live collection begins when your local server starts.')} Jobs and eligibility must be confirmed on the original posting. No paid API keys required.</span>`;
  renderInternational();renderCoverage();renderCompletion();icons(banner);
}
function fillFilters(){
  const bd=state.jobs.filter(j=>j.region!=='International'),intl=state.jobs.filter(j=>j.region==='International');
  const unique=(arr)=>[...new Set(arr.filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b)));
  function populate(id, allLabel, values){
    const el=$('#'+id),current=el?.value||'all';if(!el)return;
    el.innerHTML=`<option value="all">${esc(allLabel)}</option>`+values.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
    el.value=values.includes(current)?current:'all';
  }
  populate('sectorSelect','All sectors',unique(bd.map(j=>j.company_sector)));
  populate('sourceSelect','Every platform',unique(bd.map(j=>j.source)));
  populate('sourceSiteSelect','Every website',unique(bd.map(jobSourceDomain)));
  populate('intlSourceSelect','Every source / portal',unique(intl.map(j=>j.source)));
  populate('intlSourceSiteSelect','Every source website',unique(intl.map(jobSourceDomain)));
  const srcSectors=unique(state.sources.map(s=>s.sector));
  $('#sourceSector').innerHTML='<option value="all">All source categories</option>'+srcSectors.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
  $('#categoryTabs').innerHTML=CATEGORIES.map(s=>`<button class="category-tab ${state.filters.category===s?'active':''}" data-category="${esc(s)}">${esc(s)}</button>`).join('');
}
function healthRecord(src){
  const records=state.sourceHealth?.sources||{};
  return records[src.id] || records['feed:'+src.name] || Object.values(records).find(x=>x.name===src.name) || null;
}
function isLinkOnly(src){return ['restricted','index','directory','link-only'].includes(src.mode) || src.sector==='Social media' || (src.sector==='Job portal');}
function renderProgress(){
  const p=state.progress||{};const total=Number(p.total)||0,checked=Number(p.checked)||0;
  const percentage=total?Math.min(100,Math.max(0,Math.round(100*checked/total))):0;
  const running=Boolean(p.running);
  const panel=$('#hourlyProgress');if(!panel)return;
  panel.classList.toggle('is-active',running);
  panel.classList.toggle('is-completed',!running&&p.phase==='completed');
  panel.classList.toggle('is-error',p.phase==='error'||p.phase==='incomplete');
  $('#progressTitle').textContent=running?'SOURCE SCAN IN PROGRESS':'SOURCE FETCH STATUS';
  $('#progressPhase').textContent=running?(' · '+String(p.phase||'checking').replaceAll('_',' ')):(p.phase==='completed'?' · Last run finished':p.phase==='error'?' · Last scan interrupted':p.phase==='incomplete'?' · Incomplete run':' · Awaiting collection');
  $('#progressPercent').textContent=percentage+'%';$('#progressFill').style.width=percentage+'%';
  $('#progressTrack').setAttribute('aria-valuenow',String(percentage));
  for(const [id,key] of [['progressChecked','checked'],['progressTotal','total'],['progressRemaining','remaining'],['progressOk','succeeded'],['progressBad','failed'],['progressLimited','partial'],['progressNewJobs','new_jobs'],['progressSkipped','skipped']]){
    $('#'+id).textContent=Number(p[key]||0).toLocaleString();
  }
  $('#progressCurrentLabel').textContent=running?'NOW CHECKING':'STATUS';
  $('#progressCurrent').textContent=running?(p.current_source||'Checking sources'):
    (p.phase==='completed'?`${Number(p.succeeded||0)} successful · ${Number(p.partial||0)} limited · ${Number(p.failed||0)} failed · ${Number(p.skipped||0)} cached / deferred`:
    p.phase==='error'?'The previous completion time remains visible; check source health or the run log.':p.phase==='incomplete'?'Some planned targets were not processed; completion time has not advanced.':(auth.vaultMode()?'This view shows the last published collection snapshot.':'Collection begins when the local server starts.'));
  renderCompletion();
}
function renderSourceHealth(){
  const records=state.sourceHealth?.sources||{},all=Object.values(records);
  const unique=new Map(state.sources.map(src=>[src.id,{...src,health:healthRecord(src)}]));
  for(const h of all){
    if(![...unique.values()].some(src=>src.health===h)){
      unique.set(h.id,{id:h.id,name:h.name,sector:h.sector||'ATS boards',domain:'public ATS / feed',mode:'public-api',website:'',health:h});
    }
  }
  const sources=[...unique.values()];
  const observed=sources.filter(src=>src.health?.history?.length);
  const lastSuccess=observed.filter(src=>!isLinkOnly(src)&&src.health.last_result==='success');
  const lastFailure=observed.filter(src=>!isLinkOnly(src)&&src.health.last_result==='failed');
  $('#healthTotal').textContent=sources.length;$('#healthObserved').textContent=observed.length;
  $('#healthSuccess').textContent=lastSuccess.length;$('#healthFailures').textContent=lastFailure.length;
  $('#navHealthCount').textContent=lastFailure.length?lastFailure.length+' !':observed.length;
  const industries=[...new Set(sources.map(src=>src.sector).filter(Boolean))].sort();
  const sectorSelect=$('#healthSector'),current=state.healthSector;
  sectorSelect.innerHTML='<option value="all">Every industry</option>'+industries.map(sec=>`<option value="${esc(sec)}">${esc(sec)}</option>`).join('');
  sectorSelect.value=industries.includes(current)?current:'all';
  const q=state.healthQuery.trim().toLocaleLowerCase();
  const filtered=sources.filter(src=>{
    if(state.healthSector!=='all'&&src.sector!==state.healthSector)return false;
    if(q&&!([src.name,src.domain,src.sector].join(' ').toLocaleLowerCase().includes(q)))return false;
    const history=src.health?.history||[],last=history.at(-1)?.result||'never';
    if(state.healthFilter==='link-only')return isLinkOnly(src);
    if(state.healthFilter==='never')return history.length===0;
    if(['success','failed','partial'].includes(state.healthFilter))return last===state.healthFilter;
    return true;
  });
  filtered.sort((a,b)=>{
    const score=x=>x.health?.last_result==='failed'?0:x.health?.last_result==='partial'?1:x.health?.last_result==='success'?2:isLinkOnly(x)?4:3;
    return score(a)-score(b)||a.name.localeCompare(b.name);
  });
  $('#healthRows').innerHTML=filtered.slice(0,state.healthLimit).map(src=>{
    const history=(src.health?.history||[]).slice(-10);
    const dots=[...Array(Math.max(0,10-history.length)).fill(null),...history].map(check=>{
      const label=!check?'No recorded check':check.result==='success'?'Recruitment source checked':check.result==='partial'?'Limited coverage':'Failed fetch';
      const detail=check?`${check.at||''} · ${check.jobs_found||0} jobs · ${check.message||'No error'}`:'';
      return `<i class="health-square ${!check?'empty':check.result==='success'?'good':check.result==='partial'?'partial':'bad'}" title="${esc(label+' · '+detail)}" aria-label="${esc(label+' '+detail)}"></i>`;
    }).join('');
    const last=history.at(-1),status=isLinkOnly(src)?'link-only':(last?.result||'not scanned');
    const passCount=history.filter(h=>h.result==='success').length;const ratio=history.length?` · ${passCount}/${history.length} passed`:'';
    const detailHint=last?.message?last.message.slice(0,110):'';
    const statusLabel=status==='success'?`Success${ratio} · ${last.jobs_found} jobs`:status==='failed'?`Failed${ratio} · see tooltip`:status==='partial'?`Limited${ratio} · see reason`:status==='link-only'?'Link-only':'Awaiting scan';
    const quick=safeUrl(last?.resolved_url||src.careers_url||src.website);
    const time=last?.at?`Checked ${formatBDTimestamp(last.at)}`:'No fetch attempts recorded';
    return `<div class="health-entry"><div class="health-source"><strong>${esc(src.name)}</strong><span>${esc(src.sector||'Other')} · ${esc(src.domain||'ATS board')}</span>${(status==='failed'||status==='partial')&&detailHint?`<small class="health-error" title="${esc(last.message)}">${esc(detailHint)}</small>`:''}</div><div class="health-dots" title="Oldest check on left">${dots}<small>${esc(time)}</small></div><div class="health-state ${esc(status)}" title="${esc(detailHint)}"><i></i>${esc(statusLabel)}</div><div>${quick?`<a class="source-visit" href="${esc(quick)}" target="_blank" rel="noopener noreferrer">Open ↗</a>`:'<span class="health-not-linked">API</span>'}</div></div>`;
  }).join('')||emptyState('No sources match the selected health filters.','Change the industry, keyword or result status.',false);
  $('#healthMoreWrap').hidden=filtered.length<=state.healthLimit;
  if(!$('#healthMoreWrap').hidden)$('#healthMore').textContent=`Show more sources · ${filtered.length-state.healthLimit} remaining`;
}
function renderDiscovery(){
  const matching=state.discoveryQueries.filter(q=>state.queryGroup==='all'||q.group===state.queryGroup);
  const selected=matching.slice(0,state.queryLimit);
  $('#discoveryQueryGrid').innerHTML=selected.map(q=>{
    const url=safeUrl(q.search_url);
    return `<a class="discovery-item" href="${esc(url||'#')}" target="_blank" rel="noopener noreferrer"><small>${esc(q.group)}</small><span>${esc(q.query)}</span>${svg('external')}</a>`;
  }).join('');
  $('#moreDiscovery').hidden=matching.length<=state.queryLimit;
  if(!$('#moreDiscovery').hidden)$('#moreDiscovery').textContent=`Show ${matching.length-state.queryLimit} more search queries`;
  $$('.query-tab').forEach(el=>el.classList.toggle('active',el.dataset.queryGroup===state.queryGroup));
  icons($('#discoveryQueryGrid'));
}
function renderSources(){const health=state.status.source_health||[];let list=state.sources.filter(s=>{const q=state.sourceQuery.toLowerCase();return (state.sourceSector==='all'||s.sector===state.sourceSector)&&(!q||[s.name,s.domain,s.sector].join(' ').toLowerCase().includes(q));});const count=list.length;list=list.slice(0,state.sourceLimit);$('#sourcesList').innerHTML=list.map(src=>{const info=health.find(x=>x.name===src.name);let label=src.mode==='search'?'Homepage discovery':'Source link / discovery',css='';if(src.mode==='public-api'){label='No-key publisher API';css='ok';}if(src.mode==='restricted'){label='Search links only';css='restricted';}else if(src.mode==='index'){label='Portal index only';css='restricted';}else if(src.mode==='career'){label='Career page / not checked';}if(info){label=info.state==='ok'?`Checked · ${info.jobs_found} matched`:info.state==='cached'?'Cached · scheduled':info.state==='partial'?'Limited coverage · '+(info.reason_code||'see source health'):(info.message||'Blocked / unavailable');css=info.state==='ok'?'ok':info.state==='cached'?'':info.state==='partial'?'limited':'blocked';}const target=safeUrl(src.careers_url||src.website)||`https://www.google.com/search?q=${encodeURIComponent(src.name+' careers information security Bangladesh')}`;return `<div class="source-entry"><div><div class="source-name">${esc(src.name)}</div><div class="source-domain">${esc(src.sector)} / ${esc(src.domain)}</div></div><div class="source-status"><i class="status-dot ${css}"></i>${esc(label)}</div><div class="source-actions"><a class="source-visit" href="${esc(target||'#')}" target="_blank" rel="noopener noreferrer" aria-label="Open website for ${esc(src.name)}">Visit ↗</a></div></div>`;}).join('')||emptyState('No matching sources.','Try a different employer name or sector.',false);if(count>state.sourceLimit)$('#sourcesList').innerHTML+=`<div style="padding:15px;text-align:center;border-top:1px solid #273b2b"><button class="button button-outline" id="moreSources">Show more (${count-state.sourceLimit} remaining)</button></div>`;}
function renderProfile(){const p=state.profile;$('#profileTitle').value=p.title||'';$('#profileYears').value=p.years??'';$('#profileSkills').value=p.skills||'';$('#profileCerts').value=p.certs||'';$('#profileCategories').innerHTML=FOCUS.map((cat,i)=>`<label class="check-chip"><input type="checkbox" name="focusCategory" value="${esc(cat)}" ${p.categories?.includes(cat)?'checked':''}><span>${esc(cat)}</span></label>`).join('');$('#profileSectors').innerHTML=SECTORS.map(sec=>`<label class="check-chip"><input type="checkbox" name="focusSector" value="${esc(sec)}" ${p.sectors?.includes(sec)?'checked':''}><span>${esc(sec)}</span></label>`).join('');}
function renderAll(){fillFilters();renderMetrics();renderJobs();renderSaved();renderArchived();renderApplied();renderSources();renderSourceHealth();renderDiscovery();renderProgress();renderProfile();renderInternational();route();icons();}
function route(){let key=location.hash.replace('#','').split('/')[0]||'jobs';if(!['jobs','international','saved','applied','archived','sources','health','profile','about'].includes(key))key='jobs';state.page=key;$$('.page').forEach(p=>{p.hidden=p.id!==`page-${key}`;p.classList.toggle('active',!p.hidden);});$$('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===key));$('#currentBreadcrumb').textContent=({jobs:'BANGLADESH JOBS',international:'INTERNATIONAL JOBS',saved:'SAVED ROLES',applied:'APPLIED JOBS',archived:'ARCHIVED JOBS',sources:'SOURCE WATCHLIST',health:'SOURCE HEALTH',profile:'MATCH PROFILE',about:'ABOUT'}[key]);$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');if(window.innerWidth<800)window.scrollTo({top:0,behavior:'instant'});}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2700);}
function toggleSave(id){if(state.saved.has(id)){state.saved.delete(id);toast('Removed from saved opportunities');}else{state.saved.add(id);toast('Saved locally in your browser');}saveSaved();renderJobs();renderInternational();renderSaved();renderArchived();if(state.drawerId)renderDrawerContent(resolveJob(state.drawerId));}
function drawerInfo(label,value){return `<div class="detail-cell"><small>${esc(label)}</small><strong>${esc(value??'Not specified')}</strong></div>`;}
function drawList(title,items){return `<section class="drawer-section"><h3>${esc(title)}</h3>${Array.isArray(items)&&items.length?`<ul>${items.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:`<p>Not available in the collected posting. Open the original listing for complete details.</p>`}</section>`;}
function renderDrawerContent(job){if(!job)return;const m=match(job),left=daysDelta(job.deadline),detail=String(job.description||''),img=safeUrl(job.poster_url),source=safeUrl(job.source_url),level=job.description_status||'Search excerpt';const experience=job.min_years===null||job.min_years===undefined?'Not stated':`${job.min_years}${job.max_years?'–'+job.max_years:'+'} years`;
  const noteFocused=document.activeElement?.id==='applicationNote',selection=noteFocused?[$('#applicationNote').selectionStart,$('#applicationNote').selectionEnd]:null,scrollTop=$('#drawerBody').scrollTop;
  $('#drawerBody').innerHTML=`<div class="company-profile">${mark(job)}<div class="company-data"><div class="company-name">${esc(job.company)}</div><div class="company-sector">${esc(job.company_sector)} · ${esc(job.source)}</div></div></div>
    <h2 id="drawerTitle">${esc(job.title)}</h2><div class="drawer-subtitle">${esc(job.location)} · ${esc(job.employment_type)} · ${esc(job.workplace)}</div><div class="drawer-tags"><span>${esc(job.company_sector||'Industry not stated')}</span><span>${esc(job.region==='International'?(job.eligibility||'Verify eligibility'):'Bangladesh opportunity')}</span></div>
    <div class="drawer-tags"><span>${esc(job.category)}</span><span>${esc(job.seniority)}</span><span>${m.score}% estimated fit</span></div>
    <div class="drawer-detail-grid">${drawerInfo('POSTED',dateFmt(job.posted_at))}${drawerInfo('APPLICATION DEADLINE',job.deadline?`${dateFmt(job.deadline)}${left===0?' · Today':left>0&&left<=5?` · ${left}d left`:''}`:'Not stated')}${drawerInfo('EXPERIENCE',experience)}${drawerInfo('COMPENSATION',job.salary||'Not disclosed')}</div>
    ${!jobIsOpen(job)?`<p class="drawer-archive-notice">${svg('archive')} Archived · ${esc(archiveLabel(job))}${job.deadline?' ('+esc(dateFmt(job.deadline))+')':''}. Your application record stays in Applied Jobs.</p>`:''}
    ${applicationPanel(job)}
    <div class="drawer-match-detail"><h3>${m.score}% estimated alignment with your profile</h3><p>${esc(m.confidence)} · Calculated from advertised skills, entered experience and your preferred fields. ${state.profile.years===''?'Your years of experience are not yet set.':''}</p><div class="drawer-breakdown"><span>Skills ${m.breakdown.skills}%</span><span>Experience ${m.breakdown.experience}%</span><span>Focus ${m.breakdown.focus}%</span><span>Sector ${m.breakdown.sector}%</span></div><div class="drawer-tags" style="margin:14px 0 0">${m.matched.map(s=>`<span>✓ ${esc(s)}</span>`).join('')||'<span>No explicitly matching listed skills yet</span>'}${m.missing.slice(0,5).map(s=>`<span style="background:#2c271a;border-color:#5a4931;color:#e0c7a0">Gap · ${esc(s)}</span>`).join('')}</div></div>
    <section class="drawer-section"><h3>About this opportunity</h3><p>${esc(detail||'Full description is not available in the dataset. Visit the original posting to review job requirements.')}</p></section>
    ${drawList('Key responsibilities',job.responsibilities)}${drawList('Job requirements',job.requirements)}
    ${img?`<section class="drawer-section"><h3>Image included in job posting</h3><img class="drawer-poster" loading="lazy" src="${esc(img)}" alt="Posting image supplied by the original job source"></section>`:''}
    <section class="drawer-section"><h3>Source & completeness</h3>
      <div class="drawer-origin"><span>COLLECTED FROM</span><strong>${esc(jobSourceLabel(job))}</strong><small>${esc(jobSourceDomain(job))} · ${esc(job.source||'Unspecified collection method')}</small></div>
      <p class="drawer-source-note">${esc(level)} · ${esc(job.verification_level||'Source indexed')}. Third-party job portals may expose only excerpts. The original listing is authoritative for eligibility, application procedure, vacancy status and deadline.</p>
      ${source?`<a class="drawer-source-link" href="${esc(source)}" target="_blank" rel="noopener noreferrer">View original source posting ${svg('external')}</a>`:''}
      ${job.vacancy_reason?`<p class="drawer-source-note"><strong>Why this appeared:</strong> ${esc(job.vacancy_reason)}${Array.isArray(job.vacancy_evidence)&&job.vacancy_evidence.length?` · ${esc(job.vacancy_evidence.slice(0,6).join(', '))}`:''}. Detection signals do not confirm that a vacancy is still open.</p>`:''}
      ${job.alert_received_at?`<p class="drawer-source-note">Alert received: ${esc(dateFmt(String(job.alert_received_at).slice(0,10)))}. The posting date is shown only when supplied by the publisher.</p>`:''}
      ${Number.isFinite(job.relevance_score)?`<p class="drawer-source-note">Cybersecurity relevance signal <strong>${esc(job.relevance_score)}/100</strong>${Array.isArray(job.matched_terms)&&job.matched_terms.length?` · matched: ${esc(job.matched_terms.slice(0,8).join(', '))}`:''}</p>`:''}
      ${Array.isArray(job.also_listed_on)&&job.also_listed_on.length?`<div class="drawer-also"><span>ALSO LISTED ON</span>${job.also_listed_on.map(x=>safeUrl(x.url)?`<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener noreferrer">${esc(x.source_name||jobSourceDomain({source_url:x.url}))} ${svg('external')}</a>`:'').join('')}</div>`:''}
    </section>`;
  $('#drawerFooter').innerHTML=`${!job._applicationSnapshot?`<button class="icon-button ${state.saved.has(job.id)?'is-saved':''}" data-action="save" data-id="${esc(job.id)}" title="Save opportunity" aria-label="Save opportunity">${svg('bookmark')}</button>`:''}<button class="button button-muted" data-action="copy" data-id="${esc(job.id)}">${svg('copy')} Copy link</button><a class="button button-green" href="${esc(safeUrl(job.apply_url)||source||'#')}" target="_blank" rel="noopener noreferrer">${jobIsOpen(job)&&!job._applicationSnapshot?'Open posting / apply':'View original source'} ${svg('external')}</a>`;icons($('#jobDrawer'));
  $('#drawerBody').scrollTop=scrollTop;if(noteFocused&&$('#applicationNote')){$('#applicationNote').focus({preventScroll:true});$('#applicationNote').setSelectionRange(...selection);}
}
function openDrawer(id){const job=resolveJob(id);if(!job)return;const same=state.drawerId===id;state.drawerId=id;renderDrawerContent(job);if(!same)$('#drawerBody').scrollTop=0;$('#jobDrawer').classList.add('open');$('#jobDrawer').setAttribute('aria-hidden','false');$('#drawerBackdrop').classList.add('open');document.body.classList.add('lock-scroll');$('#closeDrawer').focus();}
function closeDrawer(){state.drawerId=null;$('#jobDrawer').classList.remove('open');$('#jobDrawer').setAttribute('aria-hidden','true');$('#drawerBackdrop').classList.remove('open');document.body.classList.remove('lock-scroll');}
function resetFilters(){state.filters={category:'All roles',q:'',sector:'all',location:'all',workplace:'all',source:'all',sourceSite:'all',sort:'match',minMatch:0,recent:false,deadline:false,verified:false};$('#jobSearch').value='';$('#sectorSelect').value='all';$('#locationSelect').value='all';$('#workplaceSelect').value='all';$('#sourceSelect').value='all';$('#sourceSiteSelect').value='all';$('#sortSelect').value='match';$('#matchRange').value='0';$('#matchRangeText').textContent='0%';$('#recentOnly').checked=false;$('#hasDeadline').checked=false;$('#hideUnverified').checked=false;fillFilters();renderJobs();}
function csvExport(){const fields=[['Title','title'],['Company','company'],['Sector','company_sector'],['Location','location'],['Workplace','workplace'],['Employment type','employment_type'],['Skill match %','_match'],['Posted','posted_at'],['Deadline','deadline'],['Experience years','min_years'],['Salary','salary'],['Required skills','_skills'],['Source platform','source'],['Original publisher','_source_name'],['Source website','_source_domain'],['Original source link','source_url'],['Apply link','apply_url']];const cell=s=>{let v=String(s??'');if(/^[\s]*[=+\-@\t\r]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};const rows=[fields.map(p=>cell(p[0])).join(',')];getJobs().forEach(j=>rows.push(fields.map(([,k])=>cell(k==='_match'?match(j).score:k==='_skills'?(j.skills||[]).join('; '):k==='_source_name'?jobSourceLabel(j):k==='_source_domain'?jobSourceDomain(j):j[k])).join(',')));const blob=new Blob(['\ufeff'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`cybercareers-bd-${bdToday()}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),3000);toast('CSV exported · spreadsheet-formula protection enabled');}
async function loadData(){const files=['data/jobs.json','data/sources.json','data/status.json','data/source_health.json','data/progress.json','data/search_queries.json'];const results=await Promise.all(files.map(async filename=>{if(auth.vaultMode()){const name=filename.slice(5);try{return await auth.loadJSON(name);}catch(e){if(/not in the encrypted dataset/.test(e.message))return name==='jobs.json'?{jobs:[]}:name.endsWith('queries.json')||name==='sources.json'?[]:{};throw e;}}const r=await fetch(filename+'?v='+Date.now(),{cache:'no-store'});if(r.status===404&&['data/jobs.json','data/status.json','data/source_health.json','data/progress.json'].includes(filename))return filename==='data/jobs.json'?{jobs:[]}:{};if(!r.ok)throw Error(`Could not load ${filename}: ${r.status}`);return r.json();}));state.jobs=Array.isArray(results[0].jobs)?results[0].jobs:[];state.sources=Array.isArray(results[1])?results[1]:[];state.status=results[2]||{};state.sourceHealth=results[3]||{sources:{}};state.progress=results[4]||{};state.discoveryQueries=Array.isArray(results[5])?results[5]:[];}
// Local-only service discovery and refresh. Static GitHub Pages continues working.
let localRefreshTimer=null;
function showRefreshState(running){
  state.localRefreshing=running;
  const btn=$('#refreshJobsButton');
  if(btn){
    btn.hidden=!state.localServer;
    btn.disabled=running;
    btn.innerHTML=running?`${svg('radar')} Checking sources…`:`${svg('radar')} Refresh jobs`;
    icons(btn);
  }
  const scan=$('#scanNowButton');
  if(scan){
    scan.hidden=!state.localServer;
    scan.disabled=running;
    scan.classList.toggle('is-running',running);
    scan.querySelector('.scan-now-label').textContent=running?'Scanning…':'Scan now';
    icons(scan);
  }
}
async function fetchLocalRefreshStatus(){
  const r=await fetch('/api/refresh/status',{cache:'no-store'});
  if(!r.ok)throw Error('Local refresh status unavailable');
  return r.json();
}
async function reloadRefreshedData(){
  ensureApplications();
  await loadData();
  fillFilters();
  const f=state.filters;
  for(const [id,key] of [['sectorSelect','sector'],['locationSelect','location'],['workplaceSelect','workplace'],['sourceSelect','source'],['sourceSiteSelect','sourceSite'],['sortSelect','sort']])$('#'+id).value=f[key];
  $('#intlSourceSelect').value=state.intlSource;$('#intlSourceSiteSelect').value=state.intlSourceSite;
  $('#sourceSector').value=state.sourceSector;
  renderMetrics();renderJobs();renderInternational();renderSaved();renderArchived();renderApplied();renderSources();renderSourceHealth();renderDiscovery();renderProgress();
  if(state.drawerId){const opened=resolveJob(state.drawerId);if(opened)renderDrawerContent(opened);else closeDrawer();}
}
async function pollLocalRefresh(){
  localRefreshTimer=null;
  try{
    const report=await fetchLocalRefreshStatus();
    state.progress=report.progress||state.progress;
    renderProgress();
    if(report.running){
      showRefreshState(true);
      try{
        const h=await fetch('/data/source_health.json?v='+Date.now(),{cache:'no-store'});
        if(h.ok){state.sourceHealth=await h.json();if(state.page==='health')renderSourceHealth();}
      }catch{/* Current progress remains visible during a brief disk write. */}

      localRefreshTimer=setTimeout(pollLocalRefresh,2500);
      return;
    }
    const wasRunning=state.localRefreshing;
    showRefreshState(false);
    if(wasRunning){
      await reloadRefreshedData();
      const last=report.last_result;
      toast(report.last_error||(!last?'Refresh finished':`Refresh complete · ${last.jobs_count||0} jobs · ${last.new_candidates||0} candidates`));
    }
  }catch(e){
    showRefreshState(false);
    toast('Could not check refresh status · verify the local server');
    console.warn(e);
  }
}
async function detectLocalServer(){
  if(auth.vaultMode()||!/^https?:$/.test(location.protocol))return;
  try{
    const r=await fetch('/api/health',{cache:'no-store'});
    if(!r.ok)return;
    const info=await r.json();
    if(info.mode!=='local'||info.ok!==true)return;
    state.localServer=true;
    showRefreshState(false);
    renderMetrics();
    const report=await fetchLocalRefreshStatus();
    state.progress=report.progress||state.progress;renderProgress();
    if(report.running){showRefreshState(true);localRefreshTimer=setTimeout(pollLocalRefresh,2500);}
    // Follow the server's independent hourly background schedule while a tab
    // remains open. Do not require a manual browser refresh to see new jobs.
    if(!window.cybercareersSyncTimer){
      window.cybercareersSyncTimer=setInterval(async()=>{
        if(!state.localServer)return;
        try{
          const progress=await fetchLocalRefreshStatus();
          state.progress=progress.progress||state.progress;renderProgress();
          if(progress.running){showRefreshState(true);if(!localRefreshTimer)localRefreshTimer=setTimeout(pollLocalRefresh,700);return;}
          const snapshot=await fetch('/data/status.json?v='+Date.now(),{cache:'no-store'});
          if(!snapshot.ok)return;
          const newest=await snapshot.json();
          if((newest.updated_at && newest.updated_at!==state.status.updated_at)||
             (newest.collection_finished_at && newest.collection_finished_at!==state.status.collection_finished_at)||
             (newest.progress_summary?.run_id && newest.progress_summary.run_id!==state.status.progress_summary?.run_id)){
            await reloadRefreshedData();
            toast('Job intelligence automatically synchronized · newest source scan loaded');
          }
          if(state.localRefreshing&&!localRefreshTimer)showRefreshState(false);
        }catch{ /* Offline: the previous cached dataset stays visible. */ }
      },60*1000);
    }
  }catch{ /* The page is hosted statically; no local refresh API is available. */ }
}
async function triggerLocalRefresh(){
  if(!state.localServer||state.localRefreshing)return;
  try{
    const r=await fetch('/api/refresh',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-CyberCareers-Action':'refresh'},
      body:'{}',
    });
    if(r.status!==202&&r.status!==409)throw Error(`Request failed (${r.status})`);
    const initial=await r.json();state.progress=initial.progress||state.progress;renderProgress();
    showRefreshState(true);
    toast(r.status===409?'A refresh is already running':'Source checking started · current jobs remain visible');
    if(localRefreshTimer)clearTimeout(localRefreshTimer);
    localRefreshTimer=setTimeout(pollLocalRefresh,1500);
  }catch(e){toast('Could not start refresh · '+e.message);}
}
function applicationsCsv(){
  const cell=value=>{let text=String(value??'');if(/^[\s]*[=+\-@\t\r]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';};
  const rows=[['Title','Company','Applied date (BDT)','Deadline','Listing status','Notes','Notes last updated','Source URL']];
  for(const record of applicationRecords()){const live=liveApplicationJob(record),job=live||record.job;rows.push([job.title,job.company,record.applied_date,job.deadline,!jobIsOpen(job)?archiveLabel(job):live?'Active listing - verify availability':'No longer in current feed',record.note,record.updated_at,job.source_url||job.apply_url]);}
  return '\ufeff'+rows.map(row=>row.map(cell).join(',')).join('\r\n');
}
function exportApplications(){
  if(!applicationRecords().length)return;
  const blob=new Blob([applicationsCsv()],{type:'text/csv;charset=utf-8'}),link=document.createElement('a');
  link.href=URL.createObjectURL(blob);link.download=`cybercareers-applied-${bdToday()}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),3000);toast('Applications and notes exported.');
}
let deadlineDay=bdToday();
function refreshDeadlineViews(){const day=bdToday();if(day!==deadlineDay){deadlineDay=day;renderJobViews();}}
function bind(){
  window.addEventListener('hashchange',route);
  document.addEventListener('click',async e=>{
    const act=e.target.closest('[data-action]');if(act){e.preventDefault();const id=act.dataset.id;
      if(act.dataset.action==='details')openDrawer(id);
      if(act.dataset.action==='save')toggleSave(id);
      if(act.dataset.action==='mark-applied')markApplied(id);
      if(act.dataset.action==='application-notes'){openDrawer(id);$('#applicationNote')?.focus();}
      if(act.dataset.action==='save-note')saveApplicationNote(id);
      if(act.dataset.action==='remove-applied')removeApplication(id);
      if(act.dataset.action==='saved-archive'){state.archiveSavedOnly=true;$('#archiveSavedOnly').checked=true;renderArchived();location.hash='archived';}
      if(act.dataset.action==='copy'){const j=resolveJob(id);if(j){try{await navigator.clipboard.writeText(j.apply_url||j.source_url);toast('Job link copied');}catch{toast('Could not copy automatically · open the original posting');}}}
      if(act.dataset.action==='reset-filters')resetFilters();return;
    }
    const p=e.target.closest('[data-page-button]');if(p){location.hash=p.dataset.pageButton;return;}
    const category=e.target.closest('[data-category]');if(category){state.filters.category=category.dataset.category;$$('[data-category]').forEach(el=>el.classList.toggle('active',el===category));renderJobs();return;}
    if(e.target.closest('#moreSources')){state.sourceLimit+=50;renderSources();return;}
    if(e.target.closest('#healthMore')){state.healthLimit+=70;renderSourceHealth();return;}
    if(e.target.closest('#moreDiscovery')){state.queryLimit+=24;renderDiscovery();return;}
    const qtab=e.target.closest('[data-query-group]');if(qtab){state.queryGroup=qtab.dataset.queryGroup;state.queryLimit=12;renderDiscovery();return;}
    if(e.target.closest('#intlMoreButton')){state.intlLimit+=30;renderInternational();return;}
    if(e.target.closest('#archiveMoreButton')){state.archiveLimit+=30;renderArchived();return;}
    if(e.target.closest('#appliedMoreButton')){state.appliedLimit+=30;renderApplied();return;}
  });
  document.addEventListener('input',e=>{if(e.target.id!=='applicationNote')return;const field=e.target,id=field.dataset.applicationId,record=applicationRecord(id);if(!record)return;const note=field.value.slice(0,NOTE_LIMIT);if(note===record.note)applicationDrafts.delete(id);else applicationDrafts.set(id,{note,baseNote:applicationDrafts.get(id)?.baseNote??record.note});$('#applicationNoteCount').textContent=`${note.length} / ${NOTE_LIMIT}`;$('#applicationNoteStatus').textContent=applicationDrafts.has(id)?'Unsaved changes':'Saved in this browser';});
  window.addEventListener('storage',e=>{if(!applicationStore||(e.key!==null&&e.key!==applicationStore.storageKey))return;try{applicationStore.reload();applicationIssue='';renderJobViews();}catch(error){applicationIssue=error.message;renderApplicationStorage();}});
  window.addEventListener('beforeunload',e=>{if(applicationDrafts.size){e.preventDefault();e.returnValue='';}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshDeadlineViews();});
  $('#exportApplications')?.addEventListener('click',exportApplications);
  $('#archiveSearch')?.addEventListener('input',e=>{state.archiveQuery=e.target.value;state.archiveLimit=30;renderArchived();});
  $('#archiveRegion')?.addEventListener('change',e=>{state.archiveRegion=e.target.value;state.archiveLimit=30;renderArchived();});
  $('#archiveSort')?.addEventListener('change',e=>{state.archiveSort=e.target.value;renderArchived();});
  $('#archiveSavedOnly')?.addEventListener('change',e=>{state.archiveSavedOnly=e.target.checked;state.archiveLimit=30;renderArchived();});
  $('#appliedSearch')?.addEventListener('input',e=>{state.appliedQuery=e.target.value;state.appliedLimit=30;renderApplied();});
  $('#appliedStatus')?.addEventListener('change',e=>{state.appliedStatus=e.target.value;state.appliedLimit=30;renderApplied();});
  $('#appliedSort')?.addEventListener('change',e=>{state.appliedSort=e.target.value;renderApplied();});
  $('#exploreButton')?.addEventListener('click',()=>$('#openingsHeader').scrollIntoView({behavior:'smooth',block:'start'}));
  $('#clearFilters')?.addEventListener('click',resetFilters);$('#exportButton')?.addEventListener('click',csvExport);$('#refreshJobsButton')?.addEventListener('click',triggerLocalRefresh);$('#scanNowButton')?.addEventListener('click',triggerLocalRefresh);
  $('#jobSearch')?.addEventListener('input',e=>{state.filters.q=e.target.value;renderJobs();});
  $('#intlSearch')?.addEventListener('input',e=>{state.intlQuery=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlEligibilitySelect')?.addEventListener('change',e=>{state.intlEligibility=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSourceSelect')?.addEventListener('change',e=>{state.intlSource=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSourceSiteSelect')?.addEventListener('change',e=>{state.intlSourceSite=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSortSelect')?.addEventListener('change',e=>{state.intlSort=e.target.value;renderInternational();});
  for(const [id,key] of [['sectorSelect','sector'],['locationSelect','location'],['workplaceSelect','workplace'],['sourceSelect','source'],['sourceSiteSelect','sourceSite'],['sortSelect','sort']])$('#'+id)?.addEventListener('change',e=>{state.filters[key]=e.target.value;renderJobs();});
  $('#matchRange')?.addEventListener('input',e=>{state.filters.minMatch=Number(e.target.value);$('#matchRangeText').textContent=e.target.value+'%';renderJobs();});
  for(const [id,key] of [['recentOnly','recent'],['hasDeadline','deadline'],['hideUnverified','verified']])$('#'+id)?.addEventListener('change',e=>{state.filters[key]=e.target.checked;renderJobs();});
  $('#sourceSearch')?.addEventListener('input',e=>{state.sourceQuery=e.target.value;state.sourceLimit=50;renderSources();});
  $('#sourceSector')?.addEventListener('change',e=>{state.sourceSector=e.target.value;state.sourceLimit=50;renderSources();});
  $('#healthSearch')?.addEventListener('input',e=>{state.healthQuery=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#healthSector')?.addEventListener('change',e=>{state.healthSector=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#healthFilter')?.addEventListener('change',e=>{state.healthFilter=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#profileForm')?.addEventListener('submit',e=>{e.preventDefault();const years=$('#profileYears').value.trim();state.profile={title:$('#profileTitle').value.trim(),years:years===''?'':Math.min(45,Math.max(0,Number(years))),skills:$('#profileSkills').value.trim().slice(0,3000),certs:$('#profileCerts').value.trim().slice(0,350),categories:$$('input[name=focusCategory]:checked').map(el=>el.value),sectors:$$('input[name=focusSector]:checked').map(el=>el.value)};saveProfile();renderJobViews();toast('Profile saved privately · matches recalculated');location.hash='jobs';});
  $('#resetProfile')?.addEventListener('click',()=>{state.profile=structuredClone(DEFAULT_PROFILE);saveProfile();renderProfile();renderJobViews();toast('Profile restored to default focus areas');});
  $('#closeDrawer')?.addEventListener('click',closeDrawer);$('#drawerBackdrop')?.addEventListener('click',closeDrawer);
  $('#menuToggle')?.addEventListener('click',()=>{$('#sidebar').classList.add('open');$('#mobileShade').classList.add('open');});
  $('#mobileShade')?.addEventListener('click',()=>{$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');}if((e.key==='/'||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'))&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();if(state.page==='international'){$('#intlSearch').focus();}else{location.hash='jobs';$('#jobSearch').focus();}}});
}
function showSession(){if(!auth.vaultMode())return;const who=auth.currentUser();$$('.vault-only').forEach(el=>el.hidden=false);const su=$('#sessionUser');if(su)su.textContent=who?.name||'Signed in';const logout=$('#logoutButton');if(logout)logout.onclick=()=>{if(!applicationDrafts.size||window.confirm('You have unsaved application notes. Sign out and discard those edits?')){applicationDrafts.clear();auth.logout();}};const note=$('#sidePolicyNote');if(note)note.textContent='Encrypted dataset · unlocked in this browser only. Collection runs hourly in GitHub Actions.';}
let vaultSyncBusy=false;
let vaultReloadPending=false;
let snapshotSyncStarted=false;
function startSnapshotSync(){
  if(snapshotSyncStarted)return;
  snapshotSyncStarted=true;
  setInterval(()=>{renderCompletion();refreshDeadlineViews();},30000);
  if(!auth.vaultMode())return;
  const sync=async()=>{
    if(vaultSyncBusy||document.hidden)return;
    vaultSyncBusy=true;
    try{
      const result=await auth.refreshPublishedSession();
      if(result.reauthenticate){
        document.documentElement.classList.add('cc-locked');
        clearApplicationDOM();
        await auth.requireLogin();
        ensureApplications();
        vaultReloadPending=true;
      }
      if(result.changed)vaultReloadPending=true;
      if(vaultReloadPending){
        await reloadRefreshedData();showSession();
        vaultReloadPending=false;
        toast('Latest published fetch loaded');
      }
    }catch(e){console.warn('Snapshot refresh deferred',e);}
    finally{vaultSyncBusy=false;}
  };
  setInterval(sync,60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
}
async function init(){
  icons();
  if(auth.vaultMode()){
    document.documentElement.classList.add('cc-locked');
    if(!(await auth.restoreSession()))await auth.requireLogin();
    document.documentElement.classList.remove('cc-locked');
  }
  try{bind();}catch(e){console.error('UI binding failed',e);}
  ensureApplications();showSession();
  try{
    await loadData();showSession();renderAll();
  }catch(e){
    vaultReloadPending=auth.vaultMode();
    console.error(e);
    $('#jobsGrid').innerHTML=emptyState('Dataset could not be loaded.','The last published snapshot may still be updating. Automatic refresh will retry.',false);
    $('#dataBanner').textContent=auth.vaultMode()?'The published dataset is temporarily unavailable. Automatic refresh will retry.':'The job dataset was unavailable. Run python -m server.app from the project directory.';
    renderArchived();renderApplied();route();icons();
  }finally{startSnapshotSync();if(!auth.vaultMode())await detectLocalServer();}
}
init();
