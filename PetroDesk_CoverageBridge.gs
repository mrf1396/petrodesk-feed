/**
 * PetroDesk | Coverage Bridge v0.8 (Google Apps Script)
 * Add as a NEW .gs file to the existing project. Do not replace Code.gs.
 * No OpenAI API, no Telegram publishing, no login scraping.
 * The news links in GitHub must be PUBLIC. Do not publish the private Sheet.
 */
var PDCOVER8 = {
  sheetId:'1eUZ9wQL4bHsyh7WKPlqaNGGZubrNbp8sEFmhN0TA3VQ',
  // Set after creating the GitHub repo and successfully running its workflow:
  publicJsonUrl:'', // https://raw.githubusercontent.com/OWNER/REPO/main/docs/items.json
  feedName:'پایش اختصاصی خبر فارسی',
  bankName:'ورودی اخبار',
  reportName:'گزارش اختلاف خودکار',
  logName:'وضعیت پوشش منابع',
  maxImport:20,
  maxReport:160,
  freshnessHours:96
};

function pdCover8Get_(){
  if(!/^https:\/\/(raw\.githubusercontent\.com|[a-z0-9-]+\.github\.io)\//i.test(PDCOVER8.publicJsonUrl)){
    throw Error('Please set PDCOVER8.publicJsonUrl to a public GitHub raw JSON URL first.');
  }
  var r=UrlFetchApp.fetch(PDCOVER8.publicJsonUrl,{muteHttpExceptions:true,followRedirects:false});
  var code=r.getResponseCode();
  if(code!==200)throw Error('GitHub public feed HTTP '+code+'; check URL and workflow status');
  if(r.getContentText().length>1500000)throw Error('Feed too large');
  var x=JSON.parse(r.getContentText('UTF-8'));
  if(!x||x.schema!==1||!Array.isArray(x.items)||x.items.length>800)throw Error('Unexpected JSON schema');
  return x;
}
function pdCover8Normalize_(s){
  return String(s||'').replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/[\u200c\u200d]/g,' ')
   .replace(/[۰-۹]/g,function(c){return ''+(c.charCodeAt(0)-1776);})
   .replace(/[^\w\u0600-\u06FF\s]/g,' ').replace(/\s+/g,' ').toLowerCase().trim();
}
function pdCover8Link_(url){
  var m=String(url||'').trim().match(/^https:\/\/(?:www\.)?khabarfarsi\.com\/u\/(\d+)/i);
  return m?'https://khabarfarsi.com/u/'+m[1]:'';
}
function pdCover8Similarity_(x,y){
  var a=pdCover8Normalize_(x).split(' ').filter(function(z){return z.length>2;});
  var b=pdCover8Normalize_(y).split(' ').filter(function(z){return z.length>2;});
  if(!a.length||!b.length)return 0;
  var X={},Y={};a.forEach(function(z){X[z]=1;});b.forEach(function(z){Y[z]=1;});
  var common=0,all=0;
  Object.keys(X).forEach(function(z){all++;if(Y[z])common++;});
  Object.keys(Y).forEach(function(z){if(!X[z])all++;});
  return all?common/all:0;
}
function pdCover8LoadBank_(ss){
  var sh=ss.getSheetByName(PDCOVER8.bankName);
  if(!sh)throw Error('Missing bank sheet');
  var n=Math.max(0,sh.getLastRow()-1);
  var rows=n?sh.getRange(2,3,n,4).getDisplayValues():[];
  var urls={},titles={},titleArray=[];
  rows.forEach(function(row){
    [row[2],row[3]].forEach(function(u){var v=pdCover8Link_(u);if(v)urls[v]=true;});
    var key=pdCover8Normalize_(row[1]);if(key&&key.length>=18){titles[key]=true;titleArray.push(row[1]);}
  });
  return {sheet:sh,urls:urls,titles:titles,titleArray:titleArray};
}
function pdCover8Classify_(row,bank){
  var url=pdCover8Link_(row.url),title=pdCover8Normalize_(row.title);
  if(!url||title.length<12)return {status:'رد ساختاری',reason:'لینک یا عنوان خبری معتبر نیست'};
  if(bank.urls[url])return {status:'در بانک',reason:'لینک تجمیع‌کننده قبلاً ثبت شده'};
  if(bank.titles[title])return {status:'در بانک',reason:'تیتر عیناً در بانک وجود دارد'};
  // Suspected duplicate is not treated as confirmed. ChatGPT/human checks it.
  var max=0,near='';
  bank.titleArray.forEach(function(t){var n=pdCover8Similarity_(row.title,t);if(n>max){max=n;near=t;}});
  if(max>=0.61)return {status:'احتمال تکراری',reason:'شباهت واژگانی '+Math.round(max*100)+'٪ با «'+near.slice(0,90)+'»؛ نیازمند تطبیق رویداد'};
  return {status:'نامزد جامانده',reason:'لینک و عنوان متناظر در بانک یافت نشد؛ تازگی و اصل خبر بررسی شود'};
}
function pdCover8Rows_(){
  var ss=SpreadsheetApp.openById(PDCOVER8.sheetId),bank=pdCover8LoadBank_(ss),feed=pdCover8Get_();
  var items=feed.items.map(function(row){
    if(!row || !pdCover8Link_(row.url))return null;
    if(!row.first_seen || !/\d{4}-\d\d-\d\dT/.test(row.first_seen))return null;
    var ms=Date.parse(row.first_seen);if(!isFinite(ms))return null;
    if(Date.now()-ms>PDCOVER8.freshnessHours*3600000)return null;
    var val=pdCover8Classify_(row,bank);
    return {id:row.id||'',title:String(row.title||'').slice(0,260),url:pdCover8Link_(row.url),tags:(row.tags||[]).join('، '),seen:row.first_seen, status:val.status, reason:val.reason};
  }).filter(Boolean);
  return {feed:feed,items:items,ss:ss,bank:bank};
}
function pdCover8Probe(){
  var a=pdCover8Rows_(),counts={};a.items.forEach(function(x){counts[x.status]=(counts[x.status]||0)+1;});
  Logger.log('Public GitHub feed: '+a.feed.items.length+' archived; recent: '+a.items.length+'; counts '+JSON.stringify(counts));
  a.items.slice(0,5).forEach(function(x){Logger.log(x.status+' | '+x.title+' | '+x.url);});
  Logger.log('READ-ONLY: no Sheets changed.');
}
function pdCover8Import(){
  var lock=LockService.getScriptLock();if(!lock.tryLock(5000))return;
  try{
    var a=pdCover8Rows_();
    if(a.feed.status!=='ok')throw Error('No live page access in GitHub workflow; do not import stale archive as current news');
    var candidates=a.items.filter(function(x){return x.status==='نامزد جامانده';}).slice(0,PDCOVER8.maxImport);
    var dest=[];var seen={};
    candidates.forEach(function(x){
      if(seen[x.url])return;seen[x.url]=1;
      var k=Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,x.url).map(function(b){return ('0'+(b&255).toString(16)).slice(-2)}).join('').slice(0,14);
      dest.push([Utilities.getUuid(),new Date(),'خبر فارسی (برچسب موضوعی)',x.title,'',x.url,'','',
        'کشف از صفحه برچسب؛ متن کامل و تاریخ انتشار بررسی نشده',k,k,'برچسب: '+x.tags+' | زمان اولین کشف: '+x.seen]);
    });
    if(dest.length){
      var sh=a.bank.sheet,st=sh.getLastRow()+1;
      if(st+dest.length-1>sh.getMaxRows())sh.insertRowsAfter(sh.getMaxRows(),st+dest.length-1-sh.getMaxRows());
      sh.getRange(st,1,dest.length,12).setValues(dest);
    }
    Logger.log('Imported provisional title+link candidates: '+dest.length+' (no publishing)');
  } finally {lock.releaseLock();}
}
function pdCover8DailyReport(){
  var a=pdCover8Rows_(),sh=a.ss.getSheetByName(PDCOVER8.reportName);
  if(!sh)throw Error('Missing report sheet');
  var tz='Asia/Tehran',day=Utilities.formatDate(new Date(),tz,'yyyy-MM-dd');
  var seen={};if(sh.getLastRow()>1){
    sh.getRange(2,1,sh.getLastRow()-1,4).getDisplayValues().forEach(function(r){if(r[0]===day)seen[r[3]]=true;});
  }
  var add=[];
  a.items.slice(0,PDCOVER8.maxReport).forEach(function(x){if(seen[x.url])return;seen[x.url]=true;
    add.push([day,x.seen,x.title,x.url,x.tags,x.status,x.reason,
      'زمان انتشار اصلی تأیید نشده','فقط کشف؛ متن ناشر بررسی نشده','در انتظار']);
  });
  if(add.length){var start=sh.getLastRow()+1;if(start+add.length-1>sh.getMaxRows())sh.insertRowsAfter(sh.getMaxRows(),start+add.length-1-sh.getMaxRows());sh.getRange(start,1,add.length,10).setValues(add);}
  var st=a.ss.getSheetByName(PDCOVER8.logName);
  if(st){
    var counts={};a.items.forEach(function(x){counts[x.status]=(counts[x.status]||0)+1;});
    (a.feed.sources||[{tag:'GitHub عمومی',status:a.feed.status||'نامشخص',count:0,reason:'',url:''}]).forEach(function(src){
      st.appendRow([day,new Date(),src.tag,src.status,src.count||0,counts['نامزد جامانده']||0,counts['احتمال تکراری']||0,(src.reason||'')+' | زمان کشف، نه زمان انتشار؛ صاحب‌خبر خارج از این اتصال است']);
    });
  }
  Logger.log('Daily candidate comparison written: '+add.length+' | '+day);
}
function pdCover8Setup(){
  // Only after successful read-only probe + one manual daily report + quota review.
  pdCover8Pause();
  ScriptApp.newTrigger('pdCover8DailyReport').timeBased().everyDays(1).atHour(19).create();
  ScriptApp.newTrigger('pdCover8Import').timeBased().everyMinutes(30).create();
  Logger.log('Enabled: daily difference report + 30-minute candidate import. Existing triggers untouched. Check project timezone.');
}
function pdCover8Pause(){
  ScriptApp.getProjectTriggers().forEach(function(t){
    if(['pdCover8DailyReport','pdCover8Import'].indexOf(t.getHandlerFunction())>=0)ScriptApp.deleteTrigger(t);
  });
}
function pdCover8SelfTest(){
  var a=pdCover8Link_('https://khabarfarsi.com/u/123?utm_source=x')==='https://khabarfarsi.com/u/123';
  var b=pdCover8Link_('https://private.local/u/1')==='';
  var c=pdCover8Normalize_('پتروشيمي')===pdCover8Normalize_('پتروشیمی');
  var d=pdCover8Similarity_('رکورد تولید پتروشیمی تبریز','رکورد تولید پتروشیمی تبریز')===1;
  [a,b,c,d].forEach(function(x,i){Logger.log((x?'PASS ':'FAIL ')+i);});
  if([a,b,c,d].some(function(x){return !x;}))throw Error('PD coverage self-test failed');
  Logger.log('All 4 Coverage Bridge tests passed; no bank changes.');
}
