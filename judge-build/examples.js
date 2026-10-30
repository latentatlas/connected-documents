'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requestedLanguage=new URLSearchParams(location.search).get('lang');
let lang=['tr','en'].includes(requestedLanguage)?requestedLanguage:['tr','en'].includes(localStorage.getItem('cw-language'))?localStorage.getItem('cw-language'):'en';
let records, current='project-release', docIndex=0, phase='native';
const T=(tr,en)=>lang==='tr'?tr:en;
const labels={project:['Proje teslimi','Project delivery'],research:['Araştırma raporu','Research report'],volunteer:['Gönüllü katılımı','Volunteer onboarding']};
const copy={
 'project-release':{
  title:['Bir tarih değiştiğinde, üç belge birlikte güncellenir.','One date change reaches three connected documents.'],
  tab:['Teslim tarihini değiştir','Change a release date'],
  change:['Teslim 19 Kasım, kalite onayı 17 Kasım. Kalite çalışması üç gün önce başlamalı.','Release: November 19. QA sign-off: November 17. QA must start three days earlier.'],
  keep:['İşin kapsamı, sorumluları ve kapsam dışı özellikler.','Scope, owners and excluded features.'],
  result:['Proje özeti, iş planı ve devir notundaki tarihler birlikte güncellendi. Taslak metninde düzeltme yapılmadı.','Dates changed across the brief, work plan and handoff. No draft text corrections were made.'],
  docs:[['Proje özeti','Project brief'],['İş planı','Work plan'],['Devir notu','Handoff note']]
 },
 'research-corrected':{
  title:['Sayı değişince, ona bağlı yorum da değişir.','When a count changes, its conclusion changes too.'],
  tab:['Araştırma sonucunu düzelt','Correct the research result'],
  change:['Aynı kurgusal çalışmada sonuç 26/40 yerine 33/40. Yeni oran %82,5; %75 eşiği karşılanıyor.','The same fictional study changes from 26/40 to 33/40. The rate is now 82.5%, meeting the 75% threshold.'],
  keep:['Araştırma yöntemi, sınırlılıklar ve genelleme yapılmaması.','Method, limitations and the restriction on general claims.'],
  result:['Sayı, yüzde ve eşik kararı üç belgede birlikte güncellendi. Taslak metninde düzeltme yapılmadı.','The count, percentage and threshold decision changed in all three documents. No draft text corrections were made.'],
  docs:[['Sonuç notu','Result note'],['İlerleme özeti','Progress brief'],['Sunum notları','Speaking notes']]
 },
 'research-noop':{
  title:['Yeni bilgi yoksa, doğru belgeler aynı kalır.','When nothing has changed, correct documents stay intact.'],
  tab:['Güncel belgeleri tekrar kontrol et','Check the current documents again'],
  change:['Kaydedilmiş 33/40 sonucu yeniden verildi. Kaynakta yeni bir değişiklik yok.','The saved 33/40 result was supplied again. There was no new source change.'],
  keep:['Üç belgenin tamamı, kelimesi kelimesine.','All three documents, word for word.'],
  result:['Nemotron değişiklik önermedi. Yeni belge sürümü oluşturulmadı.','Nemotron proposed no edits. No new document revision was created.'],
  docs:[['Sonuç notu','Result note'],['İlerleme özeti','Progress brief'],['Sunum notları','Speaking notes']]
 },
 'volunteer-paper':{
  title:['Bir gruba özel karar, diğer işlere taşınmaz.','A group-specific decision stays within that group.'],
  tab:['Gruba özel kural koy','Apply a group-specific rule'],
  change:['Gönüllüler North Hall’da buluşacak. Yalnız bu grup imzalı kâğıt onay getirecek; mobil kayıt isteğe bağlı.','Volunteers meet in North Hall. Only this group must bring signed paper consent; mobile RSVP is optional.'],
  keep:['Ekibin iç kontrol listesi ve başka etkinliğin daveti.','The internal coordinator checklist and a different event’s invitation.'],
  result:['İki katılımcı belgesi, tam form bağlantılarıyla güncellendi. Diğer iki belge aynı kaldı. Düzeltme gerekmedi.','Two participant documents changed, including the full form URLs. The other two stayed intact. No correction was needed.'],
  docs:[['Gönüllü daveti','Volunteer invitation'],['Sık sorulan sorular','Volunteer FAQ'],['Ekibin kontrol listesi','Internal checklist'],['Başka etkinliğin daveti','Other event invitation']]
 },
 'volunteer-revoke':{
  title:['Kararı geri alırken, eski kuraldan kalanları gör.','When a decision is revoked, inspect what remains.'],
  tab:['Özel kuralı geri al','Revoke the special rule'],
  change:['Gönüllüler Cedar Hall’a döndü. Kâğıt onay istisnası kaldırıldı; telefondan kayıt ve çıktı gerektirmeyen varsayılan geri geldi.','Volunteers return to Cedar Hall. Revoke the paper-consent exception and restore phone-friendly registration with no participant printing.'],
  keep:['Ekibin iç kontrol listesi ve başka etkinliğin daveti.','The internal coordinator checklist and a different event’s invitation.'],
  result:['Bağlantılar doğruydu, fakat eski “isteğe bağlı” ifadesi kaldı. Asistan iki metni tek turda netleştirdi. İlk model yanıtı aşağıda ayrı tutuluyor.','The URLs were correct, but the old “optional” wording remained. An assistant clarified two texts in one correction round. The original model response remains separate below.'],
  docs:[['Gönüllü daveti','Volunteer invitation'],['Sık sorulan sorular','Volunteer FAQ'],['Ekibin kontrol listesi','Internal checklist'],['Başka etkinliğin daveti','Other event invitation']]
 }
};
const outcomeLabels={blocked:['Kabul engellendi: aynı metinli düzenleme','Blocked: identical-body edit'],repaired:['Asistan düzeltmesiyle kaydedildi','Saved after assistant correction'],unchanged:['Değişiklik önerilmedi','No change proposed'],accepted_without_edits:['Taslak düzeltmesiz kaydedildi','Saved without draft edits']};
const text=pair=>pair[lang==='tr'?0:1];
function lines(value,other,kind){const old=new Set(other.split('\n'));return value.split('\n').map(l=>`<span class="${l&&!old.has(l)?kind:''}">${esc(l)||' '}</span>`).join('');}
function choose(id){if(!copy[id])return;current=id;docIndex=0;phase='native';history.replaceState(null,'','#'+id);render();}
function render(){
 const c=records.cases.find(x=>x.id===current),m=copy[current],d=c.documents[docIndex],after=d[phase],repaired=c.manual_edit_rounds>0;
 document.documentElement.lang=lang;document.title=T('Bağlı belgeler · Gerçek model örnekleri','Connected documents · Recorded model examples');
 $('#examples').innerHTML=`<header><a class="brand" href="/">${T('Bağlı belgeler','Connected documents')}<span>${T('Gerçek model örnekleri','Recorded model examples')}</span></a><div class="header-actions"><a href="${records.workspace_url?'/':'/review.html'}" class="workspace-link">${records.workspace_url?T('Çalışma alanını aç','Open workspace'):T('Ürünü dene','Try the review')} ↗</a>${records.workspace_url?`<a href="/trial" class="workspace-link">${T('Kısa kullanıcı denemesi','Short user study')}</a>`:''}<button id="language" class="plain">${T('English','Türkçe')}</button></div></header>
 <main class="example-main"><section class="example-intro"><p class="eyebrow">${T('ÜÇ FARKLI İŞTE AYNI İHTİYAÇ','ONE NEED ACROSS THREE KINDS OF WORK')}</p><h1>${T('Bilgi değişir.<br>Belgeler birbirini tutmalı.','Facts change.<br>Your documents should still agree.')}</h1><p>${T('Aynı bilgiyi birden fazla belgede tutan ekipler için: ilgili metinleri birlikte güncelle, diğerlerini koru, sonucu inceleyerek kaydet.','For teams maintaining the same facts in several documents: update related text together, preserve the rest, then review and save.')}</p><div class="recorded-label"><strong>NVIDIA Nemotron 3 Super · Nebius Token Factory</strong>${T('Kaydedilmiş gerçek Nemotron yanıtları · Bu ekran yeni model isteği göndermez.','Recorded real Nemotron responses · This page makes no new model call.')}</div></section>
 <nav class="work-tabs" aria-label="${T('Örnek iş türü','Example work type')}">${Object.entries(labels).map(([id,label],i)=>`<button class="work-tab ${c.work===id?'active':''}" data-work="${id}" aria-pressed="${c.work===id}"><span>0${i+1}</span>${text(label)}</button>`).join('')}</nav>
 <section class="example-card"><nav class="case-tabs" aria-label="${T('Örnek durum','Example condition')}">${records.cases.filter(x=>x.work===c.work).map(x=>`<button data-case="${x.id}" class="${x.id===current?'selected':''}" aria-pressed="${x.id===current}">${text(copy[x.id].tab)}</button>`).join('')}</nav>
 <h2>${text(m.title)}</h2><div class="context-grid"><div><h3>1 · ${T('Ne değişti?','What changed?')}</h3><p>${text(m.change)}</p></div><div><h3>2 · ${T('Ne korunmalı?','What must stay?')}</h3><p>${text(m.keep)}</p></div><div><h3>3 · ${T('Ne oldu?','What happened?')}</h3><p>${text(m.result)}</p></div></div>
 <div class="example-result ${repaired?'needs-review':''}"><strong>${c.changed_documents} / ${c.documents.length} ${T('belge için değişiklik önerildi','documents received proposed edits')}</strong><span>${repaired?T('İki belgede asistan düzeltmesi var','Assistant corrections in two documents'):c.action==='noop'?T('Kayıtlı metinler değişmedi','Saved texts stayed unchanged'):T('Taslak düzeltmesi: 0 · Asistan incelemesi','Draft corrections: 0 · Assistant review')}</span></div>
 ${repaired?`<p class="semantic-warning">${T('9/9 alan kontrolü geçtiği hâlde anlamı ayrıca düzeltmek gerekti. “Modelin ilk yanıtı” ile “Düzeltme sonrası”nı karşılaştırabilirsiniz.','All 9 field checks passed, but the meaning still needed correction. Compare “Original model response” with “After correction”.')}</p>`:''}
 ${ReviewView.panel(c.review_context,lang)}
 <div class="document-header"><h3>${T('Değişikliği belgelerde gör','Inspect the change in the documents')}</h3><span>${docIndex+1} / ${c.documents.length}</span></div>
 <nav class="doc-tabs" aria-label="${T('Belge seçimi','Document selection')}">${c.documents.map((x,i)=>`<button data-doc="${i}" class="${docIndex===i?'selected':''}" aria-pressed="${docIndex===i}"><b>${i+1}.</b>${text(m.docs[i])}<small>${x.changed?T('Değişti','Changed'):T('Aynı','Unchanged')}</small></button>`).join('')}</nav>
 ${repaired?`<div class="phase-tabs" aria-label="${T('Yanıt aşaması','Response stage')}"><button data-phase="native" aria-pressed="${phase==='native'}" class="${phase==='native'?'selected':''}">${T('Modelin ilk yanıtı','Original model response')}</button><button data-phase="saved" aria-pressed="${phase==='saved'}" class="${phase==='saved'?'selected':''}">${T('Düzeltme sonrası','After correction')}</button></div>`:''}
 ${ReviewView.document(c.review_context,d.id,lang)}
 <div class="document-grid compare"><article><div class="column-label">${T('Değişiklikten önce','Before the change')}</div><pre class="document-body">${lines(d.before,after,'removed')}</pre></article><article><div class="column-label">${phase==='native'?T('Nemotron’un ilk yanıtı','Original Nemotron response'):T('Asistan düzeltmesinden sonra kaydedilen','Saved after assistant correction')}<span>${!d.changed?T('Aynı metin','Unchanged text'):''}</span></div><pre class="document-body">${lines(after,d.before,'added')}</pre></article></div>
 <div class="doc-navigation"><button id="previous" ${docIndex===0?'disabled':''}>← ${T('Önceki belge','Previous document')}</button><button id="next" ${docIndex===c.documents.length-1?'disabled':''}>${T('Sonraki belge','Next document')} →</button></div>
 <p class="reading-note">${T('Belge metinleri İngilizcedir. Renkler satır farklarını gösterir; doğruluk kararı değildir. Bu örnekleri asistan inceledi; bağımsız kullanıcı denemesi yapılmadı.','Document texts are English. Colors show line differences, not correctness. An assistant reviewed these examples; they are not an independent user study.')}</p>
 ${c.packet?`<div class="output"><div><h3>${T('Bu örnekte kaydedilen belge paketi','The document packet saved in this example')}</h3><p>${repaired?T('Asistan düzeltmelerini içerir. İlk model yanıtıyla karıştırılmaz.','Includes assistant corrections. It is distinct from the original model response.'):T('İncelenen taslak metinleri, ayrı belge dosyaları olarak.','The reviewed draft texts, as separate document files.')}</p></div><a class="download" href="/example-packets/${c.packet}">${T('Örnek paketi indir','Download example packet')} ↓</a></div>`:''}
 <details class="receipt"><summary>${T('Model ve kayıt bilgisi','Model and record details')}</summary><dl><dt>${T('Model','Model')}</dt><dd>${esc(c.model)}</dd><dt>${T('Sağlayıcı','Provider')}</dt><dd>Nebius Token Factory</dd><dt>${T('Akıl yürütme','Reasoning')}</dt><dd>${c.reasoning_enabled?T('Açık','Enabled'):T('Bu eski çağrıda kapalı','Disabled in this earlier call')}</dd><dt>${T('Gerçek çağrı kaydı','Recorded call')}</dt><dd>${esc(c.job_id)}</dd><dt>${T('Tamamlanma zamanı (UTC)','Completion time (UTC)')}</dt><dd>${esc(c.completed_at)}</dd><dt>${T('İlk yanıtın alan kontrolleri','Original field checks')}</dt><dd>${c.checks_passed}/${c.checks_total} · ${T('Anlamsal doğruluk garantisi değildir','Not a guarantee of semantic correctness')}</dd></dl></details>
 </section>
 <section class="evidence-overview"><h2>${T('Gördüğünüz örneklerin sınırı','What these examples establish')}</h2><p>${T('Çalışan akış: değişikliği bağlı belgelere taşıma, diğer içeriği koruma ve inceleme sonrasında ayrı dosyalar üretme. Daha az hata, daha az kontrol yükü veya zaman tasarrufu henüz karşılaştırmalı olarak gösterilmedi.','Working behavior: carry a change across connected documents, preserve other content, and produce separate files after review. Fewer errors, less checking effort and time savings have not yet been demonstrated comparatively.')}</p><details id="all-calls"><summary>${T('11 gerçek çağrının tamamını gör — başarısızlar dahil','View all 11 real calls — including failures')}</summary><p>${T('Bunlar aynı geliştiricinin hazırladığı gelişim kontrolleridir; genel başarı oranı veya bağımsız örneklem değildir.','These are authored development checks, not a general success rate or an independent sample.')}</p><div class="table-scroll"><table><thead><tr><th>#</th><th>${T('İş','Work')}</th><th>${T('Gözlenen sonuç','Observed outcome')}</th><th>${T('Akıl yürütme','Reasoning')}</th></tr></thead><tbody>${records.all_calls.map((r,i)=>`<tr><td>${i+1}</td><td>${text(labels[r.work])}</td><td>${text(outcomeLabels[r.outcome])}</td><td>${r.contract==='nebius_documents_v3_reasoning'?T('Açık','Enabled'):T('Kapalı','Disabled')}</td></tr>`).join('')}</tbody></table></div></details></section>
 <footer>${T('Gerçek müşteri verisi içermez. Önceden hazırlanmış kurgusal belgeler kullanılır; rastgele dosya yükleme ve bilinmeyen belge ilişkilerini keşfetme henüz bu prototipte yoktur.','No real customer data. This prototype uses prepared fictional documents; arbitrary file upload and discovery of unknown document relationships are not implemented.')}</footer></main>`;
 $('#language').onclick=()=>{lang=lang==='tr'?'en':'tr';localStorage.setItem('cw-language',lang);render();};
 document.querySelectorAll('[data-work]').forEach(b=>b.onclick=()=>choose(records.cases.find(c=>c.work===b.dataset.work).id));
 document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>choose(b.dataset.case));
 document.querySelectorAll('[data-doc]').forEach(b=>b.onclick=()=>{docIndex=Number(b.dataset.doc);render();});
 document.querySelectorAll('[data-phase]').forEach(b=>b.onclick=()=>{phase=b.dataset.phase;render();});
 document.querySelectorAll('[data-context-doc]').forEach(b=>b.onclick=()=>{docIndex=c.documents.findIndex(d=>d.id===b.dataset.contextDoc);render();document.querySelector('.document-purpose').scrollIntoView({block:'start',behavior:'smooth'});});
 $('#previous').onclick=()=>{docIndex--;render();};$('#next').onclick=()=>{docIndex++;render();};
}
window.addEventListener('hashchange',()=>{if(records)choose(copy[location.hash.slice(1)]?location.hash.slice(1):'project-release');});
fetch('/examples.json').then(r=>{if(!r.ok)throw Error('EXAMPLES_UNAVAILABLE');return r.json();}).then(x=>{
 if(x.kind!=='recorded_native_fictional_walkthrough'||x.live_inference!==false)throw Error('EXAMPLE_IDENTITY');
 records=x;choose(copy[location.hash.slice(1)]?location.hash.slice(1):current);
}).catch(()=>{$('#examples').textContent=T('Doğrulanmış örnekler yüklenemedi. Çalışma alanını / adresinden açabilirsiniz.','Verified examples could not be loaded. Open the workspace at /.');});
