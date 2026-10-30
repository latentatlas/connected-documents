import {makeSession,checks,edit,accept,undo,exportFiles,zipBytes} from './review-core.mjs';
const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={'project-release':'Project delivery · change the release date','research-corrected':'Research report · correct the result','volunteer-paper':'Volunteer onboarding · apply a group rule','volunteer-revoke':'Volunteer onboarding · revoke the rule','research-noop':'Research report · nothing has changed'};
let data,selected=new URLSearchParams(location.search).get('case')||'project-release',index=0,notice='';
const sessions=new Map();
const current=()=>data.cases.find(c=>c.id===selected);
const session=()=>{if(!sessions.has(selected))sessions.set(selected,makeSession(current()));return sessions.get(selected);};
function status(){
  const c=current(),s=session(),rows=checks(c,s),passed=rows.filter(x=>x.passed).length;
  $('#check-status').className='checks'+(passed===rows.length?'':' error');
  $('#check-status').innerHTML=`<strong>${passed} / ${rows.length} field checks passed</strong><p class="muted">These checks cover defined facts and protected text. Read for meaning, ambiguity and unsupported claims before accepting.</p><details><summary>See the checks</summary><ul class="check-list">${rows.map(r=>`<li>${r.passed?'✓':'!'} ${esc(r.detail)}</li>`).join('')}</ul></details>`;
  const counter=$('#edited-count');if(counter)counter.textContent=c.documents.filter(d=>s.draft[d.id]!==d.native).length;
  const button=$('#accept');if(button)button.disabled=!!s.accepted||!s.reviewed||passed!==rows.length;
}
function render(){
  const c=current(),s=session(),doc=c.documents[index],locked=c.work==='volunteer'&&doc.id in c.protected;
  const edited=c.documents.filter(d=>s.draft[d.id]!==d.native).length;
  $('#review-app').innerHTML=`<header class="topbar"><a class="brand" href="/">Connected Documents</a><nav><a href="/examples.html">Inspect recorded evidence</a><a href="/testing.html">Testing instructions</a></nav></header>
  <main class="page"><p class="eyebrow">TRY THE REVIEW WORKFLOW</p><h1>A proposed change.<br>Your decision.</h1>
  <p class="lead">Inspect every document, correct the draft if needed, then accept and download your packet.</p>
  <div class="banner"><strong>Recorded proposal · NVIDIA Nemotron 3 Super on Nebius Token Factory</strong>This free test build loads an actual saved model response. It makes no new model call. Your edits stay in this browser tab until you download them.</div>
  <div class="toolbar"><div><label for="case">Choose a fictional change</label><select id="case">${data.cases.map(x=>`<option value="${x.id}" ${x.id===selected?'selected':''}>${esc(names[x.id])}</option>`).join('')}</select></div><button id="reset">Restart this example</button></div>
  <div class="steps"><span>1 · Confirmed change</span><span class="active">2 · Review the proposal</span><span${s.accepted?' class="active"':''}>3 · Accept and download</span></div>
  ${window.ReviewView.panel(c.review_context,'en')}
  ${c.manual_edit_rounds?'<div class="notice"><strong>Watch the wording in this example.</strong> The original model response passed its field checks but kept an obsolete “optional” instruction. Inspect the meaning against the source. A recorded assistant correction is available below for comparison.</div>':''}
  ${notice?`<div class="status" role="status">${esc(notice)}</div>`:''}
  <div class="document-tabs" role="tablist" aria-label="Documents">${c.documents.map((d,i)=>`<button role="tab" aria-selected="${i===index}" data-doc="${i}">${i+1}. ${esc(d.title)}<small>${c.work==='volunteer'&&d.id in c.protected?'Preserved · outside scope':s.draft[d.id]===d.before?'Unchanged':'Proposed update'}</small></button>`).join('')}</div>
  ${window.ReviewView.document(c.review_context,doc.id,'en')}
  <div class="editor-grid"><article><h3>Before the change</h3><pre>${esc(doc.before)}</pre></article><article><h3>${s.accepted?'Your accepted text':locked?'Preserved text · read only':'Review and edit this proposal'}</h3><label class="muted" for="document-body">${locked?'This document is outside the change scope.':s.accepted?'Undo acceptance to reopen the review.':'Edit directly in this box. Field checks update as you type.'}</label><textarea id="document-body" maxlength="12000" ${locked||s.accepted?'readonly':''}>${esc(s.draft[doc.id])}</textarea></article></div>
  <div class="actions"><button id="previous" ${index===0?'disabled':''}>← Previous document</button><button id="next" ${index===c.documents.length-1?'disabled':''}>Next document →</button><span class="muted">Document ${index+1} of ${c.documents.length}</span></div>
  <div id="check-status" class="checks"></div>
  ${c.manual_edit_rounds&&!s.accepted?`<details class="reference"><summary>Compare the recorded assistant correction</summary><p>This is the separately saved historical correction. Loading it copies that text into your draft; it does not call a model or complete your review.</p><pre>${esc(c.documents[index].saved)}</pre><button id="reference">Load the recorded correction into this draft</button></details>`:''}
  <p class="recall"><span id="edited-count">${edited}</span> document(s) differ from the original model response. You can always inspect the unchanged historical record on the evidence page.</p>
  ${s.accepted?`<div class="status"><strong>Packet accepted in this browser tab.</strong> Your downloaded files will contain exactly these accepted texts.</div><div class="actions"><button id="download" class="primary">Download my accepted packet</button><button id="undo">Undo acceptance and restore the original packet</button></div>`:
  `<label class="review-confirm"><input id="reviewed" type="checkbox" ${s.reviewed?'checked':''}><span>I reviewed the changed text and the content to preserve. I understand that passing field checks does not guarantee correct meaning.</span></label><div class="actions"><button id="accept" class="primary">Accept my reviewed packet</button></div>`}
  <p class="privacy">Fictional documents only. No account, analytics, external data request or server-side save in this test build. Refreshing the page clears your edits. Download before leaving if you want to keep them. A live Nemotron runtime and setup instructions are included in the source package.</p></main>`;
  $('#case').onchange=e=>{selected=e.target.value;index=0;notice='';history.replaceState(null,'','?case='+selected);render();};
  $('#reset').onclick=()=>{sessions.set(selected,makeSession(c));index=0;notice='The original recorded proposal is loaded again.';render();};
  document.querySelectorAll('[data-doc]').forEach(b=>b.onclick=()=>{index=Number(b.dataset.doc);notice='';render();});
  document.querySelectorAll('[data-context-doc]').forEach(b=>b.onclick=()=>{index=c.documents.findIndex(d=>d.id===b.dataset.contextDoc);render();$('.editor-grid').scrollIntoView({block:'start'});});
  $('#previous').onclick=()=>{index--;render();};$('#next').onclick=()=>{index++;render();};
  $('#document-body').oninput=e=>{try{edit(c,s,doc.id,e.target.value);if($('#reviewed'))$('#reviewed').checked=false;status();}catch(error){notice=error.message;render();}};
  if($('#reviewed'))$('#reviewed').onchange=e=>{s.reviewed=e.target.checked;status();};
  if($('#accept'))$('#accept').onclick=()=>{try{accept(c,s);notice='Accepted. Review complete; your packet is ready to download.';}catch(error){notice=error.message;}render();};
  if($('#reference'))$('#reference').onclick=()=>{for(const d of c.documents)edit(c,s,d.id,d.saved);notice='Recorded assistant correction loaded. Review it, then confirm and accept.';render();};
  if($('#undo'))$('#undo').onclick=()=>{undo(s);notice='Acceptance undone. Original pre-change texts restored. Restart the example to review the recorded proposal again.';render();};
  if($('#download'))$('#download').onclick=()=>{try{const bytes=zipBytes(exportFiles(c,s));const url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));const a=document.createElement('a');a.href=url;a.download='connected-documents-'+c.id+'-my-review.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}catch(error){notice=error.message;render();}};
  status();
}
fetch('review-data.json').then(r=>{if(!r.ok)throw Error('The recorded examples could not be loaded.');return r.json();}).then(x=>{
  if(x.kind!=='recorded_review_build_v1'||x.new_provider_calls!==false)throw Error('Unexpected test-build identity.');
  data=x;if(!data.cases.some(c=>c.id===selected))selected='project-release';render();
}).catch(e=>{$('#review-app').innerHTML=`<main class="page"><h1>Examples unavailable</h1><p>${esc(e.message)}</p><a href="/">Return to the overview</a></main>`;});
