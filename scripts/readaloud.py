"""Read aloud: a right-click menu that speaks a selection or a verse with the
device's voice for that language (Web Speech API — nothing is downloaded or
stored; the voices are whatever Windows / Android has installed).

Shared by the dashboard (live.py) and the reader (build_site.py): each page
inserts CSS and JS from here with its own element selectors.
"""

CSS = r"""
#ctx { position:fixed; z-index:50; min-width:14rem; background:var(--card); color:var(--fg); border:1px solid var(--border);
  border-radius:10px; box-shadow:0 10px 30px rgba(0,0,0,.25); padding:.3rem; font:13px system-ui, sans-serif; white-space:normal; }
#ctx .it { padding:.45rem .7rem; border-radius:7px; cursor:pointer; }
#ctx .it:hover { background:var(--soft); }
#ctx .it small { display:block; color:var(--muted); font-size:11px; margin-top:.1rem; }
#ctx .it.off { color:var(--muted); cursor:default; }
.speaking { background:var(--hl) !important; border-radius:6px; }
"""

# {host}: elements where the menu applies; {verse}: the unit read when nothing is selected
JS = r"""
/* ---------- read aloud: right-click a selection or a verse ---------- */
const TTS_LANG = {en:'en-US', zh:'zh-CN', es:'es-ES', ja:'ja-JP', 'ja-easy':'ja-JP', th:'th-TH', yue:'zh-HK', nan:'zh-TW', hak:'zh-TW',
                  vi:'vi-VN', ko:'ko-KR', fa:'fa-IR', tr:'tr-TR', id:'id-ID', ms:'ms-MY', hbo:'he-IL', arc:'he-IL', grc:'el-GR', lxx:'el-GR'};
const TTS_NOTE = {nan:'no Hokkien voice exists; read with a Taiwan Mandarin voice', hak:'no Hakka voice exists; read with a Taiwan Mandarin voice',
                  grc:'Modern Greek pronunciation', hbo:'Modern Hebrew pronunciation', arc:'Modern Hebrew pronunciation'};
let ttsVoices = [];
if ('speechSynthesis' in window) { ttsVoices = speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = () => { ttsVoices = speechSynthesis.getVoices(); }; }
function ttsVoice(bcp){
  const norm = v => v.lang.replace('_', '-').toLowerCase(), base = bcp.split('-')[0];
  const c = ttsVoices.filter(v => norm(v).startsWith(base)); if (!c.length) return null;
  const exact = c.filter(v => norm(v) === bcp.toLowerCase()), pool = exact.length ? exact : c;
  return pool.find(v => /natural|online/i.test(v.name)) || pool[0];
}
function ttsLangOf(el){                                     // source text first: it sits inside a translation column
  if (el.closest('.greek')) return 'grc'; if (el.closest('.orig')) return 'hbo';
  const l = el.closest('[lang]'); if (l && l.getAttribute('lang')) return l.getAttribute('lang');
  return document.documentElement.lang || 'en';
}
function ttsLangName(code){ return (typeof TARGETS !== 'undefined' && TARGETS[code] && TARGETS[code].name) || (typeof LANGS !== 'undefined' && LANGS[code] && LANGS[code].name) || code; }
function ttsClean(code, text){
  if (code === 'hbo' || code === 'arc') text = text.replace(/[\u0591-\u05AF\u05BD\u05C0\u05C3-\u05C5]/g, '');          // cantillation, meteg, paseq, sof pasuq
  if (code === 'grc' || code === 'lxx') text = text.normalize('NFD').replace(/[\u0300\u0342]/g, '\u0301').replace(/[\u0313\u0314\u0343-\u0345]/g, '').replace(/\u0301(?=[\u0300-\u036f]*\u0301)/g, '').normalize('NFC');   // polytonic -> monotonic: grave/circumflex become acute, breathings and iota subscript go
  return text.replace(/\s+/g, ' ').trim();
}
function ttsTextOf(node){                                    // text without verse numbers, labels or furigana readings
  const c = node.cloneNode(true); c.querySelectorAll('rt, sup, .lt, .lab, .caret, .v, .ref, .chhead, .astat, .empty').forEach(x => x.remove()); return c.textContent;
}
function ttsSelection(){
  const s = window.getSelection(); if (!s || s.isCollapsed) return '';
  const d = document.createElement('div'); d.appendChild(s.getRangeAt(0).cloneContents()); return ttsTextOf(d);
}
let ttsMark = null;
/* A reading can end two ways, finished or cut off, and the reader page wants to
   know which: a story counts as heard only when it was heard to the end. The
   browser does not say plainly - Chrome reports a cancelled utterance as an
   error, Firefox as an ordinary end - so every reading is numbered, a stop is
   noted before it is asked for, and the last piece answers for the whole. */
let ttsRun = 0, ttsHalt = false;
function ttsStop(){
  ttsHalt = true; speechSynthesis.cancel();
  if (ttsMark) { ttsMark.classList.remove('speaking'); ttsMark = null; }
}
function ttsSpeak(text, code, node, done){
  ttsHalt = true; speechSynthesis.cancel();
  const run = ++ttsRun; ttsHalt = false;
  const bcp = TTS_LANG[code] || 'en-US', v = ttsVoice(bcp);
  const parts = ttsClean(code, text).match(/[^.!?。！？׃;·]+[.!?。！？׃;·]*\s*/g) || [text];   // sentence-sized pieces: long utterances get cut off
  const chunks = []; let buf = '';
  for (const p of parts) { if ((buf + p).length > 220 && buf) { chunks.push(buf); buf = ''; } buf += p; } if (buf.trim()) chunks.push(buf);
  if (ttsMark) ttsMark.classList.remove('speaking'); ttsMark = node || null; if (ttsMark) ttsMark.classList.add('speaking');
  const fin = ok => {
    if (run !== ttsRun) ok = false;                         // a piece of a reading already replaced by the next
    if (ttsMark) { ttsMark.classList.remove('speaking'); ttsMark = null; }
    if (done) { const f = done; done = null; f(ok); }      // once, whichever piece answers first
  };
  chunks.forEach((c, i) => { const u = new SpeechSynthesisUtterance(c); u.lang = bcp; if (v) u.voice = v;
    u.rate = (typeof VOICE !== 'undefined' ? VOICE.rate : 0.95); u.pitch = (typeof VOICE !== 'undefined' ? VOICE.pitch : 1);
    u.onerror = () => fin(false);
    if (i === chunks.length - 1) u.onend = () => fin(!ttsHalt);
    speechSynthesis.speak(u); });
}
const ctx = document.createElement('div'); ctx.id = 'ctx'; ctx.hidden = true; document.body.appendChild(ctx);
function ctxHide(){ ctx.hidden = true; }
document.addEventListener('contextmenu', e => {
  if (!('speechSynthesis' in window)) return;
  const host = e.target.closest('{host}'); if (!host) return;
  const verse = e.target.closest('{verse}');
  const sel = ttsSelection(), text = sel || (verse ? ttsTextOf(verse) : '');
  if (!text.trim()) return;
  e.preventDefault();
  const code = ttsLangOf(verse || e.target), bcp = TTS_LANG[code] || 'en-US', v = ttsVoice(bcp);
  let voice = v ? v.name.replace(/^Microsoft /, '').replace(/ - .*$/, '') : 'no ' + ttsLangName(code) + ' voice installed, using the default';
  if (v && v.lang.replace('_', '-').toLowerCase() !== bcp.toLowerCase()) voice += ` (${v.lang} voice; no ${bcp} voice installed)`;
  ctx.innerHTML = `<div class="it" data-a="read">Read ${sel ? 'selection' : 'verse'} aloud<small>${ttsLangName(code)} · ${voice}${TTS_NOTE[code] ? ' · ' + TTS_NOTE[code] : ''}</small></div>`
    + (speechSynthesis.speaking ? `<div class="it" data-a="stop">Stop reading</div>` : '');
  ctx.hidden = false;
  const w = ctx.offsetWidth, h = ctx.offsetHeight;
  ctx.style.left = Math.min(e.clientX, window.innerWidth - w - 8) + 'px'; ctx.style.top = Math.min(e.clientY, window.innerHeight - h - 8) + 'px';
  ctx.querySelector('[data-a=read]').onclick = () => { ttsSpeak(text, code, sel ? null : verse); ctxHide(); };
  const st = ctx.querySelector('[data-a=stop]'); if (st) st.onclick = () => { ttsStop(); ctxHide(); };
});
document.addEventListener('click', e => { if (!e.target.closest('#ctx')) ctxHide(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { ctxHide(); if ('speechSynthesis' in window) ttsStop(); } });
window.addEventListener('scroll', ctxHide, true);
"""


def js(host: str, verse: str) -> str:
    return JS.replace("{host}", host).replace("{verse}", verse)
