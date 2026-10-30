// Recorded review test build. No inference, external storage or participant tracking.
export function requireValue(value, message) { if (!value) throw new Error(message); }
export function makeSession(example) {
  const ids=example.documents.map(d=>d.id);
  requireValue(new Set(ids).size===ids.length && ids.length>0,'Document identity mismatch');
  return {caseId:example.id, packageId:example.package_id, revision:0,
    draft:Object.fromEntries(example.documents.map(d=>[d.id,d.native])),
    accepted:null, previous:null, reviewed:false};
}
export function checks(example, session) {
  const rows=[];
  const check=(name,passed,detail)=>rows.push({name,passed:!!passed,detail});
  const ids=example.documents.map(d=>d.id);
  const identity=session.caseId===example.id && session.packageId===example.package_id
    && Object.keys(session.draft).length===ids.length && ids.every(id=>typeof session.draft[id]==='string');
  check('identity',identity,'Document and project identities match.');
  if(!identity)return rows;
  for(const [id, snippets] of Object.entries(example.protected)) {
    const old=example.documents.find(d=>d.id===id);
    check('protected:'+id,example.work==='volunteer'?session.draft[id]===old.before:snippets.every(s=>session.draft[id].includes(s)),
      'Preserve '+old.title+'.');
  }
  const facts=example.facts;
  if(example.work==='project') {
    const release=facts.release_date, qa=facts.qa_signoff;
    const date=new Date(qa+'T12:00:00Z');date.setUTCDate(date.getUTCDate()-3);
    const start=date.toISOString().slice(0,10);
    for(const id of ids) {
      const text=session.draft[id];
      check('dates:'+id,text.includes(release)&&text.includes(qa),'Release and sign-off dates: '+id+'.');
      const found=[...new Set(text.match(/\d{4}-\d{2}-\d{2}/g)||[])].sort();
      const allowed=[...new Set([release,qa,...(id==='work-plan'?[start]:[])])].sort();
      check('date_set:'+id,JSON.stringify(found)===JSON.stringify(allowed),'No stale or additional dates: '+id+'.');
    }
    check('qa_start',session.draft['work-plan'].includes(start),'QA begins '+start+'.');
  } else if(example.work==='research') {
    const rate=(100*facts.passed/facts.total).toFixed(1)+'%';
    for(const id of ids) {
      const text=session.draft[id];
      check('counts:'+id,['passed','total'].every(k=>new RegExp('(?<!\\d)'+facts[k]+'(?!\\d)').test(text))&&text.includes(rate),'Counts and '+rate+': '+id+'.');
      const expected=facts.passed*100>=facts.total*75?'threshold is met':'threshold is not met';
      const opposite=expected==='threshold is met'?'threshold is not met':'threshold is met';
      const decision=(text.split('DECISION:\n')[1]||'').split('\n\n')[0].toLowerCase();
      check('decision:'+id,decision.includes(expected)&&!decision.includes(opposite),'The decision follows the 75% threshold: '+id+'.');
    }
  } else {
    for(const id of ['volunteer-message','volunteer-faq']) {
      const text=session.draft[id];
      check('venue:'+id,[facts.venue,'2026-11-03','10:00','45'].every(x=>text.includes(x)),'Venue, date, time and duration: '+id+'.');
      check('old_venue:'+id,['North Hall','Cedar Hall','South Hall'].filter(v=>v!==facts.venue).every(v=>!text.includes(v)),'No obsolete venue: '+id+'.');
      const url='https://example.invalid/volunteer/'+(facts.registration==='paper'?'consent.pdf':'rsvp');
      check('link:'+id,text.includes(url),'Registration link: '+id+'. Read obligation and optionality separately.');
    }
  }
  return rows;
}
export function edit(example,session,id,text) {
  requireValue(!session.accepted,'Undo acceptance before editing this packet.');
  requireValue(example.documents.some(d=>d.id===id),'Unknown document.');
  requireValue(typeof text==='string'&&text.length<=12000,'Document is too long.');
  if(example.work==='volunteer'&&id in example.protected) {
    requireValue(text===example.documents.find(d=>d.id===id).before,'This document is outside the change scope.');
  }
  session.draft[id]=text;session.reviewed=false;
}
export function accept(example,session) {
  requireValue(!session.accepted,'This packet is already accepted.');
  requireValue(session.reviewed,'Confirm your content review first.');
  requireValue(checks(example,session).every(c=>c.passed),'Resolve the failed field checks first.');
  session.previous=Object.fromEntries(example.documents.map(d=>[d.id,d.before]));
  session.accepted={...session.draft};session.revision+=1;return session;
}
export function undo(session) {
  requireValue(!!session.accepted,'No accepted change to undo.');
  session.draft={...session.previous};session.accepted=null;session.previous=null;session.reviewed=false;session.revision+=1;
  return session;
}
export function exportFiles(example,session) {
  requireValue(session.accepted,'Accept the packet before downloading it.');
  requireValue(checks(example,{...session,draft:session.accepted}).every(c=>c.passed),'Accepted content no longer passes the field checks.');
  const files=Object.fromEntries(example.documents.map(d=>[d.id+'.txt',session.accepted[d.id]]));
  const meta={kind:'visitor_recorded_review_result',case_id:example.id,package_id:example.package_id,
    original_native_call:example.job_id,model:example.model,provider:example.provider,new_inference:false,
    user_review_confirmed:true,revision:session.revision,
    user_edited_documents:example.documents.filter(d=>session.accepted[d.id]!==d.native).map(d=>d.id),
    original_response_sha256:example.native_response_sha256,human_benefit_measured:false};
  files['review-manifest.json']=JSON.stringify(meta,null,2)+'\n';
  files['README.txt']='Your accepted fictional texts from a recorded review test build.\nNo new model request. Local edits are yours; they are not historical model output.\nField checks do not establish semantic correctness or measured user benefit.\n';
  return files;
}
function crc32(bytes) {
  let crc=0xffffffff;for(const value of bytes){crc^=value;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}
  return (crc^0xffffffff)>>>0;
}
// Standard uncompressed ZIP. Filenames are fixed ASCII document identities.
export function zipBytes(files) {
  const encoder=new TextEncoder(),parts=[],central=[];let offset=0,size=0;
  for(const [name,text] of Object.entries(files)) {
    requireValue(/^[A-Za-z0-9-]+\.(txt|json)$/.test(name),'Unsafe export filename.');
    const n=encoder.encode(name),b=encoder.encode(text),crc=crc32(b);
    const h=new Uint8Array(30+n.length),v=new DataView(h.buffer);
    v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint32(14,crc,true);
    v.setUint32(18,b.length,true);v.setUint32(22,b.length,true);v.setUint16(26,n.length,true);h.set(n,30);
    const c=new Uint8Array(46+n.length),d=new DataView(c.buffer);
    d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint32(16,crc,true);
    d.setUint32(20,b.length,true);d.setUint32(24,b.length,true);d.setUint16(28,n.length,true);d.setUint32(42,offset,true);c.set(n,46);
    parts.push(h,b);central.push(c);offset+=h.length+b.length;size+=c.length;
  }
  const end=new Uint8Array(22),e=new DataView(end.buffer);
  e.setUint32(0,0x06054b50,true);e.setUint16(8,central.length,true);e.setUint16(10,central.length,true);e.setUint32(12,size,true);e.setUint32(16,offset,true);
  const out=new Uint8Array(offset+size+end.length);let at=0;
  for(const part of [...parts,...central,end]){out.set(part,at);at+=part.length;}return out;
}
