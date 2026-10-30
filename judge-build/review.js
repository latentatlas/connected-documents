'use strict';
// Shared, read-only presentation. The server binds facts and document identities.
window.ReviewView=(()=>{
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function panel(c,lang='tr'){
  if(!c||c.kind!=='source_derived_review_context_v1')return '';
  const T=(a,b)=>lang==='tr'?a:b, L=v=>escape(v[lang==='tr'?0:1]);
  return `<section class="review-context" aria-label="${T('Değişikliğin dayanağı','Basis for the change')}"><div class="review-heading"><div><p class="eyebrow">${T('NE DEĞİŞECEK · NEDEN · NE KORUNACAK','WHAT CHANGES · WHY · WHAT STAYS')}</p><h3>${c.mode==='preview'?T('Üretmeden önce değişikliğin kapsamı','Scope before generation'):c.mode==='saved'?T('Kayıtlı belgelerin dayanağı','Basis for the saved documents'):T('Bu taslağı neye göre incelemeli?','What should you check this draft against?')}</h3></div><span class="saved">${T('Kaynak bilgiden hesaplandı','Derived from source facts')}</span></div>
  <div class="review-facts"><div><h4>${T('Geçerli bilgi','Current facts')}</h4><p>${L(c.expected)}</p></div><div><h4>${T('Hesap ve karar dayanağı','Calculation and decision basis')}</h4>${c.calculations.map(v=>`<p>${L(v)}</p>`).join('')}</div><div><h4>${T('Korunacak içerik','Content to preserve')}</h4><p>${L(c.preserve)}</p></div></div>
  <div class="review-targets">${c.documents.map((d,i)=>`<button type="button" data-context-doc="${escape(d.id)}"><b>${i+1}. ${L(d.title)}</b><span>${d.targeted?T('Bilgileri karşılaştır','Compare the facts'):T('Kapsam dışında · koru','Outside scope · preserve')}</span>${d.changed===null?'':`<small>${d.changed?T('Önerilen metin değişti','Proposed text changed'):T('Metin aynı','Text is unchanged')}</small>`}</button>`).join('')}</div>
  <details class="source-records"><summary>${T('Dayanak olan kaynakları oku','Read the supporting sources')} (${c.sources.length})</summary><p>${T('Bu kurgusal örneğin kaynak metinleri. Açıklamalar bu bilgilere dayanır; modelin düşünce kaydı değildir.','Source texts for this fictional example. Explanations derive from these facts; they are not the model’s reasoning trace.')}</p>${c.sources.map(s=>`<article><strong>${escape(s.source_id)} · v${escape(s.version)}</strong><pre>${escape(s.text)}</pre></article>`).join('')}</details>
  <p class="review-limit">${T('Tarih, sayı, bağlantı ve korunacak metinler kontrol edilebilir. Kaynaksız iddia, belirsiz ifade ve anlam tutarlılığı için metni de okuyun.','Dates, counts, links and protected text can be checked. Read the text for unsupported claims, ambiguity and consistency of meaning.')}</p></section>`;
 }
 function document(c,id,lang='tr'){
  const d=c?.documents.find(x=>x.id===id);if(!d)return '';
  const T=(a,b)=>lang==='tr'?a:b,L=v=>escape(v[lang==='tr'?0:1]);
  return `<aside class="document-purpose"><div><strong>${T('Bu belge kim için?','Who uses this document?')}</strong><p>${L(d.audience)} · ${L(d.purpose)}</p></div><div><strong>${c.mode==='preview'?T('Yeni taslakta beklenen bilgi','Expected in the new draft'):T('Burada neyi kontrol etmeliyim?','What should I check here?')}</strong><p>${L(d.expected)}</p><small>${d.source_ids.length?T('Dayanak: ','Sources: ')+d.source_ids.map(escape).join(', '):T('Ayrı işin kuralları korunur.','Preserve the rules of this separate work.')}</small></div></aside>`;
 }
 return {panel,document};
})();
