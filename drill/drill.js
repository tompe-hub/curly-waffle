/* Mandarin drill: listen, answer, retell, get graded. Ten minutes.
   Mounts into any element. Talks to Claude through the page's `sample`
   capability and logs each run through the host page's cloud adapter
   ({ready, push}) and store ({get, set}). Documents are
   {kind:'drill', key:'YYYY-MM-DD', stamp, runs:[...]}, saved as 'd-<key>'. */
(function(){
  var TOPICS=[
    ['strait','Cross-strait','两岸关系：北京与台北的互动、军事压力、灰色地带行动、外交承认'],
    ['scs','South China Sea','南海：菲律宾与中国的对峙、仲裁裁决、海警执法、东盟行为准则谈判'],
    ['controls','Export controls','出口管制与制裁：美国对华芯片管制、中国的反制清单、不可靠实体清单、反外国制裁法'],
    ['economy','China’s economy','中国经济：房地产调整、地方债务、消费不足、产能过剩与贸易摩擦'],
    ['asean','Singapore and ASEAN','新加坡与东盟：在中美之间的平衡、供应链转移、区域经济一体化'],
    ['chips','Chips and AI','半导体与人工智能：台积电、先进制程、算力竞争、各国产业政策']
  ];
  /* The planner's desk rotation: Monday Zaobao, Wednesday Caixin, Friday a Taiwan source */
  var OUTLET={
    1:['联合早报','Zaobao','simp','新加坡《联合早报》的评论与分析版'],
    3:['财新','Caixin','simp','《财新》的经济与政策报道'],
    5:['報導者','The Reporter','trad','台湾《报导者》或《天下杂志》的深度报道']
  };
  var DEFAULT_OUTLET=['新闻分析','News analysis','simp','华文主流媒体的新闻分析'];
  var KEY='wk-drill-v1';
  var CSS=[
    '.dr{border-left:4px solid var(--mandarin)}',
    '.dr h3{display:flex;justify-content:space-between;align-items:baseline;gap:10px}',
    '.dr-streak{display:flex;align-items:baseline;gap:10px;margin:6px 0 4px}',
    '.dr-streak b{font-family:var(--head);font-weight:700;font-size:2.6rem;line-height:1;font-variant-numeric:tabular-nums}',
    '.dr-streak span{color:var(--soft);font-size:.95rem}',
    '.dr-strip{display:grid;grid-template-columns:repeat(14,1fr);gap:4px;margin:8px 0 4px}',
    '.dr-strip i{display:block;height:22px;border-radius:4px;border:1.5px solid var(--line);font-style:normal;font-size:.7rem;line-height:19px;text-align:center;color:var(--soft)}',
    '.dr-strip i.done{background:var(--mandarin);border-color:var(--mandarin);color:var(--paper)}',
    '.dr-strip i.we{border-style:dotted}',
    '.dr-strip i.today{border-color:var(--ink);border-style:dashed}',
    '.dr-key{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--soft);font-size:.85rem;margin:0 0 10px}',
    '.dr-row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}',
    '.dr .plain{min-height:40px}',
    '.dr .go{background:var(--mandarin);border-color:var(--mandarin);color:var(--paper)}',
    '.dr .plain[disabled]{opacity:.45;cursor:default}',
    '.dr .chip{background:transparent;border:1.5px solid var(--line);border-radius:999px;padding:6px 12px;cursor:pointer;font-size:.92rem}',
    '.dr .chip[aria-pressed="true"]{border-color:var(--mandarin);color:var(--mandarin);font-weight:600}',
    '.dr-zh{font-family:"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Microsoft YaHei",var(--body);font-size:1.12rem;line-height:1.75}',
    '.dr-zh:lang(zh-Hant){font-family:"PingFang TC","Noto Sans CJK TC","Microsoft JhengHei",var(--body)}',
    '.dr-passage{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:8px 0}',
    '.dr-passage p{margin:0 0 10px}.dr-passage p:last-child{margin:0}',
    '.dr-step{font-family:var(--head);font-weight:600;font-size:.85rem;letter-spacing:.06em;text-transform:uppercase;color:var(--mandarin);margin:14px 0 2px}',
    '.dr-note{color:var(--soft);font-size:.92rem;margin:6px 0}',
    '.dr-q{border-top:1px solid var(--line);padding:12px 0}',
    '.dr-q:first-of-type{border-top:0}',
    '.dr-q ol{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:6px}',
    '.dr-q button{width:100%;text-align:left;background:var(--paper);border:1.5px solid var(--line);border-radius:8px;padding:9px 12px;cursor:pointer}',
    '.dr-q button.right{border-color:var(--food);background:color-mix(in srgb,var(--food) 14%,transparent)}',
    '.dr-q button.wrong{border-color:var(--mandarin);background:color-mix(in srgb,var(--mandarin) 12%,transparent)}',
    '.dr-q button[disabled]{cursor:default;opacity:1;color:inherit}',
    '.dr textarea{display:block;width:100%;min-height:130px;padding:10px 12px;font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:8px;resize:vertical}',
    '.dr-clock{font-family:var(--head);font-weight:700;font-variant-numeric:tabular-nums;font-size:1.05rem}',
    '.dr-rec{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--mandarin);margin-right:6px;animation:drpulse 1s infinite}',
    '@keyframes drpulse{50%{opacity:.25}}',
    '@media (prefers-reduced-motion:reduce){.dr-rec{animation:none}}',
    '.dr-bars{display:grid;gap:7px;margin:8px 0 12px}',
    '.dr-bar{display:grid;grid-template-columns:120px 1fr 34px;gap:8px;align-items:center;font-size:.92rem}',
    '.dr-bar i{display:block;height:10px;border-radius:2px;background:var(--mandarin)}',
    '.dr-bar b{text-align:right;font-variant-numeric:tabular-nums}',
    '.dr-level{font-family:var(--head);font-weight:700;font-size:2rem;line-height:1;margin:4px 0}',
    '.dr-fix{border-top:1px solid var(--line);padding:9px 0;font-size:.95rem}',
    '.dr-fix s{color:var(--soft)}',
    '.dr-fix small{display:block;color:var(--soft);font-size:.88rem;margin-top:2px}',
    '.dr-terms{width:100%;border-collapse:collapse;font-size:.95rem;margin:6px 0}',
    '.dr-terms td{padding:6px 8px 6px 0;border-bottom:1px solid var(--line);vertical-align:top}',
    '.dr-terms td:first-child{white-space:nowrap}',
    '.dr-err{color:var(--mandarin);font-size:.92rem;margin:8px 0}'
  ].join('\n');

  function pad(n){return (n<10?'0':'')+n;}
  function ymd(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());}
  function parse(k){var p=k.split('-');return new Date(+p[0],+p[1]-1,+p[2]);}
  function dflt(s){return String(s==null?'':s);}
  function escH(s){return dflt(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function clamp(n,lo,hi){n=Number(n);if(isNaN(n))return lo;return Math.max(lo,Math.min(hi,n));}
  function mmss(s){s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+pad(s%60);}

  /* Weekends never break a streak; a missed weekday does. Today still counts as open until it ends. */
  function streakOf(days){
    var d=new Date(), n=0, i;
    if(!days[ymd(d)]) d.setDate(d.getDate()-1);
    for(i=0;i<800;i++){
      var k=ymd(d), wd=d.getDay();
      if(days[k]) n++;
      else if(wd!==0&&wd!==6) break;
      d.setDate(d.getDate()-1);
    }
    return n;
  }

  function mount(o){
    var host=o.host, store=o.store, cloud=o.cloud||{ready:Promise.resolve(null),push:function(){}};
    if(!host) return null;
    if(!document.getElementById('dr-css')){var st=document.createElement('style');st.id='dr-css';st.textContent=CSS;document.head.appendChild(st);}
    var D=store.get(KEY,null)||{}; if(!D.logs) D.logs={};
    var sampleP=(window.claude&&typeof window.claude.use==='function')?window.claude.use('sample').catch(function(){return null;}):Promise.resolve(null);
    var S=null, synced=false; /* S: the run in progress */
    var ctl=null, timers={}, rec=null, voices=[];

    function save(key){
      var doc=D.logs[key]; doc.stamp=new Date().toISOString();
      store.set(KEY,D);
      clearTimeout(timers[key]);
      timers[key]=setTimeout(function(){cloud.push('d-'+key,doc,function(ok){note(ok?'Saved to your account.':'Could not save just now. Kept on this device.');});},300);
    }
    function note(t){var el=host.querySelector('.dr-sync');if(el)el.textContent=t;}
    function doneDays(){var m={};Object.keys(D.logs).forEach(function(k){var r=D.logs[k].runs;if(r&&r.length)m[k]=1;});return m;}
    function weekRuns(){
      var now=new Date(), mon=new Date(now); mon.setDate(now.getDate()-((now.getDay()+6)%7));
      var from=ymd(mon), out=[];
      Object.keys(D.logs).sort().forEach(function(k){if(k>=from)(D.logs[k].runs||[]).forEach(function(r){out.push(r);});});
      return out;
    }
    function recentTitles(){
      var t=[];Object.keys(D.logs).sort().reverse().slice(0,10).forEach(function(k){(D.logs[k].runs||[]).forEach(function(r){if(r.title)t.push(r.title);});});
      return t.slice(0,8);
    }
    function outletFor(){return OUTLET[new Date().getDay()]||DEFAULT_OUTLET;}

    /* ---------- speech out ---------- */
    function loadVoices(){try{voices=(window.speechSynthesis&&speechSynthesis.getVoices())||[];}catch(e){voices=[];}}
    loadVoices();
    try{if(window.speechSynthesis) speechSynthesis.addEventListener('voiceschanged',loadVoices);}catch(e){}
    function pickVoice(trad){
      var zh=voices.filter(function(v){return /^(zh|cmn)/i.test(v.lang);});
      if(!zh.length) return null;
      var want=trad?/TW|Hant/i:/CN|Hans/i;
      var hit=zh.filter(function(v){return want.test(v.lang);});
      var pool=hit.length?hit:zh;
      /* prefer the better-sounding voices where the platform names them */
      var good=pool.filter(function(v){return /enhanced|premium|natural|neural|google/i.test(v.name);});
      return (good[0]||pool[0]);
    }
    function speak(text,trad,rate,onend){
      if(!window.speechSynthesis) return false;
      try{speechSynthesis.cancel();}catch(e){}
      var v=pickVoice(trad);
      var parts=(text.match(/[^。！？!?\n]+[。！？!?]?/g)||[text]).filter(function(s){return s.trim();});
      var i=0;
      function next(){
        if(i>=parts.length){if(onend)onend();return;}
        var u=new SpeechSynthesisUtterance(parts[i++]);
        u.lang=v?v.lang:(trad?'zh-TW':'zh-CN'); if(v) u.voice=v; u.rate=rate;
        u.onend=next; u.onerror=function(){if(onend)onend();};
        speechSynthesis.speak(u);
      }
      next();
      return true;
    }
    function stopSpeech(){try{if(window.speechSynthesis)speechSynthesis.cancel();}catch(e){}}

    /* ---------- speech in ---------- */
    var Rec=window.SpeechRecognition||window.webkitSpeechRecognition||null;

    /* ---------- Claude ---------- */
    function errCopy(e){
      var c=e&&e.code;
      if(c==='not_granted'||c==='sampling_disabled'||c==='not_declared'||c==='capability_disabled') return 'Claude is not available to this page. Allow it when the page asks, or open the planner in the Claude app.';
      if(c==='rate_limited') return 'Too many requests just now, or your usage limit is reached. Try again in a few minutes.';
      if(c==='invalid_json'||c==='empty_completion') return 'The answer came back malformed. Try again.';
      if(c==='refused') return 'Claude would not write this one. Pick another topic or paste a different piece.';
      if(c==='session_expired') return 'Sign in to Claude again, then try again.';
      if(c==='cancelled') return '';
      return 'Something went wrong on the way. Try again.';
    }
    function genPrompt(){
      var out=S.outlet, trad=S.trad, script=trad?'traditional characters (繁體字), Taiwan usage':'simplified characters (简体字), mainland usage';
      var common='Then write exactly 4 multiple-choice comprehension questions in Chinese (same script), testing in order: the gist, one specific detail, an inference, and the meaning of one C1 word in context. Each has 4 options in Chinese and exactly one correct option. Make wrong options plausible.\n'+
        'Then pick 6 key C1-level terms that appear in the passage, with pinyin in tone marks and a short English gloss.\n'+
        'Then write the retelling task in Chinese, one sentence: ask the learner to retell the passage in about a minute and add one sentence of their own view.\n\n'+
        'Reply with only this JSON:\n{"title":"short Chinese headline","paragraphs":["...","..."],"questions":[{"q":"...","options":["...","...","...","..."],"answer":0,"why":"one short English sentence"}],"terms":[{"term":"...","pinyin":"...","gloss":"..."}],"task":"..."}';
      var who='You are building a listening drill for an advanced Mandarin learner: C1 in 2019, now about B2, rebuilding listening and speaking towards C1 by June. They are a British China and Indo-Pacific specialist living in Singapore, so policy, trade and security vocabulary is what they need.\n\n';
      if(S.source==='paste'){
        return who+'This is an excerpt from the article they are reading this morning:\n<<<\n'+S.pasted.slice(0,2400)+'\n>>>\n\n'+
          'Take the most substantial 220 to 380 characters of it as the passage, verbatim, in whole sentences, keeping its original script, split into one or two paragraphs. If it is not in Chinese, reply with {"error":"not Chinese"}.\n'+common;
      }
      var avoid=recentTitles();
      return who+'Write an original passage of 240 to 300 Chinese characters in two paragraphs, in '+script+', in the register of '+out[3]+'. Topic: '+S.topic[2]+'.\n'+
        'It is practice material, not news. Do not invent specific recent events, dates, figures or quotations and present them as fact. Write about standing positions, mechanisms, trade-offs and long-running disputes that are well established, the way an analysis column explains a live issue. Use formal written vocabulary at C1 (for example 鉴于、与此同时、在……背景下、不容忽视、有鉴于此、并非……而是), varied sentence length, and at least one sentence that states a view and qualifies it.\n'+
        (avoid.length?'Do not repeat these recent headlines or their angle: '+avoid.join('；')+'.\n':'')+common;
    }
    function gradePrompt(){
      var qs=S.data.questions.map(function(q,i){return (i+1)+'. '+q.q;}).join('\n');
      return 'You are a strict, kind Mandarin examiner grading a C1-level listening-and-retelling task. The learner was C1 in 2019 and is rebuilding to C1 now. Grade against CEFR C1 for spoken production.\n\n'+
        'Passage they heard:\n<<<\n'+S.data.paragraphs.join('\n')+'\n>>>\n\nTask: '+S.data.task+'\n\n'+
        'Their retelling'+(S.spoken?' (spoken, transcribed by the browser\'s speech recognition, so ignore punctuation, missing punctuation and obvious homophone slips from the transcriber; judge the Mandarin they meant)':' (typed)')+':\n<<<\n'+S.answer.slice(0,3000)+'\n>>>\n'+
        'It took them '+Math.round(S.speakSecs)+' seconds.\n\n'+
        'Score 0 to 5 on each: coverage (main points and structure retold), accuracy (nothing distorted or invented), range (C1 vocabulary and structures, not just words lifted from the passage), grammar (correct, natural sentences). Give an overall CEFR estimate from B1 to C2, allowing + and -.\n'+
        'Give up to 4 corrections of things they actually said: the original, a natural C1 version, and a short English reason. Give 3 upgrades: a plain phrase they used or could have used, a more precise C1 alternative, and its pinyin. Then write a model retelling of about 120 characters in the passage\'s script, with one sentence of view.\n'+
        'Write the verdict in English, one or two sentences, specific, no praise padding.\n\n'+
        'Reply with only this JSON:\n{"level":"B2+","scores":{"coverage":0,"accuracy":0,"range":0,"grammar":0},"verdict":"...","corrections":[{"said":"...","better":"...","why":"..."}],"upgrades":[{"plain":"...","c1":"...","pinyin":"..."}],"model":"..."}';
    }
    function valid(d){
      return d&&!d.error&&Array.isArray(d.paragraphs)&&d.paragraphs.length&&Array.isArray(d.questions)&&d.questions.length>=3&&
        d.questions.every(function(q){return q&&q.q&&Array.isArray(q.options)&&q.options.length>=2&&q.answer>=0&&q.answer<q.options.length;});
    }

    /* ---------- screens ---------- */
    function h(html){host.innerHTML='<div class="group dr">'+html+'</div>';return host.firstChild;}
    function lang(){return S&&S.trad?'zh-Hant':'zh-Hans';}
    function clock(){return S?mmss((Date.now()-S.started)/1000):'0:00';}

    function home(){
      stopSpeech(); if(rec){try{rec.abort();}catch(e){}rec=null;}
      S=null;
      var days=doneDays(), n=streakOf(days), today=ymd(new Date());
      var strip='', d=new Date(); d.setDate(d.getDate()-13);
      for(var i=0;i<14;i++){
        var k=ymd(d), wd=d.getDay(), cls=[];
        if(days[k]) cls.push('done'); if(wd===0||wd===6) cls.push('we'); if(k===today) cls.push('today');
        strip+='<i class="'+cls.join(' ')+'" title="'+k+'">'+'SMTWTFS'.charAt(wd)+'</i>';
        d.setDate(d.getDate()+1);
      }
      var wr=weekRuns(), quiz=0, qn=0, lv=[];
      wr.forEach(function(r){if(r.quiz){quiz+=r.quiz[0];qn+=r.quiz[1];} if(r.level) lv.push(r.level);});
      var todayRuns=(D.logs[today]&&D.logs[today].runs)||[];
      var out=outletFor();
      var box=h(
        '<h3>Morning drill<small>Ten minutes</small></h3>'+
        '<p class="why">Listen to a short piece, answer four questions, retell it out loud, and Claude grades the retelling against C1. At the 05:40 desk or on the train.</p>'+
        '<div class="dr-streak"><b>'+n+'</b><span>'+(n===1?'day':'days')+' in a row'+(todayRuns.length?', today done':(n?', today still open':''))+'</span></div>'+
        '<div class="dr-strip" aria-label="Last fourteen days">'+strip+'</div>'+
        '<div class="dr-key"><span>Filled: drilled</span><span>Dotted: weekend, never breaks the streak</span><span>Dashed: today</span></div>'+
        (wr.length?'<p class="dr-note">This week: '+wr.length+(wr.length===1?' drill':' drills')+(qn?', '+quiz+' of '+qn+' questions right':'')+(lv.length?', last level '+escH(lv[lv.length-1]):'')+'.</p>':'')+
        '<div class="dr-row"><button type="button" class="plain go" data-a="start">'+(todayRuns.length?'Another drill':'Start today’s drill')+'</button>'+
        (termsThisWeek().length?'<button type="button" class="plain" data-a="terms">This week’s terms</button>':'')+'</div>'+
        '<p class="dr-note dr-sync">'+(synced?'Saved to your account.':'Saved on this device.')+'</p>'
      );
      box.querySelector('[data-a="start"]').onclick=setup;
      var tb=box.querySelector('[data-a="terms"]'); if(tb) tb.onclick=termsScreen;
    }

    function termsThisWeek(){
      var seen={}, out=[];
      weekRuns().forEach(function(r){(r.terms||[]).forEach(function(t){if(t&&t[0]&&!seen[t[0]]){seen[t[0]]=1;out.push(t);}});});
      return out;
    }
    function termsScreen(){
      var t=termsThisWeek();
      var rows=t.map(function(x){return '<tr><td class="dr-zh">'+escH(x[0])+'</td><td>'+escH(x[1])+'</td><td>'+escH(x[2])+'</td></tr>';}).join('');
      var box=h('<h3>This week’s terms<small>'+t.length+'</small></h3>'+
        '<p class="why">From every drill since Monday. They are the flashcards for 21:15. Copy puts them on the clipboard one per line, tab-separated, which imports straight into Anki.</p>'+
        '<table class="dr-terms">'+rows+'</table>'+
        '<div class="dr-row"><button type="button" class="plain" data-a="copy">Copy for Anki</button><button type="button" class="plain" data-a="back">Back</button></div><p class="dr-note" data-el="cn"></p>');
      box.querySelector('[data-a="back"]').onclick=home;
      box.querySelector('[data-a="copy"]').onclick=function(){
        var txt=t.map(function(x){return x[0]+'\t'+x[1]+' · '+x[2];}).join('\n'), cn=box.querySelector('[data-el="cn"]');
        function fallback(){var ta=document.createElement('textarea');ta.value=txt;ta.setAttribute('readonly','');box.appendChild(ta);ta.select();cn.textContent='Select all and copy.';}
        try{navigator.clipboard.writeText(txt).then(function(){cn.textContent='Copied '+t.length+' terms.';},fallback);}catch(e){fallback();}
      };
    }

    function setup(){
      var out=outletFor();
      S={started:Date.now(),outlet:out,trad:out[2]==='trad',topic:TOPICS[(new Date().getDate())%TOPICS.length],source:'gen',pasted:'',plays:0,peeked:false};
      var chips=TOPICS.map(function(t){return '<button type="button" class="chip" data-topic="'+t[0]+'">'+escH(t[1])+'</button>';}).join('');
      var box=h('<h3>Today’s piece<small>'+escH(out[1])+' register</small></h3>'+
        '<p class="dr-step">Source</p>'+
        '<div class="dr-row"><button type="button" class="chip" data-src="gen">Claude writes one</button><button type="button" class="chip" data-src="paste">Paste today’s article</button></div>'+
        '<div data-el="gen"><p class="dr-note">A passage in the style of '+escH(out[1])+' on a live issue. It explains standing positions and arguments, not today’s headlines: Claude cannot read the news from this page. To drill the real thing, paste it.</p>'+
        '<div class="dr-row">'+chips+'</div></div>'+
        '<div data-el="paste" hidden><p class="dr-note">Paste two or three paragraphs from this morning’s '+escH(out[1]==='News analysis'?'reading':out[1])+'. Claude keeps a passage of 200 to 400 characters, verbatim.</p><textarea data-el="pastebox" lang="zh" placeholder="在这里粘贴文章段落"></textarea></div>'+
        '<p class="dr-step">Script</p>'+
        '<div class="dr-row"><button type="button" class="chip" data-script="simp">简体</button><button type="button" class="chip" data-script="trad">繁體</button></div>'+
        '<div class="dr-row"><button type="button" class="plain go" data-a="make">Make the drill</button><button type="button" class="plain" data-a="back">Back</button></div>'+
        '<p class="dr-err" data-el="err" hidden></p>');
      function sync(){
        box.querySelectorAll('[data-topic]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.topic===S.topic[0]));});
        box.querySelectorAll('[data-src]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.src===S.source));});
        box.querySelectorAll('[data-script]').forEach(function(b){b.setAttribute('aria-pressed',String((b.dataset.script==='trad')===S.trad));});
        box.querySelector('[data-el="gen"]').hidden=S.source!=='gen';
        box.querySelector('[data-el="paste"]').hidden=S.source!=='paste';
      }
      box.querySelectorAll('[data-topic]').forEach(function(b){b.onclick=function(){S.topic=TOPICS.filter(function(t){return t[0]===b.dataset.topic;})[0];sync();};});
      box.querySelectorAll('[data-src]').forEach(function(b){b.onclick=function(){S.source=b.dataset.src;sync();};});
      box.querySelectorAll('[data-script]').forEach(function(b){b.onclick=function(){S.trad=b.dataset.script==='trad';sync();};});
      box.querySelector('[data-a="back"]').onclick=home;
      box.querySelector('[data-a="make"]').onclick=function(){
        var err=box.querySelector('[data-el="err"]');
        if(S.source==='paste'){
          S.pasted=box.querySelector('[data-el="pastebox"]').value.trim();
          var han=(S.pasted.match(/[\u4e00-\u9fff]/g)||[]).length;
          if(han<80){err.hidden=false;err.textContent='Paste at least a full paragraph of Chinese first.';return;}
          S.topic=['paste','Your article',''];
        }
        make();
      };
      sync();
    }

    function make(){
      var box=h('<h3>Writing the drill<small class="dr-clock">'+clock()+'</small></h3><p class="dr-note" data-el="st">Thinking… this takes up to a minute.</p>'+
        '<div class="dr-row"><button type="button" class="plain" data-a="stop">Stop</button></div>');
      ctl=new AbortController();
      box.querySelector('[data-a="stop"]').onclick=function(){if(ctl)ctl.abort();};
      sampleP.then(function(sample){
        if(!sample){failed({code:'not_granted'});return;}
        return sample.json(genPrompt(),{signal:ctl.signal,cache:false,onText:function(){var st=box.querySelector('[data-el="st"]');if(st)st.textContent='Writing…';}})
          .then(function(d){
            if(!valid(d)){failed({code:d&&d.error?'refused':'invalid_json'});return;}
            d.questions=d.questions.slice(0,4); d.terms=(d.terms||[]).slice(0,8); d.task=d.task||(S.trad?'請用一分鐘複述這段內容，並加一句你自己的看法。':'请用一分钟复述这段内容，并加一句你自己的看法。');
            S.data=d; S.quiz=[]; listen();
          },failed);
      });
      function failed(e){
        var msg=errCopy(e); if(!msg){setup();return;}
        var b=h('<h3>No drill this time</h3><p class="dr-err">'+escH(msg)+'</p><div class="dr-row"><button type="button" class="plain go" data-a="retry">Try again</button><button type="button" class="plain" data-a="back">Back</button></div>');
        b.querySelector('[data-a="retry"]').onclick=make; b.querySelector('[data-a="back"]').onclick=home;
      }
    }

    function passageHTML(){return '<div class="dr-passage dr-zh" lang="'+lang()+'">'+S.data.paragraphs.map(function(p){return '<p>'+escH(p)+'</p>';}).join('')+'</div>';}

    function listen(){
      var hasVoice=!!(window.speechSynthesis&&pickVoice(S.trad));
      var rate=S.rate||1;
      var box=h('<h3>1. Listen<small class="dr-clock">'+clock()+'</small></h3>'+
        '<p class="dr-zh" lang="'+lang()+'"><b>'+escH(S.data.title||'')+'</b></p>'+
        (hasVoice?'<p class="why">Twice, text hidden. The first time for the gist, the second for the detail. Headphones help.</p>'
                 :'<p class="dr-err">This device has no Mandarin voice installed, so the text is shown instead. On an iPhone: Settings, Accessibility, Spoken Content, Voices, Chinese. Then reopen the page.</p>')+
        (hasVoice?'<div class="dr-row"><button type="button" class="plain go" data-a="play">Play</button><button type="button" class="plain" data-a="stop">Stop</button></div>'+
          '<div class="dr-row" role="group" aria-label="Speed"><button type="button" class="chip" data-rate="0.85">0.85×</button><button type="button" class="chip" data-rate="1">1×</button><button type="button" class="chip" data-rate="1.2">1.2×</button></div>'+
          '<p class="dr-note" data-el="plays"></p>':'')+
        '<div data-el="text"'+(hasVoice?' hidden':'')+'>'+passageHTML()+'</div>'+
        '<div class="dr-row">'+(hasVoice?'<button type="button" class="plain" data-a="peek">Show the text</button>':'')+'<button type="button" class="plain go" data-a="next">To the questions</button></div>');
      function plays(){var el=box.querySelector('[data-el="plays"]');if(el)el.textContent='Played '+S.plays+(S.plays===1?' time':' times')+'.'+(S.plays>=2?' Enough: to the questions.':'');}
      function syncRate(){box.querySelectorAll('[data-rate]').forEach(function(b){b.setAttribute('aria-pressed',String(+b.dataset.rate===rate));});}
      if(hasVoice){
        box.querySelector('[data-a="play"]').onclick=function(){S.plays++;plays();speak(S.data.paragraphs.join('\n'),S.trad,rate);};
        box.querySelector('[data-a="stop"]').onclick=stopSpeech;
        box.querySelectorAll('[data-rate]').forEach(function(b){b.onclick=function(){rate=S.rate=+b.dataset.rate;syncRate();};});
        box.querySelector('[data-a="peek"]').onclick=function(){S.peeked=true;box.querySelector('[data-el="text"]').hidden=false;this.hidden=true;};
        syncRate();plays();
      }
      box.querySelector('[data-a="next"]').onclick=function(){stopSpeech();quiz(0);};
    }

    function quiz(i){
      var q=S.data.questions[i], total=S.data.questions.length, right=S.quiz.filter(Boolean).length;
      var opts=q.options.map(function(op,j){return '<li><button type="button" data-j="'+j+'" class="dr-zh" lang="'+lang()+'">'+'ABCD'.charAt(j)+'. '+escH(op)+'</button></li>';}).join('');
      var box=h('<h3>2. Questions<small class="dr-clock">'+clock()+'</small></h3>'+
        '<p class="dr-note">'+(i+1)+' of '+total+(i?', '+right+' right so far':'')+'. From memory.</p>'+
        '<div class="dr-q"><p class="dr-zh" lang="'+lang()+'"><b>'+escH(q.q)+'</b></p><ol>'+opts+'</ol><p class="dr-note" data-el="why" hidden></p></div>'+
        '<div class="dr-row"><button type="button" class="plain go" data-a="next" hidden>'+(i+1<total?'Next question':'To the retelling')+'</button>'+
        '<button type="button" class="plain" data-a="replay">Hear it again</button></div>');
      box.querySelector('[data-a="replay"]').onclick=function(){S.plays++;speak(S.data.paragraphs.join('\n'),S.trad,S.rate||1);};
      if(!(window.speechSynthesis&&pickVoice(S.trad))) box.querySelector('[data-a="replay"]').hidden=true;
      box.querySelectorAll('[data-j]').forEach(function(b){
        b.onclick=function(){
          var j=+b.dataset.j, ok=j===Number(q.answer);
          S.quiz[i]=ok;
          box.querySelectorAll('[data-j]').forEach(function(x){x.disabled=true;if(+x.dataset.j===Number(q.answer))x.classList.add('right');});
          if(!ok) b.classList.add('wrong');
          var w=box.querySelector('[data-el="why"]');w.hidden=false;w.textContent=(ok?'Right. ':'Not quite. ')+dflt(q.why);
          box.querySelector('[data-a="next"]').hidden=false;
        };
      });
      box.querySelector('[data-a="next"]').onclick=function(){stopSpeech();if(i+1<total)quiz(i+1);else speakScreen();};
    }

    function speakScreen(){
      S.answer=S.answer||''; S.spoken=false; S.speakSecs=0;
      var box=h('<h3>3. Retell it<small class="dr-clock">'+clock()+'</small></h3>'+
        '<p class="dr-zh" lang="'+lang()+'">'+escH(S.data.task)+'</p>'+
        '<p class="why">About a minute, out loud, without looking at the text. Use the words you heard, then one sentence of your own view.</p>'+
        (Rec?'<div class="dr-row"><button type="button" class="plain go" data-a="rec">Start speaking</button><span class="dr-clock" data-el="t" style="align-self:center"></span></div>'
            :'<p class="dr-note">This browser cannot transcribe speech here. Tap the microphone on your keyboard and dictate, or type.</p>')+
        '<textarea data-el="ans" lang="'+lang()+'" class="dr-zh" placeholder="'+(Rec?'Your words appear here as you speak. Fix anything the transcriber got wrong.':'Dictate or type your retelling')+'"></textarea>'+
        '<p class="dr-err" data-el="err" hidden></p>'+
        '<div class="dr-row"><button type="button" class="plain go" data-a="grade">Grade it</button><button type="button" class="plain" data-a="skip">Skip the grading</button></div>');
      var ta=box.querySelector('[data-el="ans"]'), t0=0, tick=null, base='';
      ta.value=S.answer;
      ta.addEventListener('input',function(){S.answer=ta.value;});
      var rb=box.querySelector('[data-a="rec"]');
      function stopRec(){if(rec){try{rec.stop();}catch(e){}} }
      if(rb) rb.onclick=function(){
        if(rec){stopRec();return;}
        var r;
        try{r=new Rec();}catch(e){fail('Speech recognition would not start here. Dictate with the keyboard microphone, or type.');return;}
        r.lang=S.trad?'zh-TW':'zh-CN'; r.continuous=true; r.interimResults=true;
        base=ta.value?ta.value+(/[。！？]$/.test(ta.value)?'':'，'):'';
        r.onresult=function(ev){
          var fin='', tmp='';
          for(var k=0;k<ev.results.length;k++){var tx=ev.results[k][0].transcript; if(ev.results[k].isFinal) fin+=tx; else tmp+=tx;}
          ta.value=base+fin+tmp; S.answer=ta.value; S.spoken=true;
        };
        r.onerror=function(ev){
          var c=ev&&ev.error;
          if(c==='not-allowed'||c==='service-not-allowed') fail('The microphone is blocked for this page. Dictate with the keyboard microphone instead, it works the same.');
          else if(c==='no-speech') fail('Nothing heard. Try again, closer to the phone.');
          else if(c&&c!=='aborted') fail('Transcription stopped ('+c+'). Dictate with the keyboard microphone, or type.');
        };
        r.onend=function(){rec=null;clearInterval(tick);S.speakSecs+=(Date.now()-t0)/1000;rb.innerHTML='Start speaking';};
        try{r.start();}catch(e){fail('Speech recognition would not start here. Dictate with the keyboard microphone, or type.');return;}
        rec=r; t0=Date.now();
        rb.innerHTML='<span class="dr-rec" aria-hidden="true"></span>Stop';
        var te=box.querySelector('[data-el="t"]');
        tick=setInterval(function(){te.textContent=mmss(S.speakSecs+(Date.now()-t0)/1000);},500);
      };
      function fail(m){var e=box.querySelector('[data-el="err"]');e.hidden=false;e.textContent=m;}
      box.querySelector('[data-a="grade"]').onclick=function(){
        stopRec();
        S.answer=ta.value.trim();
        if((S.answer.match(/[\u4e00-\u9fff]/g)||[]).length<20){fail('Say or type at least two or three sentences first.');return;}
        if(!S.speakSecs) S.speakSecs=Math.max(30,(Date.now()-S.started)/1000/4);
        grade();
      };
      box.querySelector('[data-a="skip"]').onclick=function(){stopRec();S.answer=ta.value.trim();S.result=null;finish();};
    }

    function grade(){
      var box=h('<h3>4. Grading<small class="dr-clock">'+clock()+'</small></h3><p class="dr-note" data-el="st">Thinking… up to a minute.</p>'+
        '<div class="dr-row"><button type="button" class="plain" data-a="stop">Stop</button></div>');
      ctl=new AbortController();
      box.querySelector('[data-a="stop"]').onclick=function(){if(ctl)ctl.abort();};
      sampleP.then(function(sample){
        if(!sample){failed({code:'not_granted'});return;}
        return sample.json(gradePrompt(),{signal:ctl.signal,cache:false,onText:function(){var st=box.querySelector('[data-el="st"]');if(st)st.textContent='Writing the feedback…';}})
          .then(function(r){
            if(!r||!r.scores){failed({code:'invalid_json'});return;}
            S.result=r; finish();
          },failed);
      });
      function failed(e){
        var msg=errCopy(e);
        if(!msg){speakScreen();return;}
        var b=h('<h3>Not graded</h3><p class="dr-err">'+escH(msg)+'</p><div class="dr-row"><button type="button" class="plain go" data-a="retry">Try again</button><button type="button" class="plain" data-a="skip">Log it ungraded</button></div>');
        b.querySelector('[data-a="retry"]').onclick=grade; b.querySelector('[data-a="skip"]').onclick=function(){S.result=null;finish();};
      }
    }

    function finish(){
      var key=ymd(new Date()), r=S.result, right=S.quiz.filter(Boolean).length;
      var sc=r?['coverage','accuracy','range','grammar'].map(function(k){return clamp(r.scores[k],0,5);}):null;
      var run={
        t:new Date().toISOString(), topic:S.topic[1], title:dflt(S.data.title).slice(0,60), source:S.source, script:S.trad?'trad':'simp',
        plays:S.plays, peeked:S.peeked, quiz:[right,S.data.questions.length], spoken:!!S.spoken,
        level:r?dflt(r.level).slice(0,4):'', score:sc?sc.reduce(function(a,b){return a+b;},0):null,
        secs:Math.round((Date.now()-S.started)/1000),
        terms:(S.data.terms||[]).map(function(x){return [dflt(x.term),dflt(x.pinyin),dflt(x.gloss)];})
      };
      if(!D.logs[key]) D.logs[key]={kind:'drill',key:key,runs:[]};
      D.logs[key].runs=(D.logs[key].runs||[]).concat([run]).slice(-6);
      save(key);
      var n=streakOf(doneDays());
      var html='<h3>Done<small class="dr-clock">'+mmss(run.secs)+'</small></h3>'+
        '<div class="dr-streak"><b>'+n+'</b><span>'+(n===1?'day':'days')+' in a row. Questions: '+right+' of '+run.quiz[1]+'.</span></div>';
      if(r){
        var LBL=['Coverage','Accuracy','C1 range','Grammar'];
        html+='<p class="dr-step">Retelling</p><p class="dr-level">'+escH(run.level||'–')+'</p><p>'+escH(r.verdict)+'</p>'+
          '<div class="dr-bars">'+sc.map(function(v,i){return '<div class="dr-bar"><span>'+LBL[i]+'</span><i style="width:'+(v/5*100)+'%"></i><b>'+v+'/5</b></div>';}).join('')+'</div>';
        if(r.corrections&&r.corrections.length){
          html+='<p class="dr-step">Corrections</p>'+r.corrections.slice(0,4).map(function(c){
            return '<div class="dr-fix"><span class="dr-zh" lang="'+lang()+'"><s>'+escH(c.said)+'</s><br>'+escH(c.better)+'</span><small>'+escH(c.why)+'</small></div>';}).join('');
        }
        if(r.upgrades&&r.upgrades.length){
          html+='<p class="dr-step">Say it at C1</p>'+r.upgrades.slice(0,3).map(function(u){
            return '<div class="dr-fix"><span class="dr-zh" lang="'+lang()+'">'+escH(u.plain)+' → <b>'+escH(u.c1)+'</b></span><small>'+escH(u.pinyin)+'</small></div>';}).join('');
        }
        if(r.model) html+='<p class="dr-step">Model retelling</p><div class="dr-passage dr-zh" lang="'+lang()+'"><p>'+escH(r.model)+'</p></div>'+
          (window.speechSynthesis&&pickVoice(S.trad)?'<div class="dr-row"><button type="button" class="plain" data-a="shadow">Play it, then shadow it</button></div>':'');
      } else {
        html+='<p class="dr-note">Logged without a grade. The streak counts it.</p>';
      }
      html+='<p class="dr-step">The passage</p>'+passageHTML();
      if(run.terms.length) html+='<p class="dr-step">Terms for tonight’s flashcards</p><table class="dr-terms">'+run.terms.map(function(x){return '<tr><td class="dr-zh" lang="'+lang()+'">'+escH(x[0])+'</td><td>'+escH(x[1])+'</td><td>'+escH(x[2])+'</td></tr>';}).join('')+'</table>';
      html+='<div class="dr-row"><button type="button" class="plain go" data-a="home">Back to the streak</button></div><p class="dr-note dr-sync">Saving…</p>';
      var box=h(html);
      var sh=box.querySelector('[data-a="shadow"]'); if(sh) sh.onclick=function(){speak(r.model,S.trad,0.9);};
      box.querySelector('[data-a="home"]').onclick=home;
      try{box.scrollIntoView({block:'start'});}catch(e){}
    }

    cloud.ready.then(function(docs){
      if(!docs) return;
      synced=true;
      if(o.restoring){Object.keys(D.logs).forEach(function(k){(o.restorePush||cloud.push)('d-'+k,D.logs[k]);});if(!S)home();return;}
      var changed=false;
      docs.forEach(function(v){
        if(!v||v.kind!=='drill'||!v.key) return;
        var mine=D.logs[v.key];
        if(!mine||!mine.stamp||(v.stamp||'')>=mine.stamp){D.logs[v.key]=v;changed=true;}
        else cloud.push('d-'+v.key,mine);
      });
      Object.keys(D.logs).forEach(function(k){
        if(!docs.some(function(v){return v&&v.kind==='drill'&&v.key===k;})) cloud.push('d-'+k,D.logs[k]);
      });
      if(changed) store.set(KEY,D);
      if(!S) home();
    });

    home();
    return {render:function(){if(!S)home();},streak:function(){return streakOf(doneDays());}};
  }

  window.MandarinDrill={mount:mount,streakOf:streakOf};
})();
