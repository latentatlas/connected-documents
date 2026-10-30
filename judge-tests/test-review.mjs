import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'connected-documents-'));
process.on('exit',()=>fs.rmSync(temp,{recursive:true,force:true}));
import {makeSession,checks,edit,accept,undo,exportFiles,zipBytes} from '../judge-build/review-core.mjs';
const root=new URL('../',import.meta.url);
const data=JSON.parse(fs.readFileSync(new URL('judge-build/review-data.json',root)));
const fixtures=JSON.parse(fs.readFileSync(new URL('judge-tests/review-parity-fixtures.json',root)));
for(const row of fixtures){
  const c=data.cases.find(c=>c.id===row.case_id),s=makeSession(c);s.draft=row.bodies;
  assert.deepEqual(checks(c,s).map(({name,passed})=>({name,passed})),row.expected_checks,row.case_id+':'+row.variant);
}
for(const c of data.cases){
  const s=makeSession(c);
  assert.throws(()=>accept(c,s),/Confirm/);
  assert.throws(()=>exportFiles(c,s),/Accept/);
  const wrong={...s,packageId:'another-project'};assert.equal(checks(c,wrong)[0].passed,false);
  if(c.work==='volunteer')assert.throws(()=>edit(c,s,'workshop-invite','overwrite'),/outside/);
  s.reviewed=true;accept(c,s);
  const files=exportFiles(c,s);
  for(const d of c.documents)assert.equal(files[d.id+'.txt'],s.accepted[d.id]);
  const meta=JSON.parse(files['review-manifest.json']);assert.equal(meta.new_inference,false);assert.equal(meta.case_id,c.id);
  fs.writeFileSync(path.join(temp,'export-'+c.id+'.zip'),zipBytes(files));
  assert.throws(()=>edit(c,s,c.documents[0].id,'late edit'),/Undo/);
  undo(s);assert.deepEqual(s.draft,Object.fromEntries(c.documents.map(d=>[d.id,d.before])));assert.equal(s.accepted,null);
  assert.throws(()=>exportFiles(c,s),/Accept/);
}
const c=data.cases.find(x=>x.id==='project-release'),s=makeSession(c);
edit(c,s,'work-plan',s.draft['work-plan'].replace('2026-11-14','2026-11-16'));s.reviewed=true;
assert.throws(()=>accept(c,s),/Resolve/);
assert.throws(()=>zipBytes({'../escape.txt':'no'}),/Unsafe/);
console.log(JSON.stringify({pythonParityVariants:fixtures.length,reviewFlows:data.cases.length,exportArchives:data.cases.length,identityGuards:true,reviewRequired:true,scopeGuard:true,fieldFailureBlocksAcceptance:true,noNewProviderCalls:true},null,2));
