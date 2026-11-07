/* CyberCareers BD — dependency-free static frontend; client-side profile scoring.
   In vault mode (GitHub Pages) all data is decrypted locally after login — see auth.js. */
import * as auth from './auth.js';
const ICONS = {
  globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 0 0 18M12 3a15 15 0 0 1 0 18"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  bookmark:'<path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16l-7-5-7 5Z"/>',
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
const state={jobs:[],sources:[],status:{},sourceHealth:{sources:{}},progress:{},discoveryQueries:[],healthQuery:'',healthSector:'all',healthFilter:'all',healthLimit:70,queryGroup:'all',queryLimit:12,profile:loadProfile(),saved:loadSaved(),intlQuery:'',intlEligibility:'all',intlSource:'all',intlSourceSite:'all',intlSort:'match',intlLimit:30,intlIncludeExpired:false,filters:{category:'All roles',q:'',sector:'all',location:'all',workplace:'all',source:'all',sourceSite:'all',sort:'match',minMatch:0,recent:false,deadline:false,verified:false,includeExpired:false},page:'jobs',sourceQuery:'',sourceSector:'all',sourceLimit:50,drawerId:null,localServer:false,localRefreshing:false};
let toastTimer;

function loadProfile(){try{const p=JSON.parse(localStorage.getItem('ccbd-profile')||'null');return p&&typeof p==='object'?{...DEFAULT_PROFILE,...p}:structuredClone(DEFAULT_PROFILE);}catch{return {...DEFAULT_PROFILE};}}
function loadSaved(){try{const a=JSON.parse(localStorage.getItem('ccbd-saved')||'[]');return new Set(Array.isArray(a)?a:[]);}catch{return new Set();}}
function saveProfile(){localStorage.setItem('ccbd-profile',JSON.stringify(state.profile));}
function saveSaved(){localStorage.setItem('ccbd-saved',JSON.stringify([...state.saved]));}
function bdToday(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Dhaka',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function daysDelta(date){if(!/^\d{4}-\d{2}-\d{2}$/.test(String(date||'')))return null;return Math.round((Date.parse(date+'T00:00:00Z')-Date.parse(bdToday()+'T00:00:00Z'))/86400000);}
function dateFmt(s){if(!s)return 'Not stated';const d=new Date(s+'T12:00:00Z');return Number.isNaN(+d)?'Not stated':new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(d);}
function shortDate(s){if(!s)return 'Date not stated';const d=new Date(s+'T12:00:00Z');return Number.isNaN(+d)?'Not stated':new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(d);}
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
function jobIsOpen(job){const left=daysDelta(job.deadline);return job.vacancy_status!=='expired'&&(left===null||left>=0);}
function getJobs(){const f=state.filters;const query=f.q.trim().toLowerCase();let list=state.jobs.filter(job=>{
    if((!f.includeExpired&&!jobIsOpen(job))||job.region==='International')return false;
    if(f.category!=='All roles'&&job.category!==f.category)return false;
    if(f.sector!=='all'&&job.company_sector!==f.sector)return false;
    if(f.location!=='all'){const t=(job.location+' '+job.workplace).toLowerCase();if(f.location==='Remote'){if(!(/remote|anywhere|bangladesh.wide/i.test(t)))return false;}else if(!t.includes(f.location.toLowerCase()))return false;}
    if(f.workplace!=='all'&&job.workplace!==f.workplace)return false;
    if(f.source!=='all'&&job.source!==f.source)return false;
    if(f.sourceSite!=='all'&&jobSourceDomain(job)!==f.sourceSite)return false;
    if(f.recent&&!(typeof daysDelta(job.posted_at)==='number'&&daysDelta(job.posted_at)>=-7&&daysDelta(job.posted_at)<=0))return false;
    if(f.deadline&&!job.deadline)return false;
    if(f.verified&&job.verification_level==='Search indexed (unverified)')return false;
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
  const tone=m.score>=70?'#94f7aa':m.score>=45?'#d1e5a4':'#b2bfa7';
  const chips=m.matched.slice(0,3).map(s=>`<span class="skill-chip">${esc(s)} ✓</span>`).join('')+m.missing.slice(0,2).map(s=>`<span class="skill-chip missing">${esc(s)}</span>`).join('')+(job.skills?.length>5?`<span class="skill-chip more">+${Math.max(0,job.skills.length-5)} skills</span>`:'');
  return `<article class="job-card" data-card="${esc(job.id)}">
    <div class="job-card-head"><div class="company-profile">${mark(job)}<div class="company-data"><div class="company-name" title="${esc(job.company)}">${esc(job.company)}</div><div class="company-sector">${esc(job.company_sector)}</div></div></div><div class="match-score" title="Estimated fit—not a hiring prediction"><div class="score-ring" style="--ring-color:${tone};--ring-pct:${m.score}%"><strong>${m.score}%</strong></div><span class="match-label">SKILL FIT</span></div></div>
    <div class="job-badges"><span class="mini-badge industry-tag">${esc(job.company_sector||'Industry not specified')}</span>${job.region==='International'?`<span class="mini-badge region-tag">${esc((job.eligibility||'Verify eligibility').replace(' / Bangladesh eligible',''))}</span>`:''}${isNew?'<span class="mini-badge new">NEW</span>':''}${!jobIsOpen(job)?'<span class="mini-badge expired">EXPIRED · ARCHIVE</span>':job.vacancy_status==='older_unverified'?'<span class="mini-badge archived">OLDER · VERIFY</span>':''}${job.region==='International'&&job.eligibility_confidence==='unconfirmed'?'<span class="mini-badge archived">ELIGIBILITY UNKNOWN</span>':''}<span class="mini-badge">${esc(job.category)}</span>${/volunteer/i.test(job.employment_type||'')?'<span class="mini-badge volunteer">UNPAID VOLUNTEER</span>':''}${job.workplace==='Remote'?'<span class="mini-badge remote">REMOTE</span>':''}${left!==null&&left>=0&&left<=5?`<span class="mini-badge deadline">${left===0?'ENDS TODAY':left+'D LEFT'}</span>`:''}</div>
    <h3 class="job-title"><a href="#jobs" data-action="details" data-id="${esc(job.id)}">${esc(job.title)}</a></h3><p class="job-description">${esc(job.description||'Open the source listing for full job information and requirements.')}</p>
    <div class="job-skills">${chips||'<span class="skill-chip missing">Requirements: see original</span>'}</div><div class="job-spacer"></div>
    ${jobSourceRow(job)}
    <div class="job-meta"><span title="${esc(job.location)}">${svg('map')} ${esc(job.location)}</span><span>${svg('clock')} ${esc(job.posted_at?'Posted '+shortDate(job.posted_at):'Posted date unavailable')}</span>${job.deadline?`<span class="${left!==null&&left<=5?'ends-soon':''}">${svg('calendar')} Due ${esc(shortDate(job.deadline))}</span>`:`<span>${svg('calendar')} Deadline not stated</span>`}</div>
    <div class="job-footer"><button class="button button-outline" data-action="details" data-id="${esc(job.id)}">View role details ${svg('arrow')}</button><a class="button button-green" href="${esc(safeUrl(job.apply_url)||safeUrl(job.source_url)||'#')}" target="_blank" rel="noopener noreferrer" aria-label="Open posting or application for ${esc(job.title)}">${jobIsOpen(job)?'Apply / source':'Check archive'} ${svg('external')}</a><button class="icon-button ${state.saved.has(job.id)?'is-saved':''}" data-action="save" data-id="${esc(job.id)}" aria-label="${state.saved.has(job.id)?'Remove saved job':'Save job'}" title="${state.saved.has(job.id)?'Remove saved job':'Save job'}">${svg('bookmark')}</button></div>
  </article>`;
}
function emptyState(message='No openings match these filters.',hint='Try resetting filters or reducing your minimum match score.',showReset=true){return `<div class="empty-state"><span class="sidebar-mini-icon">${svg('search')}</span><h3>${esc(message)}</h3><p>${esc(hint)}</p>${showReset?'<button class="button button-outline" data-action="reset-filters">Reset filters</button>':''}</div>`;}
function renderJobs(){const data=getJobs();$('#jobsGrid').innerHTML=data.length?data.map(card).join(''):emptyState();$('#resultsCount').textContent=`${data.length} results`;$('#filterSummary').textContent=`${data.length} ${data.length===1?'role':'roles'} matching your filters`;$('#resultsFoot').textContent=data.length?`Showing ${data.length} matched job postings · Confirm availability before applying`:'';icons($('#jobsGrid'));}
function internationalJobs(){
  const q=state.intlQuery.trim().toLowerCase();const eligibility=state.intlEligibility;
  const jobs=state.jobs.filter(j=>{
    if(j.region!=='International'||(!state.intlIncludeExpired&&!jobIsOpen(j)))return false;
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
function renderSaved(){const data=state.jobs.filter(j=>state.saved.has(j.id)&&jobIsOpen(j)).sort((a,b)=>match(b).score-match(a).score);$('#savedGrid').innerHTML=data.length?data.map(card).join(''):emptyState('No saved roles yet.','Bookmark a job from the radar to add it to your private shortlist.',false);$('#savedSummary').textContent=`${data.length} saved ${data.length===1?'role':'roles'}`;$('#navSavedCount').textContent=state.saved.size;icons($('#savedGrid'));}
function renderMetrics(){const open=state.jobs.filter(j=>jobIsOpen(j)&&j.region!=='International');$('#metricTotal').textContent=open.length;$('#metricMatch').textContent=open.filter(j=>match(j).score>=70).length;$('#metricCompanies').textContent=new Set(open.map(j=>j.company.toLowerCase())).size;$('#metricSources').textContent=state.sources.length;$('#navJobsCount').textContent=open.length;$('#navSourcesCount').textContent=state.sources.length;$('#sideSourceCount').textContent=state.sources.length;$('#sideUpdated').textContent=(state.status.updated_at||'').slice(0,10)||'Not yet run';$('#sideEngine').textContent='FREE / HOURLY';$('#sourceTotal').textContent=state.sources.length;$('#sourceBanking').textContent=state.sources.filter(s=>s.sector==='Banking').length;$('#sourcePortals').textContent=state.sources.filter(s=>s.sector==='Job portal').length;$('#sourceChecked').textContent=state.status.official_career_targets_checked||'0';const stamp=(state.status.updated_at||'').slice(0,10);$('#topStatusText').textContent=stamp?`Updated ${stamp}`:'Dataset ready';
  const banner=$('#dataBanner');banner.classList.remove('warning');
  const providers=(state.status.source_health||[]).filter(x=>x.mode==='Free publisher feed');
  const published=providers.filter(x=>x.state==='ok').length;
  const feedErrors=providers.filter(x=>x.state==='error').length;
  const checked=Number(state.status.official_career_targets_checked||0);
  banner.innerHTML=`${svg('info')}<span><strong>Free-source intelligence / hourly.</strong> ${open.length} non-expired Bangladesh leads · ${(state.status.archived_expired||0)} expired records retained in archive · ${published} feeds updated · ${feedErrors} feed errors · ${checked} employer pages checked. ${stamp?`Last collection <strong>${esc(stamp)}</strong>.`:(auth.vaultMode()?'First collection runs at the next hourly GitHub Actions publish.':'First live collection begins when your local server starts.')} Jobs and eligibility must be confirmed on the original posting. No paid API keys required.</span>`;
  renderInternational();icons(banner);
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
  panel.classList.toggle('is-error',p.phase==='error');
  $('#progressTitle').textContent=running?'HOURLY SCAN IN PROGRESS':'HOURLY SOURCE SCANNER';
  $('#progressPhase').textContent=running?(' · '+String(p.phase||'checking').replaceAll('_',' ')):(p.phase==='completed'?' · Last scan completed':p.phase==='error'?' · Last scan interrupted':' · Ready for scheduled run');
  $('#progressPercent').textContent=percentage+'%';$('#progressFill').style.width=percentage+'%';
  $('#progressTrack').setAttribute('aria-valuenow',String(percentage));
  for(const [id,key] of [['progressChecked','checked'],['progressTotal','total'],['progressRemaining','remaining'],['progressOk','succeeded'],['progressBad','failed'],['progressLimited','partial'],['progressNewJobs','new_jobs']]){
    $('#'+id).textContent=Number(p[key]||0).toLocaleString();
  }
  $('#progressCurrent').textContent=running?(p.current_source||'Checking sources'):
    (p.phase==='completed'?'Last run finished · automatic hourly checks remain enabled':
    p.phase==='error'?'See the local Python terminal for the reason':(auth.vaultMode()?'Runs hourly in GitHub Actions; this view shows the last published snapshot':'Starts when the local Python server runs'));
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
      const label=!check?'No recorded check':check.result==='success'?'Career page fetched':check.result==='partial'?'Homepage only':'Failed fetch';
      const detail=check?`${check.at||''} · ${check.jobs_found||0} jobs · ${check.message||'No error'}`:'';
      return `<i class="health-square ${!check?'empty':check.result==='success'?'good':check.result==='partial'?'partial':'bad'}" title="${esc(label+' · '+detail)}" aria-label="${esc(label+' '+detail)}"></i>`;
    }).join('');
    const last=history.at(-1),status=isLinkOnly(src)?'link-only':(last?.result||'not scanned');
    const passCount=history.filter(h=>h.result==='success').length;const ratio=history.length?` · ${passCount}/${history.length} passed`:'';
    const detailHint=last?.message?last.message.slice(0,110):'';
    const statusLabel=status==='success'?`Success${ratio} · ${last.jobs_found} jobs`:status==='failed'?`Failed${ratio} · see tooltip`:status==='partial'?`Limited${ratio} · careers unverified`:status==='link-only'?'Link-only':'Awaiting scan';
    const quick=safeUrl(src.careers_url||src.website);
    const time=last?.at?`Checked ${new Date(last.at).toLocaleString()}`:'No fetch attempts recorded';
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
function renderSources(){const health=state.status.source_health||[];let list=state.sources.filter(s=>{const q=state.sourceQuery.toLowerCase();return (state.sourceSector==='all'||s.sector===state.sourceSector)&&(!q||[s.name,s.domain,s.sector].join(' ').toLowerCase().includes(q));});const count=list.length;list=list.slice(0,state.sourceLimit);$('#sourcesList').innerHTML=list.map(src=>{const info=health.find(x=>x.name===src.name);let label=src.mode==='search'?'Homepage discovery':'Source link / discovery',css='';if(src.mode==='public-api'){label='No-key publisher API';css='ok';}if(src.mode==='restricted'){label='Search links only';css='restricted';}else if(src.mode==='index'){label='Portal index only';css='restricted';}else if(src.mode==='career'){label='Career page / not checked';}if(info){label=info.state==='ok'?`Checked · ${info.jobs_found} matched`:info.state==='cached'?'Cached · scheduled':info.state==='partial'?'Company reachable · careers unverified':(info.message||'Blocked / unavailable');css=info.state==='ok'?'ok':info.state==='cached'?'':info.state==='partial'?'limited':'blocked';}const target=safeUrl(src.careers_url||src.website)||`https://www.google.com/search?q=${encodeURIComponent(src.name+' careers information security Bangladesh')}`;return `<div class="source-entry"><div><div class="source-name">${esc(src.name)}</div><div class="source-domain">${esc(src.sector)} / ${esc(src.domain)}</div></div><div class="source-status"><i class="status-dot ${css}"></i>${esc(label)}</div><div class="source-actions"><a class="source-visit" href="${esc(target||'#')}" target="_blank" rel="noopener noreferrer" aria-label="Open website for ${esc(src.name)}">Visit ↗</a></div></div>`;}).join('')||emptyState('No matching sources.','Try a different employer name or sector.',false);if(count>state.sourceLimit)$('#sourcesList').innerHTML+=`<div style="padding:15px;text-align:center;border-top:1px solid #273b2b"><button class="button button-outline" id="moreSources">Show more (${count-state.sourceLimit} remaining)</button></div>`;}
function renderProfile(){const p=state.profile;$('#profileTitle').value=p.title||'';$('#profileYears').value=p.years??'';$('#profileSkills').value=p.skills||'';$('#profileCerts').value=p.certs||'';$('#profileCategories').innerHTML=FOCUS.map((cat,i)=>`<label class="check-chip"><input type="checkbox" name="focusCategory" value="${esc(cat)}" ${p.categories?.includes(cat)?'checked':''}><span>${esc(cat)}</span></label>`).join('');$('#profileSectors').innerHTML=SECTORS.map(sec=>`<label class="check-chip"><input type="checkbox" name="focusSector" value="${esc(sec)}" ${p.sectors?.includes(sec)?'checked':''}><span>${esc(sec)}</span></label>`).join('');}
function renderAll(){fillFilters();renderMetrics();renderJobs();renderSaved();renderSources();renderSourceHealth();renderDiscovery();renderProgress();renderProfile();renderInternational();route();icons();}
function route(){let key=location.hash.replace('#','').split('/')[0]||'jobs';if(!['jobs','international','saved','sources','health','profile','about'].includes(key))key='jobs';state.page=key;$$('.page').forEach(p=>{p.hidden=p.id!==`page-${key}`;p.classList.toggle('active',!p.hidden);});$$('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===key));$('#currentBreadcrumb').textContent=({jobs:'BANGLADESH JOBS',international:'INTERNATIONAL JOBS',saved:'SAVED ROLES',sources:'SOURCE WATCHLIST',health:'SOURCE HEALTH',profile:'MATCH PROFILE',about:'ABOUT'}[key]);$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');if(window.innerWidth<800)window.scrollTo({top:0,behavior:'instant'});}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2700);}
function toggleSave(id){if(state.saved.has(id)){state.saved.delete(id);toast('Removed from saved opportunities');}else{state.saved.add(id);toast('Saved locally in your browser');}saveSaved();renderJobs();renderInternational();renderSaved();if(state.drawerId)renderDrawerContent(state.jobs.find(j=>j.id===state.drawerId));}
function drawerInfo(label,value){return `<div class="detail-cell"><small>${esc(label)}</small><strong>${esc(value??'Not specified')}</strong></div>`;}
function drawList(title,items){return `<section class="drawer-section"><h3>${esc(title)}</h3>${Array.isArray(items)&&items.length?`<ul>${items.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:`<p>Not available in the collected posting. Open the original listing for complete details.</p>`}</section>`;}
function renderDrawerContent(job){if(!job)return;const m=match(job),left=daysDelta(job.deadline),detail=String(job.description||''),img=safeUrl(job.poster_url),source=safeUrl(job.source_url),level=job.description_status||'Search excerpt';const experience=job.min_years===null||job.min_years===undefined?'Not stated':`${job.min_years}${job.max_years?'–'+job.max_years:'+'} years`;
  $('#drawerBody').innerHTML=`<div class="company-profile">${mark(job)}<div class="company-data"><div class="company-name">${esc(job.company)}</div><div class="company-sector">${esc(job.company_sector)} · ${esc(job.source)}</div></div></div>
    <h2 id="drawerTitle">${esc(job.title)}</h2><div class="drawer-subtitle">${esc(job.location)} · ${esc(job.employment_type)} · ${esc(job.workplace)}</div><div class="drawer-tags"><span>${esc(job.company_sector||'Industry not stated')}</span><span>${esc(job.region==='International'?(job.eligibility||'Verify eligibility'):'Bangladesh opportunity')}</span></div>
    <div class="drawer-tags"><span>${esc(job.category)}</span><span>${esc(job.seniority)}</span><span>${m.score}% estimated fit</span></div>
    <div class="drawer-detail-grid">${drawerInfo('POSTED',dateFmt(job.posted_at))}${drawerInfo('APPLICATION DEADLINE',job.deadline?`${dateFmt(job.deadline)}${left===0?' · Today':left>0&&left<=5?` · ${left}d left`:''}`:'Not stated')}${drawerInfo('EXPERIENCE',experience)}${drawerInfo('COMPENSATION',job.salary||'Not disclosed')}</div>
    <div class="drawer-match-detail"><h3>${m.score}% estimated alignment with your profile</h3><p>${esc(m.confidence)} · Calculated from advertised skills, entered experience and your preferred fields. ${state.profile.years===''?'Your years of experience are not yet set.':''}</p><div class="drawer-breakdown"><span>Skills ${m.breakdown.skills}%</span><span>Experience ${m.breakdown.experience}%</span><span>Focus ${m.breakdown.focus}%</span><span>Sector ${m.breakdown.sector}%</span></div><div class="drawer-tags" style="margin:14px 0 0">${m.matched.map(s=>`<span>✓ ${esc(s)}</span>`).join('')||'<span>No explicitly matching listed skills yet</span>'}${m.missing.slice(0,5).map(s=>`<span style="background:#2c271a;border-color:#5a4931;color:#e0c7a0">Gap · ${esc(s)}</span>`).join('')}</div></div>
    <section class="drawer-section"><h3>About this opportunity</h3><p>${esc(detail||'Full description is not available in the dataset. Visit the original posting to review job requirements.')}</p></section>
    ${drawList('Key responsibilities',job.responsibilities)}${drawList('Job requirements',job.requirements)}
    ${img?`<section class="drawer-section"><h3>Image included in job posting</h3><img class="drawer-poster" loading="lazy" src="${esc(img)}" alt="Posting image supplied by the original job source"></section>`:''}
    <section class="drawer-section"><h3>Source & completeness</h3>
      <div class="drawer-origin"><span>COLLECTED FROM</span><strong>${esc(jobSourceLabel(job))}</strong><small>${esc(jobSourceDomain(job))} · ${esc(job.source||'Unspecified collection method')}</small></div>
      <p class="drawer-source-note">${esc(level)} · ${esc(job.verification_level||'Source indexed')}. Third-party job portals may expose only excerpts. The original listing is authoritative for eligibility, application procedure, vacancy status and deadline.</p>
      ${source?`<a class="drawer-source-link" href="${esc(source)}" target="_blank" rel="noopener noreferrer">View original source posting ${svg('external')}</a>`:''}
      ${Number.isFinite(job.relevance_score)?`<p class="drawer-source-note">Cybersecurity relevance signal <strong>${esc(job.relevance_score)}/100</strong>${Array.isArray(job.matched_terms)&&job.matched_terms.length?` · matched: ${esc(job.matched_terms.slice(0,8).join(', '))}`:''}</p>`:''}
      ${Array.isArray(job.also_listed_on)&&job.also_listed_on.length?`<div class="drawer-also"><span>ALSO LISTED ON</span>${job.also_listed_on.map(x=>safeUrl(x.url)?`<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener noreferrer">${esc(x.source_name||jobSourceDomain({source_url:x.url}))} ${svg('external')}</a>`:'').join('')}</div>`:''}
    </section>`;
  $('#drawerFooter').innerHTML=`<button class="icon-button ${state.saved.has(job.id)?'is-saved':''}" data-action="save" data-id="${esc(job.id)}" title="Save opportunity" aria-label="Save opportunity">${svg('bookmark')}</button><button class="button button-muted" data-action="copy" data-id="${esc(job.id)}">${svg('copy')} Copy link</button><a class="button button-green" href="${esc(safeUrl(job.apply_url)||source||'#')}" target="_blank" rel="noopener noreferrer">Open posting / apply ${svg('external')}</a>`;icons($('#jobDrawer'));
}
function openDrawer(id){const job=state.jobs.find(j=>j.id===id);if(!job)return;state.drawerId=id;renderDrawerContent(job);$('#jobDrawer').classList.add('open');$('#jobDrawer').setAttribute('aria-hidden','false');$('#drawerBackdrop').classList.add('open');document.body.classList.add('lock-scroll');$('#closeDrawer').focus();}
function closeDrawer(){state.drawerId=null;$('#jobDrawer').classList.remove('open');$('#jobDrawer').setAttribute('aria-hidden','true');$('#drawerBackdrop').classList.remove('open');document.body.classList.remove('lock-scroll');}
function resetFilters(){state.filters={category:'All roles',q:'',sector:'all',location:'all',workplace:'all',source:'all',sourceSite:'all',sort:'match',minMatch:0,recent:false,deadline:false,verified:false,includeExpired:false};$('#jobSearch').value='';$('#sectorSelect').value='all';$('#locationSelect').value='all';$('#workplaceSelect').value='all';$('#sourceSelect').value='all';$('#sourceSiteSelect').value='all';$('#sortSelect').value='match';$('#matchRange').value='0';$('#matchRangeText').textContent='0%';$('#recentOnly').checked=false;$('#hasDeadline').checked=false;$('#hideUnverified').checked=false;$('#includeExpired').checked=false;fillFilters();renderJobs();}
function csvExport(){const fields=[['Title','title'],['Company','company'],['Sector','company_sector'],['Location','location'],['Workplace','workplace'],['Employment type','employment_type'],['Skill match %','_match'],['Posted','posted_at'],['Deadline','deadline'],['Experience years','min_years'],['Salary','salary'],['Required skills','_skills'],['Source platform','source'],['Original publisher','_source_name'],['Source website','_source_domain'],['Original source link','source_url'],['Apply link','apply_url']];const cell=s=>{let v=String(s??'');if(/^[\s]*[=+\-@\t\r]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};const rows=[fields.map(p=>cell(p[0])).join(',')];getJobs().forEach(j=>rows.push(fields.map(([,k])=>cell(k==='_match'?match(j).score:k==='_skills'?(j.skills||[]).join('; '):k==='_source_name'?jobSourceLabel(j):k==='_source_domain'?jobSourceDomain(j):j[k])).join(',')));const blob=new Blob(['\ufeff'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`cybercareers-bd-${bdToday()}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),3000);toast('CSV exported · spreadsheet-formula protection enabled');}
async function loadData(){const files=['data/jobs.json','data/sources.json','data/status.json','data/source_health.json','data/progress.json','data/search_queries.json'];const results=await Promise.all(files.map(async filename=>{if(auth.vaultMode()){const name=filename.slice(5);try{return await auth.loadJSON(name);}catch(e){if(/not in the encrypted dataset/.test(e.message))return name==='jobs.json'?{jobs:[]}:name.endsWith('queries.json')||name==='sources.json'?[]:{};throw e;}}const r=await fetch(filename+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(`Could not load ${filename}: ${r.status}`);return r.json();}));state.jobs=Array.isArray(results[0].jobs)?results[0].jobs:[];state.sources=Array.isArray(results[1])?results[1]:[];state.status=results[2]||{};state.sourceHealth=results[3]||{sources:{}};state.progress=results[4]||{};state.discoveryQueries=Array.isArray(results[5])?results[5]:[];}
// Local-only service discovery and refresh. Static GitHub Pages continues working.
let localRefreshTimer=null;
function showRefreshState(running){
  state.localRefreshing=running;
  const btn=$('#refreshJobsButton');
  if(!btn)return;
  btn.hidden=!state.localServer;
  btn.disabled=running;
  btn.innerHTML=running?`${svg('radar')} Checking sources…`:`${svg('radar')} Refresh jobs`;
  icons(btn);
}
async function fetchLocalRefreshStatus(){
  const r=await fetch('/api/refresh/status',{cache:'no-store'});
  if(!r.ok)throw Error('Local refresh status unavailable');
  return r.json();
}
async function reloadRefreshedData(){
  await loadData();
  fillFilters();
  const f=state.filters;
  for(const [id,key] of [['sectorSelect','sector'],['locationSelect','location'],['workplaceSelect','workplace'],['sourceSelect','source'],['sourceSiteSelect','sourceSite'],['sortSelect','sort']])$('#'+id).value=f[key];
  $('#intlSourceSelect').value=state.intlSource;$('#intlSourceSiteSelect').value=state.intlSourceSite;
  $('#sourceSector').value=state.sourceSector;
  renderMetrics();renderJobs();renderInternational();renderSaved();renderSources();renderSourceHealth();renderDiscovery();renderProgress();
  if(state.drawerId){const opened=state.jobs.find(j=>j.id===state.drawerId);if(opened)renderDrawerContent(opened);else closeDrawer();}
}
async function pollLocalRefresh(){
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
  if(!['localhost','127.0.0.1','[::1]'].includes(location.hostname))return;
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
          if(newest.updated_at && newest.updated_at!==state.status.updated_at){
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
function bind(){
  window.addEventListener('hashchange',route);
  document.addEventListener('click',async e=>{
    const act=e.target.closest('[data-action]');if(act){e.preventDefault();const id=act.dataset.id;if(act.dataset.action==='details')openDrawer(id);if(act.dataset.action==='save')toggleSave(id);if(act.dataset.action==='copy'){const j=state.jobs.find(j=>j.id===id);if(j){try{await navigator.clipboard.writeText(j.apply_url||j.source_url);toast('Job link copied');}catch{toast('Could not copy automatically · open the original posting');}}}if(act.dataset.action==='reset-filters')resetFilters();return;}
    const p=e.target.closest('[data-page-button]');if(p){location.hash=p.dataset.pageButton;return;}
    const category=e.target.closest('[data-category]');if(category){state.filters.category=category.dataset.category;$$('[data-category]').forEach(el=>el.classList.toggle('active',el===category));renderJobs();return;}
    if(e.target.closest('#moreSources')){state.sourceLimit+=50;renderSources();return;}
    if(e.target.closest('#healthMore')){state.healthLimit+=70;renderSourceHealth();return;}
    if(e.target.closest('#moreDiscovery')){state.queryLimit+=24;renderDiscovery();return;}
    const qtab=e.target.closest('[data-query-group]');if(qtab){state.queryGroup=qtab.dataset.queryGroup;state.queryLimit=12;renderDiscovery();return;}
    if(e.target.closest('#intlMoreButton')){state.intlLimit+=30;renderInternational();return;}
  });
  $('#exploreButton').addEventListener('click',()=>$('#openingsHeader').scrollIntoView({behavior:'smooth',block:'start'}));
  $('#clearFilters').addEventListener('click',resetFilters);$('#exportButton').addEventListener('click',csvExport);$('#refreshJobsButton').addEventListener('click',triggerLocalRefresh);
  $('#jobSearch').addEventListener('input',e=>{state.filters.q=e.target.value;renderJobs();});
  $('#intlSearch').addEventListener('input',e=>{state.intlQuery=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlEligibilitySelect').addEventListener('change',e=>{state.intlEligibility=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSourceSelect').addEventListener('change',e=>{state.intlSource=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSourceSiteSelect').addEventListener('change',e=>{state.intlSourceSite=e.target.value;state.intlLimit=30;renderInternational();});
  $('#intlSortSelect').addEventListener('change',e=>{state.intlSort=e.target.value;renderInternational();});
  $('#intlIncludeExpired').addEventListener('change',e=>{state.intlIncludeExpired=e.target.checked;renderInternational();});
  for(const [id,key] of [['sectorSelect','sector'],['locationSelect','location'],['workplaceSelect','workplace'],['sourceSelect','source'],['sourceSiteSelect','sourceSite'],['sortSelect','sort']])$('#'+id).addEventListener('change',e=>{state.filters[key]=e.target.value;renderJobs();});
  $('#matchRange').addEventListener('input',e=>{state.filters.minMatch=Number(e.target.value);$('#matchRangeText').textContent=e.target.value+'%';renderJobs();});
  for(const [id,key] of [['recentOnly','recent'],['hasDeadline','deadline'],['hideUnverified','verified'],['includeExpired','includeExpired']])$('#'+id).addEventListener('change',e=>{state.filters[key]=e.target.checked;renderJobs();});
  $('#sourceSearch').addEventListener('input',e=>{state.sourceQuery=e.target.value;state.sourceLimit=50;renderSources();});
  $('#sourceSector').addEventListener('change',e=>{state.sourceSector=e.target.value;state.sourceLimit=50;renderSources();});
  $('#healthSearch').addEventListener('input',e=>{state.healthQuery=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#healthSector').addEventListener('change',e=>{state.healthSector=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#healthFilter').addEventListener('change',e=>{state.healthFilter=e.target.value;state.healthLimit=70;renderSourceHealth();});
  $('#profileForm').addEventListener('submit',e=>{e.preventDefault();const years=$('#profileYears').value.trim();state.profile={title:$('#profileTitle').value.trim(),years:years===''?'':Math.min(45,Math.max(0,Number(years))),skills:$('#profileSkills').value.trim().slice(0,3000),certs:$('#profileCerts').value.trim().slice(0,350),categories:$$('input[name=focusCategory]:checked').map(el=>el.value),sectors:$$('input[name=focusSector]:checked').map(el=>el.value)};saveProfile();renderMetrics();renderJobs();renderInternational();renderSaved();toast('Profile saved privately · matches recalculated');location.hash='jobs';});
  $('#resetProfile').addEventListener('click',()=>{state.profile=structuredClone(DEFAULT_PROFILE);saveProfile();renderProfile();renderMetrics();renderJobs();renderInternational();renderSaved();toast('Profile restored to default focus areas');});
  $('#closeDrawer').addEventListener('click',closeDrawer);$('#drawerBackdrop').addEventListener('click',closeDrawer);
  $('#menuToggle').addEventListener('click',()=>{$('#sidebar').classList.add('open');$('#mobileShade').classList.add('open');});
  $('#mobileShade').addEventListener('click',()=>{$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();$('#sidebar').classList.remove('open');$('#mobileShade').classList.remove('open');}if((e.key==='/'||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'))&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();if(state.page==='international'){$('#intlSearch').focus();}else{location.hash='jobs';$('#jobSearch').focus();}}});
}
function showSession(){if(!auth.vaultMode())return;const who=auth.currentUser();$$('.vault-only').forEach(el=>el.hidden=false);$('#sessionUser').textContent=who?.name||'Signed in';$('#logoutButton').addEventListener('click',()=>auth.logout());const note=$('#sidePolicyNote');if(note)note.textContent='Encrypted dataset · unlocked in this browser only. Collection runs hourly in GitHub Actions.';}
async function init(){icons();if(auth.vaultMode()){document.documentElement.classList.add('cc-locked');if(!(await auth.restoreSession()))await auth.requireLogin();document.documentElement.classList.remove('cc-locked');}bind();try{await loadData();showSession();renderAll();if(!auth.vaultMode())await detectLocalServer();}catch(e){console.error(e);$('#jobsGrid').innerHTML=emptyState('Dataset could not be loaded.','Run the site from a local web server, or publish via GitHub Pages. See README for instructions.',false);$('#dataBanner').textContent='The job dataset was unavailable. Run python -m server.app from the project directory to use the local portal.';}}
init();
