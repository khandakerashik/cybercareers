/* Dependency-free application store regressions: node tests/applications_store.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.resolve(__dirname, '..', 'applications.js'), 'utf8');
let assertions = 0;
const check = (condition, message) => { assert.ok(condition, message); assertions++; };
const eq = (actual, expected, message) => { assert.deepEqual(actual, expected, message); assertions++; };
const throws = (fn, code) => { assert.throws(fn, error => error.code === code); assertions++; };

class MemoryStorage {
  constructor() { this.values = new Map(); this.failRead = false; this.failWrite = null; this.writes = 0; }
  getItem(key) { if (this.failRead) throw Object.assign(new Error('blocked'), {name:'SecurityError'}); return this.values.get(key) ?? null; }
  setItem(key, value) { if (this.failWrite) throw Object.assign(new Error('blocked'), {name:this.failWrite}); this.values.set(key, String(value)); this.writes++; }
}
const job = (id = 'collector-1', url = 'https://www.linkedin.com/jobs/view/1234567890/') => ({
  id, title:'Senior Application Security Engineer', company:'Example Bank PLC',
  source:'LinkedIn alert email', source_url:url, apply_url:url, deadline:'2027-01-01',
  location:'Dhaka, Bangladesh', region:'Bangladesh', category:'Application Security', company_sector:'Banking',
  vacancy_status:'unverified', description:'Publisher content must never be saved in the application snapshot.',
  requirements:['Do not copy this'], responsibilities:['Do not copy this'], salary:'Do not copy this',
});
const options = (storage, scope='https://example.com/careers/|user:one', now='2026-11-22T19:30:00.000Z') => ({storage,scope,now:()=>new Date(now)});

(async () => {
  const {createApplicationStore, ApplicationStoreError, NOTE_LIMIT} = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
  eq(NOTE_LIMIT,1000);
  check(new ApplicationStoreError('example','message') instanceof Error);
  const storage = new MemoryStorage();
  const store = createApplicationStore(options(storage));
  eq(store.list(),[]);
  const applied = store.mark(job());
  eq(applied.applied_at,'2026-11-22T19:30:00.000Z');
  eq(applied.applied_date,'2026-11-23','Default application date uses Bangladesh time across UTC midnight');
  eq(applied.note,'');
  eq(store.get(applied.id).id,applied.id);
  eq(store.get('collector-1').id,applied.id);
  check(!Object.hasOwn(applied.job,'description'));
  check(!Object.hasOwn(applied.job,'requirements'));
  eq(applied.job.vacancy_status,'unverified');
  const persisted = JSON.parse(storage.getItem(store.storageKey));
  check(!JSON.stringify(persisted).includes('Publisher content'));

  const originalTime = applied.applied_at;
  const note = 'Applied through the employer portal. Follow up next week.\nCV version 3.';
  eq(store.saveNote(applied.id,note).note,note);
  eq(store.mark(job()).note,note,'Idempotent mark preserves notes');
  eq(store.get(applied.id).applied_at,originalTime);
  const restored = createApplicationStore(options(storage));
  eq(restored.list().length,1);
  eq(restored.get(applied.id).note,note);
  eq(restored.get(applied.id).job.title,job().title,'Snapshot survives disappearance from live data');
  const altered = restored.get(applied.id);
  altered.job.title='Changed outside store'; altered.note='Not persisted';
  eq(restored.get(applied.id).job.title,job().title,'Returned records are detached');
  eq(restored.get(applied.id).note,note);

  const changedCollectorId = {...job('collector-v2'), title:'Sr. Application Security Engineer', company:'Example Bank Limited',
    source_url:'https://bd.linkedin.com/comm/jobs/view/application-security-1234567890/?trackingId=abc'};
  eq(restored.get(changedCollectorId).id,applied.id,'Canonical posting identity survives collector ID and harmless title/company formatting changes');
  eq(restored.mark(changedCollectorId).id,applied.id);
  eq(restored.get('collector-v2').id,applied.id);
  eq(restored.get(applied.id).job.id,'collector-1','Original snapshot identity is retained');
  eq(restored.get(applied.id).note,note);

  const distinct = restored.mark(job('collector-2','https://www.linkedin.com/jobs/view/9999999999/'));
  check(distinct.id !== applied.id,'Distinct portal requisitions remain distinct');
  eq(restored.list().length,2);
  const circularUrl='https://bank.example/careers/circular.pdf';
  const circleA=restored.mark({...job('shared-id',circularUrl),title:'SOC Analyst'});
  const circleB=restored.mark({...job('shared-id',circularUrl),title:'Penetration Tester'});
  check(circleA.id !== circleB.id,'A shared circular and reused collector ID do not collapse separate roles');
  eq(restored.get({...job('shared-id',circularUrl),title:'SOC Analyst'}).id,circleA.id);
  eq(restored.get({...job('shared-id',circularUrl),title:'Penetration Tester'}).id,circleB.id);
  eq(restored.get('shared-id'),null,'Ambiguous collector aliases do not silently pick another application');
  const ref1=restored.mark(job('ref1','https://bank.example/vacancy?ref=one'));
  const ref2=restored.mark(job('ref2','https://bank.example/vacancy?ref=two'));
  check(ref1.id !== ref2.id,'Generic requisition query parameters are retained');

  const otherUser=createApplicationStore(options(storage,'https://example.com/careers/|user:two'));
  const otherSite=createApplicationStore(options(storage,'https://example.com/other/|user:one'));
  const local=createApplicationStore(options(storage,'https://example.com/careers/|local'));
  eq(otherUser.list(),[]);eq(otherSite.list(),[]);eq(local.list(),[]);
  check(otherUser.storageKey !== store.storageKey && otherSite.storageKey !== store.storageKey);
  otherUser.mark(job());
  eq(otherUser.list().length,1);
  eq(local.list().length,0);

  restored.mark(job(),'2026-11-19');
  eq(restored.get(applied.id).applied_date,'2026-11-19');
  eq(restored.get(applied.id).applied_at,originalTime,'Editing the application date does not rewrite the original application action timestamp');
  throws(()=>restored.mark(job(),'2026-02-30'),'invalid_record');
  throws(()=>restored.saveNote(applied.id,'x'.repeat(NOTE_LIMIT+1)),'invalid_record');
  eq(restored.get(applied.id).note,note);
  eq(restored.saveNote(applied.id,'x'.repeat(NOTE_LIMIT)).note.length,NOTE_LIMIT);
  eq(restored.saveNote(applied.id,'').note,'','Empty notes are supported');

  // Separate store instances represent tabs with stale in-memory snapshots.
  const sharedStorage=new MemoryStorage(),tabA=createApplicationStore(options(sharedStorage)),tabB=createApplicationStore(options(sharedStorage));
  const a=tabA.mark(job('a','https://employer.example/jobs/a'));
  const b=tabB.mark(job('b','https://employer.example/jobs/b'));
  eq(tabB.list().length,2,'Mark rereads and preserves unrelated records from another tab');
  tabA.saveNote(a.id,'Tab A note');
  eq(tabA.list().length,2,'A stale-tab note save does not erase another application');
  eq(tabB.reload().find(record=>record.id===a.id).note,'Tab A note');
  const removed=tabB.remove(a.id);
  eq(removed.id,a.id);
  eq(tabA.reload().map(record=>record.id),[b.id]);
  throws(()=>tabA.saveNote(a.id,'Gone'),'not_found');
  eq(tabA.list().length,1);
  eq(tabB.mark(removed.job,removed.applied_date).id,removed.id,'Removed records can be marked again');

  const before=tabA.list(),rawBefore=sharedStorage.getItem(tabA.storageKey);
  sharedStorage.failWrite='QuotaExceededError';
  throws(()=>tabA.mark(job('new','https://employer.example/jobs/new')),'quota_exceeded');
  eq(tabA.list(),before,'Quota failure does not pretend the application was added');
  eq(sharedStorage.getItem(tabA.storageKey),rawBefore);
  throws(()=>tabA.saveNote(b.id,'Not saved'),'quota_exceeded');
  eq(tabA.get(b.id).note,'');
  throws(()=>tabA.remove(b.id),'quota_exceeded');
  check(tabA.get(b.id));
  sharedStorage.failWrite=null; sharedStorage.failRead=true;
  throws(()=>tabA.reload(),'storage_unavailable');
  throws(()=>tabA.mark(job('new','https://employer.example/jobs/new')),'storage_unavailable');
  eq(tabA.list(),before,'A blocked read leaves the last confirmed local memory intact');
  sharedStorage.failRead=false;

  const malformedStore=new MemoryStorage(),good=createApplicationStore(options(malformedStore));
  good.mark(job());
  malformedStore.values.set(good.storageKey,'{"version":1,"records":');
  const malformed=malformedStore.getItem(good.storageKey);
  throws(()=>createApplicationStore(options(malformedStore)),'corrupt_storage');
  throws(()=>good.saveNote(applied.id,'Must not clobber broken storage'),'corrupt_storage');
  eq(malformedStore.getItem(good.storageKey),malformed);
  const badVersion={...persisted,version:200};
  malformedStore.values.set(good.storageKey,JSON.stringify(badVersion));
  throws(()=>good.reload(),'corrupt_storage');
  const extraDescription=JSON.parse(JSON.stringify(persisted));extraDescription.records[0].job.description='Unexpected full publisher text';
  malformedStore.values.set(good.storageKey,JSON.stringify(extraDescription));
  throws(()=>good.reload(),'corrupt_storage');
  const duplicate=JSON.parse(JSON.stringify(persisted));duplicate.records.push(duplicate.records[0]);
  malformedStore.values.set(good.storageKey,JSON.stringify(duplicate));
  throws(()=>good.reload(),'corrupt_storage');
  malformedStore.values.set(good.storageKey,' '.repeat(2*1024*1024+1));
  throws(()=>good.reload(),'corrupt_storage');
  throws(()=>createApplicationStore(options(new MemoryStorage(),'x'.repeat(4001))),'invalid_record');
  throws(()=>createApplicationStore({storage:null,scope:'site|local'}),'storage_unavailable');
  throws(()=>createApplicationStore(null),'invalid_record');
  throws(()=>store.mark({...job(),source_url:'javascript:alert(1)'}),'invalid_record');
  throws(()=>store.mark({...job(),source_url:'https://user:password@example.com/jobs/1'}),'invalid_record');
  const precise=createApplicationStore(options(new MemoryStorage()));
  const common={...job('reused',circularUrl),title:'Security Engineer'};
  const applyA={...common,apply_url:'https://employer.example/apply?requisition=A'};
  const applyB={...common,apply_url:'https://employer.example/apply?requisition=B'};
  const appliedA=precise.mark(applyA),appliedB=precise.mark(applyB);
  check(appliedA.id !== appliedB.id,'Identically titled shared-circular vacancies keep distinct application destinations');
  eq(precise.get({...applyA,id:'regenerated-collector-id'}).id,appliedA.id);
  const reqA={...common,posting_identifier:'REQ-A'},reqB={...common,posting_identifier:'REQ-B'};
  const recordA=precise.mark(reqA),recordB=precise.mark(reqB);
  check(recordA.id !== recordB.id,'Real requisition identifiers are not discarded');
  eq(precise.get({...reqA,id:'changed-hash'}).id,recordA.id);
  eq(precise.get({...reqB,id:'changed-hash'}).id,recordB.id);
  eq(precise.mark({...reqA,id:'new-hash'}).id,recordA.id);
  eq(precise.list().length,4);
  const linked=precise.mark({...job(),apply_url:'https://employer.example/apply?session=old'});
  eq(precise.get({...job('new-collector-hash'),apply_url:'https://employer.example/apply?session=new'}).id,linked.id,
    'An exact portal posting ID is stable across an application-session URL change');
  const timeDeadline=precise.mark({...job('dated','https://employer.example/jobs/dated'),deadline:'2026-12-01T18:00:00+06:00'});
  eq(timeDeadline.job.deadline,'2026-12-01T18:00:00+06:00');
  eq(precise.get({...job(),source:'x'.repeat(1000)}),null,'Malformed live rows cannot poison an otherwise valid application store');
  eq(precise.get({...job(),source_url:'javascript:alert(1)'}),null);
  check(precise.get(linked.id),'Other saved records remain accessible after an invalid live lookup');
  throws(()=>precise.mark({...job(),source:'x'.repeat(1000)}),'invalid_record');
  eq(precise.reload().length,6);
  console.log(`${assertions} application-store assertions passed.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
