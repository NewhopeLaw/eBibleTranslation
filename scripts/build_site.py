#!/usr/bin/env python3
"""Build a self-contained HTML reader for the translation.

Embeds the original text of every chapter (Hebrew / Aramaic / Greek) and every
translation found under output/<lang>/json/, and writes site/index.html:
  - reading view per target language, with superscript verse numbers,
    translator's notes, prev/next chapter, adjustable text size (persisted)
  - tabs per chapter: original | each translation | side by side | compare
  - full-text search over the selected translation
  - reference finder ("Genesis 2:7", "gen 2", "1 sam 3:10")
  - works on phone screens (book menu collapses into a dropdown)

Re-run after translating more chapters; the page embeds all data, no server
needed — open site/index.html in any browser. This one-file design is what
the planned Android APK will wrap unchanged.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, LANGS, MIXED, TARGETS, chapter_lang, slug, verse_lang
import readaloud as RA

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "output"
NORM_DIR = ROOT / "sources" / "normalized"
SITE = ROOT / "site"

ORDER = {slug(m["name"]): m["num"] for m in BOOKS.values()}
BY_SLUG = {slug(m["name"]): m for m in BOOKS.values()}
ABBREV = {
    "gen": "Genesis", "ex": "Exodus", "exod": "Exodus", "lev": "Leviticus",
    "num": "Numbers", "deut": "Deuteronomy", "dt": "Deuteronomy",
    "josh": "Joshua", "judg": "Judges", "1sam": "1 Samuel", "2sam": "2 Samuel",
    "1kgs": "1 Kings", "2kgs": "2 Kings", "1chr": "1 Chronicles",
    "2chr": "2 Chronicles", "neh": "Nehemiah", "esth": "Esther",
    "ps": "Psalms", "psa": "Psalms", "prov": "Proverbs", "eccl": "Ecclesiastes",
    "song": "Song of Songs", "isa": "Isaiah", "jer": "Jeremiah",
    "lam": "Lamentations", "ezek": "Ezekiel", "dan": "Daniel", "hos": "Hosea",
    "obad": "Obadiah", "mic": "Micah", "nah": "Nahum", "hab": "Habakkuk",
    "zeph": "Zephaniah", "hag": "Haggai", "zech": "Zechariah", "mal": "Malachi",
    "matt": "Matthew", "mt": "Matthew", "mk": "Mark", "lk": "Luke", "jn": "John",
    "rom": "Romans", "1cor": "1 Corinthians", "2cor": "2 Corinthians",
    "gal": "Galatians", "eph": "Ephesians", "phil": "Philippians",
    "col": "Colossians", "1thess": "1 Thessalonians", "2thess": "2 Thessalonians",
    "1tim": "1 Timothy", "2tim": "2 Timothy", "phlm": "Philemon",
    "heb": "Hebrews", "jas": "James", "1pet": "1 Peter", "2pet": "2 Peter",
    "1jn": "1 John", "2jn": "2 John", "3jn": "3 John", "rev": "Revelation",
}

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eBible Translation</title>
<style>
:root { --bg:#faf8f4; --fg:#22201c; --muted:#7a736a; --accent:#7c5cbf;
        --card:#ffffff; --border:#e4ded4; --hl:#f3e8b8; --fs:18px; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#181614; --fg:#e8e4dd; --muted:#948d82; --accent:#a98ee6;
          --card:#221f1c; --border:#37322c; --hl:#4a4020; }
}
* { box-sizing:border-box; margin:0; }
html { scroll-behavior:smooth; }
body { background:var(--bg); color:var(--fg);
  font:var(--fs)/1.72 Georgia, "Times New Roman", serif; }
header { position:sticky; top:0; background:var(--bg); z-index:5;
  border-bottom:1px solid var(--border); padding:.6rem .9rem;
  display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }
header .brand { font-size:15px; font-style:italic; color:var(--muted);
  margin-right:auto; white-space:nowrap; }
input, select, button.fs { font:14px system-ui, sans-serif; padding:.45rem .6rem;
  border:1px solid var(--border); border-radius:8px;
  background:var(--card); color:var(--fg); }
input:focus { outline:2px solid var(--accent); border-color:transparent; }
#ref { width:9rem; } #q { width:13rem; }
.goto { display:flex; align-items:center; gap:.4rem; font:12px system-ui, sans-serif; color:var(--muted); white-space:nowrap; }
button.fs { cursor:pointer; width:2.2rem; }
button.fs:hover { border-color:var(--accent); }
select#bookSel { max-width:11rem; display:none; }
main { max-width:42rem; margin:0 auto; padding:1.4rem 1.2rem 5rem; }
main.wide { max-width:66rem; }
.layout { display:flex; }
footer#credits { border-top:1px solid var(--border); margin-top:2rem; padding:1.2rem 1.2rem 2rem; color:var(--muted);
  font:12px/1.55 system-ui, sans-serif; }
footer#credits h2 { font:600 12px system-ui, sans-serif; text-transform:uppercase; letter-spacing:.06em; margin:0 0 .5rem; }
footer#credits p { margin:0 0 .45rem; max-width:66rem; } footer#credits a { color:inherit; }
header .sources { margin-left:auto; font:12px system-ui, sans-serif; color:var(--muted); cursor:pointer; background:none; border:0; text-decoration:underline; }
nav#books { width:210px; flex:none; padding:1rem .6rem; font:14px system-ui,sans-serif;
  border-right:1px solid var(--border); height:calc(100vh - 58px);
  overflow-y:auto; position:sticky; top:58px; }
nav#books a { display:block; padding:.15rem .55rem; color:var(--fg);
  text-decoration:none; border-radius:6px; }
nav#books a:hover { background:var(--card); }
nav#books a.on { background:var(--accent); color:#fff; }
nav#books .t { margin:.7rem 0 .25rem; font-weight:600; color:var(--muted);
  font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
nav#books a.missing { color:var(--muted); opacity:.4; pointer-events:none; }
nav#books a.untr { color:var(--muted); }
nav#books a .ct { float:right; font-size:11px; color:var(--muted); margin-top:.15rem; }
nav#books a.on .ct { color:#fff; opacity:.85; }
.chnav { font:14px system-ui,sans-serif; margin:.9rem 0 1.6rem;
  display:flex; flex-wrap:wrap; gap:.3rem; }
.chnav a { padding:.22rem .6rem; border:1px solid var(--border);
  border-radius:7px; text-decoration:none; color:var(--fg); }
.chnav a.on { background:var(--accent); color:#fff; border-color:var(--accent); }
.chnav a.untr { color:var(--muted); border-style:dashed; }
h2 { font-size:1.65em; font-weight:normal; margin:.3rem 0 .4rem; }
h2 .lang { font:13px system-ui,sans-serif; color:var(--muted); margin-left:.6rem; vertical-align:middle; }
sup.v { color:var(--accent); font:600 .58em system-ui,sans-serif;
  margin:0 .18em 0 .05em; user-select:none; vertical-align:.55em; }
p.vv { margin:0 0 1.05em; text-align:justify; hyphens:auto; }
.poetry { margin:0 0 1.05em 1.3em; text-indent:-1.3em; white-space:pre-wrap; }
.notes { margin-top:2.4rem; padding:1rem 1.2rem; background:var(--card);
  border:1px solid var(--border); border-radius:10px;
  font:14px/1.6 system-ui,sans-serif; color:var(--muted); }
.notes b { color:var(--fg); }
.pn { display:flex; justify-content:space-between; margin-top:2.6rem;
  font:15px system-ui,sans-serif; }
.pn a { color:var(--accent); text-decoration:none; padding:.5rem .9rem;
  border:1px solid var(--border); border-radius:9px; }
.pn a:hover { border-color:var(--accent); }
.pn .off { visibility:hidden; }
#results { font:15px/1.5 system-ui,sans-serif; }
#results .hit { background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:.7rem .9rem; margin:.6rem 0; cursor:pointer; }
#results .hit:hover { border-color:var(--accent); }
#results .ref { color:var(--accent); font-weight:600; font-size:13px; }
mark { background:var(--hl); color:inherit; border-radius:3px; padding:0 .1em; }
.flash { animation:flash 2.5s; }
@keyframes flash { 0%,55% { background:var(--hl); } 100% { background:transparent; } }
.empty { color:var(--muted); font:15px system-ui,sans-serif; margin-top:2rem; }
.tabs { display:flex; flex-wrap:wrap; gap:.3rem; font:14px system-ui,sans-serif; margin:-.8rem 0 1.3rem; align-items:center; }
.tabs a { padding:.25rem .75rem; border:1px solid var(--border); border-radius:999px;
  cursor:pointer; color:var(--muted); user-select:none; }
.tabs a:hover { border-color:var(--accent); }
.tabs a.on { background:var(--card); color:var(--fg); border-color:var(--accent); }
.tabs a.off { opacity:.4; cursor:default; pointer-events:none; }
.tabs .sep { width:1px; height:1.2rem; background:var(--border); margin:0 .3rem; }
.orig { font-family:"SBL Hebrew","Ezra SIL","Taamey Frank CLM","Times New Roman",serif; line-height:1.95; }
.orig.greek { font-family:"Gentium Plus","SBL Greek","Palatino Linotype","Times New Roman",serif; }
.orig[dir=rtl] { text-align:right; }
.orig sup.v { vertical-align:.7em; }
.w { cursor:pointer; border-radius:3px; } .w:hover { background:var(--soft); } .w.sel { background:var(--hl); }
main.inter .orig .w { display:inline-block; text-align:center; margin:0 .2em .45em 0; vertical-align:top; line-height:1.4; }
main.inter .orig .w::after { content:attr(data-g); display:block; font:11px/1.25 system-ui,sans-serif; color:var(--muted); direction:ltr; max-width:9em; white-space:normal; margin-top:.1em; }
main.inter .orig .w[data-m]::before { content:attr(data-m); display:block; font:9.5px/1.2 ui-monospace,Consolas,monospace; color:var(--accent); direction:ltr; }
#wpop { position:fixed; z-index:40; max-width:26rem; background:var(--card); color:var(--fg); border:1px solid var(--border); border-radius:10px;
  box-shadow:0 10px 30px rgba(0,0,0,.25); padding:.7rem .9rem; font:13px/1.45 system-ui,sans-serif; white-space:normal; direction:ltr; text-align:left; }
#wpop .hw { font-size:1.35em; } #wpop .hw .orig { font-size:1em; } #wpop .tl { color:var(--muted); margin-left:.4em; } #wpop .pos { color:var(--muted); font-size:11px; margin-left:.4em; }
#wpop .parse { margin:.35rem 0; } #wpop .parse code { font:11px ui-monospace,Consolas,monospace; color:var(--accent); margin-left:.4em; }
#wpop .meaning { color:var(--muted); font-size:12px; margin-top:.35rem; max-height:9em; overflow:auto; }
#wpop .acts { margin-top:.5rem; } #wpop .acts a { margin-right:.9rem; cursor:pointer; color:var(--accent); text-decoration:underline; }
#wpop .pre { color:var(--muted); font-size:12px; }
.tabs a.tool { border-style:dashed; }
.gs { display:grid; grid-template-columns:repeat(auto-fill,minmax(11rem,1fr)); gap:.5rem .8rem; margin:.6rem 0 1rem; font:13px system-ui,sans-serif; }
.gs label { display:flex; flex-direction:column; gap:.2rem; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }
.gs select, .gs input { font:14px system-ui,sans-serif; padding:.35rem .5rem; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--fg); }
.gs button { grid-column:1 / -1; justify-self:start; font:14px system-ui,sans-serif; padding:.45rem 1rem; border:1px solid var(--accent); border-radius:8px; background:var(--accent); color:#fff; cursor:pointer; }
.hit .orig { display:block; margin-top:.15rem; } .hit mark { background:var(--hl); color:inherit; border-radius:3px; }
.lt { font:600 10px system-ui,sans-serif; color:var(--muted); text-transform:uppercase;
  letter-spacing:.05em; margin:0 .3em; vertical-align:.5em; user-select:none; }
p.ov { margin:0 0 .6em; }
.par { display:grid; grid-template-columns:1fr 1fr; gap:0 1.6rem; align-items:start; }
.par > div { padding:.45rem 0; border-bottom:1px solid var(--border); }
.par .e { white-space:pre-wrap; }
.cmp { border-bottom:1px solid var(--border); padding:.6rem 0 .5rem; }
.cmp .row { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.15rem 0; align-items:baseline; }
.cmp .row .lab { font:600 11px system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; text-align:right; }
.cmp .row .txt { white-space:pre-wrap; }
[lang="zh"], [lang="ja"] { font-family:Georgia, "Noto Serif CJK SC", "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", "SimSun", "Songti SC", serif; line-height:1.95; }
[lang="th"] { font-family:"Noto Serif Thai", "Leelawadee UI", "Tahoma", sans-serif; line-height:2; }
[lang="yue"], [lang="nan"], [lang="hak"] { font-family:Georgia, "Noto Serif CJK TC", "Source Han Serif TC", "PMingLiU", "Microsoft JhengHei", "Songti TC", serif; line-height:1.95; }
[lang="ja-easy"] { font-family:Georgia, "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", serif; line-height:2.3; }
ruby rt { font-size:.55em; color:var(--muted); letter-spacing:0; }
[lang="ko"] { font-family:"Noto Serif KR", "Batang", "Malgun Gothic", "Apple SD Gothic Neo", serif; line-height:1.9; }
[lang="fa"] { font-family:"Vazirmatn", "Noto Naskh Arabic", "Tahoma", "Segoe UI", serif; line-height:2.1; font-size:1.06em; }
[dir="rtl"] { text-align:right; }
@media (max-width:760px){
  .par { grid-template-columns:1fr; }
  .par .o { border-bottom:0; padding-bottom:.1rem; }
  nav#books { display:none }
  select#bookSel { display:block }
  header .brand { display:none }
  #q { width:9rem } #ref { width:8rem }
}
__READALOUD_CSS__
</style>
</head>
<body>
<header>
  <span class="brand">eBible — from the Hebrew, Aramaic &amp; Greek</span>
  <select id="bookSel"></select>
  <select id="tlSel" title="Translation language"></select>
  <label class="goto" title="Type a reference: Genesis 2:7, 1 Sam 3, Ps 23 — the page follows as you type"><span>Go to</span><input id="ref" placeholder="Genesis 2:7"></label>
  <input id="q" placeholder="Search the text…">
  <button class="fs" id="fsMinus" title="Smaller text">A−</button>
  <button class="fs" id="fsPlus" title="Larger text">A+</button>
  <button class="sources" id="sources" title="Source texts, licenses and attributions">Sources &amp; licenses</button>
</header>
<div class="layout">
<nav id="books"></nav>
<main id="main"></main>
</div>
<footer id="credits">
  <h2>Source texts, licenses and attributions</h2>
  <p><b>Hebrew and Aramaic text:</b> Westminster Leningrad Codex (public domain), from the Open Scriptures Hebrew Bible —
    “Original work of the Open Scriptures Hebrew Bible available at <a href="https://github.com/openscriptures/morphhb">https://github.com/openscriptures/morphhb</a>”
    (lemma and morphology data <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>; the verse text is public domain).</p>
  <p><b>Greek New Testament:</b> The SBL Greek New Testament, copyright 2010 Society of Biblical Literature and Logos Bible Software,
    licensed under <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>, <a href="https://github.com/LogosBible/SBLGNT">https://github.com/LogosBible/SBLGNT</a>.
    Modified: critical sigla removed.</p>
  <p><b>Byzantine text consulted:</b> Robinson–Pierpont Byzantine Majority Text (2018), public domain,
    <a href="https://github.com/byztxt/byzantine-majority-text">https://github.com/byztxt/byzantine-majority-text</a>.</p>
  <p><b>Septuagint (reference only, not translated):</b> H. B. Swete, <i>The Old Testament in Greek according to the Septuagint</i>
    (Cambridge, 1887–1909; public domain); digital edition by the Open Greek and Latin project, University of Leipzig, 2015,
    <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>,
    <a href="https://github.com/OpenGreekAndLatin/First1KGreek">https://github.com/OpenGreekAndLatin/First1KGreek</a> (data/tlg0527).</p>
  <p><b>Word tags, glosses and brief lexicon:</b> STEPBible data (Translators Amalgamated Hebrew OT and Greek NT, brief lexicons, morphology code
    expansions) created by <a href="https://www.STEPBible.org">STEPBible.org</a> based on work at Tyndale House, Cambridge,
    <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>, from <a href="https://github.com/STEPBible/STEPBible-Data">github.com/STEPBible</a>
    (reformatted for this reader; the original data is distributed only from that repository).</p>
  <p><b>Translations:</b> produced from the Hebrew, Aramaic and Greek above by a local language model, checked and corrected by the project.
    Full notes: LEGAL.md in the project repository.</p>
</footer>
<script>
const DATA = __DATA__;
const ORDER = __ORDER__;
const LANGS = __LANGS__;
const TARGETS = __TARGETS__;          // {code: {name, native}} in canonical order
const ABBREV = __ABBREV__;
const $ = s => document.querySelector(s);
const disp = b => b.replace(/_/g," ");

const allBooks = Object.keys(ORDER).sort((a,b) => ORDER[a]-ORDER[b]);
const srcBooks = allBooks.filter(b => DATA[b]);                          // navigable
const chapterList = book => Object.keys(DATA[book]).map(Number).sort((a,b)=>a-b);
const trOf = (b, c) => (DATA[b] && DATA[b][c] && DATA[b][c].tr) || {};
const haveTargets = Object.keys(TARGETS).filter(t => srcBooks.some(b => Object.values(DATA[b]).some(c => c.tr && c.tr[t])));
const booksWith = t => srcBooks.filter(b => Object.values(DATA[b]).some(c => c.tr && c.tr[t]));

/* ---------- translation language + view (persisted) ---------- */
let tl = localStorage.getItem("tl");
if (!haveTargets.includes(tl)) tl = haveTargets[0] || "en";
let view = localStorage.getItem("view") || "tr";   // tr | orig | par | all
function setView(v){ view = v; localStorage.setItem("view", v); route(); }
function setTl(t){ tl = t; localStorage.setItem("tl", t); $("#tlSel").value = t; if (view === "orig") view = "tr"; route(); }
const tlSel = $("#tlSel");
tlSel.innerHTML = haveTargets.map(t => `<option value="${t}">${TARGETS[t].native}</option>`).join("");
tlSel.value = tl;
tlSel.addEventListener("change", e => setTl(e.target.value));
if (haveTargets.length < 2) tlSel.style.display = "none";

/* ---------- text size ---------- */
let fs = +(localStorage.getItem("fs") || 18);
const applyFs = () => document.documentElement.style.setProperty("--fs", fs + "px");
applyFs();
$("#fsMinus").onclick = () => { fs = Math.max(14, fs - 1); localStorage.setItem("fs", fs); applyFs(); };
$("#fsPlus").onclick  = () => { fs = Math.min(26, fs + 1); localStorage.setItem("fs", fs); applyFs(); };

/* ---------- navigation ---------- */
function navRender(current) {
  let html = "", lastT = "";
  for (const b of allBooks) {
    const t = ORDER[b] <= 39 ? "Old Testament" : "New Testament";
    if (t !== lastT) { html += `<div class="t">${t}</div>`; lastT = t; }
    const nch = DATA[b] ? Object.keys(DATA[b]).length : 0;
    const ntr = DATA[b] ? Object.values(DATA[b]).filter(c => c.tr && c.tr[tl]).length : 0;
    const ct = ntr && ntr < nch ? `<span class="ct">${ntr}/${nch}</span>` : (ntr ? `<span class="ct">✓</span>` : "");
    html += `<a href="#${b}/1" class="${DATA[b]?(ntr?'':'untr'):'missing'} ${b===current?'on':''}">${disp(b)}${ct}</a>`;
  }
  $("#books").innerHTML = html;
  const sel = $("#bookSel");
  sel.innerHTML = srcBooks.map(b =>
    `<option value="${b}" ${b===current?'selected':''}>${disp(b)}</option>`).join("");
}
$("#bookSel").addEventListener("change", e => location.hash = `#${e.target.value}/1`);

function neighbours(book, ch) {
  const chs = chapterList(book);
  const i = chs.indexOf(+ch);
  let prev = i > 0 ? {b:book, c:chs[i-1]} : null;
  let next = i < chs.length-1 ? {b:book, c:chs[i+1]} : null;
  const bi = srcBooks.indexOf(book);
  if (!prev && bi > 0) { const pb = srcBooks[bi-1]; prev = {b:pb, c:chapterList(pb).at(-1)}; }
  if (!next && bi < srcBooks.length-1) { const nb = srcBooks[bi+1]; next = {b:nb, c:chapterList(nb)[0]}; }
  return {prev, next};
}

function esc(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;"); }

/* ---------- morphology: every Hebrew, Aramaic and Greek word tagged (STEPBible data, CC BY 4.0), loaded per book on demand ---------- */
const MORPH = {};                                        // morph/<Book>.js fills MORPH["Book name"]
const _loaded = {};
function loadJs(src){ return _loaded[src] || (_loaded[src] = new Promise((ok, no) => { const el = document.createElement("script"); el.src = src; el.onload = ok; el.onerror = () => { delete _loaded[src]; no(new Error(src)); }; document.head.appendChild(el); })); }
const morphLoad = book => MORPH[disp(book)] ? Promise.resolve() : loadJs(`morph/${book}.js`);
const lexLoad = () => typeof LEX !== "undefined" ? Promise.resolve() : loadJs("morph/lex.js");
const concLoad = () => typeof CONC !== "undefined" ? Promise.resolve() : loadJs("morph/conc.js");
const WRE = /[\p{L}\p{M}\p{N}]+(?:['\u2019][\p{L}\p{M}\p{N}]+)*/gu;   // same tokenizer as build_morph.py
const attr = t => esc(t).replace(/"/g, "&quot;");
function wrapSrc(text, book, ch, v){                     // words as spans; gloss + code attached when the book's tags are loaded
  const m = MORPH[disp(book)], vw = m && m[ch] && m[ch][v]; let i = 0, out = "", last = 0;
  for (const x of text.matchAll(WRE)) {
    const w = vw && vw[i];
    out += esc(text.slice(last, x.index)) + `<span class="w" data-k="${book}/${ch}/${v}/${i}"${w ? ` data-g="${attr(w[2])}" data-m="${attr(w[1])}"` : ""}>${esc(x[0])}</span>`;
    i++; last = x.index + x[0].length;
  }
  return out + esc(text.slice(last));
}
let inter = localStorage.getItem("inter") === "1";
function toggleInter(){ inter = !inter; localStorage.setItem("inter", inter ? "1" : "0"); route(); }
const TAGRE = /[HG]\d{4}[A-Za-z]?/g;
function rootTag(tags){ const m = tags.match(/\{([^}]+)\}/); return m ? m[1] : (tags.match(TAGRE) || [tags])[0]; }
function parseCode(code){                                // "HR/Ncfsa" -> "Preposition + Noun (Singular Feminine, Absolute)"; Greek codes are looked up whole
  if (typeof MORPHX === "undefined" || !code) return code || "";
  if (!/^[HA]/.test(code)) return MORPHX[code] || code;
  const lang = code[0], parts = code.split("/");
  return parts.map((p, i) => MORPHX[i ? lang + p : p] || MORPHX[p] || p).join(" + ");
}
const wpop = document.createElement("div"); wpop.id = "wpop"; wpop.hidden = true; document.body.appendChild(wpop);
let wsel = null;
function hidePop(){ wpop.hidden = true; if (wsel) { wsel.classList.remove("sel"); wsel = null; } }
async function showPop(el){
  const [book, ch, v, i] = el.dataset.k.split("/");
  await morphLoad(book); await lexLoad();
  const m = MORPH[disp(book)], d = m && m[ch] && m[ch][v] && m[ch][v][i];
  if (wsel) wsel.classList.remove("sel"); wsel = el; el.classList.add("sel");
  let html = `<div class="hw"><span class="orig">${esc(el.textContent)}</span>`;
  if (!d) { html += `</div><div class="pre">No tag for this word.</div>`; }
  else {
    const root = rootTag(d[0]), e = LEX[root], greek = /^G/.test(root);
    if (!greek) html += `<span class="tl">${esc(d[3])}</span>`;
    html += `</div>`;
    if (e) html += `<div><b class="orig">${esc(e[0])}</b><span class="tl">${esc(e[1])}</span><span class="pos">${esc(e[2])}</span> — ${esc(e[3])}</div>`;
    html += `<div class="parse">${esc(parseCode(d[1]))}<code>${esc(d[1])}</code></div>`;
    html += `<div>gloss: <b>${esc(d[2])}</b>${greek && d[3] && d[3] !== d[2] ? ` · <span class="tl">${esc(d[3])}</span>` : ""}</div>`;
    const extra = (d[0].match(TAGRE) || []).filter(t => t !== root && LEX[t]);
    if (extra.length) html += `<div class="pre">with: ${extra.map(t => `${esc(LEX[t][0])} <i>${esc(LEX[t][3])}</i>`).join(", ")}</div>`;
    if (e && e[4]) html += `<div class="meaning">${esc(e[4])}</div>`;
    html += `<div class="acts"><a onclick="showConc('${root}')">all occurrences</a><a onclick="gsOpen('${root}', '${attr(d[1])}')">this form elsewhere</a><a onclick="hidePop()">close</a></div>`;
  }
  wpop.innerHTML = html; wpop.hidden = false;
  const r = el.getBoundingClientRect(), W = wpop.offsetWidth, H = wpop.offsetHeight;
  let x = Math.min(r.left, window.innerWidth - W - 10), y = r.bottom + 6; if (y + H > window.innerHeight - 8) y = Math.max(8, r.top - H - 6);
  wpop.style.left = Math.max(8, x) + "px"; wpop.style.top = y + "px";
}
document.addEventListener("click", e => { const w = e.target.closest("main .w"); if (w) { showPop(w); return; } if (!e.target.closest("#wpop")) hidePop(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") hidePop(); });
window.addEventListener("hashchange", hidePop);
const byNum = {}; for (const b in ORDER) byNum[ORDER[b]] = b;
function verseHtml(b, ch, v, mark){                      // one source verse with token `mark` highlighted
  const src = DATA[b] && DATA[b][ch] && DATA[b][ch].src, t = src && src[v]; if (!t) return "";
  const L = LANGS[DATA[b][ch].lang || "hbo"]; let i = 0, out = "", last = 0;
  for (const x of t.matchAll(WRE)) { out += esc(t.slice(last, x.index)) + (i === mark ? `<mark>${esc(x[0])}</mark>` : esc(x[0])); i++; last = x.index + x[0].length; }
  return `<span class="orig ${L.script.toLowerCase()}" dir="${L.dir}">${out + esc(t.slice(last))}</span>`;
}
function hitsHtml(refs, cap){
  let html = "", n = 0, lastBook = null;
  for (const [bn, ch, v, i] of refs) {
    if (n++ >= cap) { html += `<p class="empty">… and ${refs.length - cap} more (narrow the search to see them)</p>`; break; }
    const b = byNum[bn]; if (!b) continue;
    if (b !== lastBook) { html += `<h3 style="font:600 13px system-ui,sans-serif;color:var(--muted);margin:1rem 0 .3rem">${disp(b)}</h3>`; lastBook = b; }
    html += `<div class="hit" onclick="location.hash='#${b}/${ch}/${v}'"><div class="ref">${disp(b)} ${ch}:${v}</div>${verseHtml(b, ch, v, i)}</div>`;
  }
  return html;
}
async function showConc(tag){                            // concordance: every occurrence of a lexeme, in canonical order
  hidePop(); await concLoad(); await lexLoad(); navRender(null);
  const refs = CONC[tag] || [], e = LEX[tag];
  const main = $("#main"); main.className = ""; main.setAttribute("dir", "ltr");
  main.innerHTML = `<h2><span class="orig">${e ? esc(e[0]) : esc(tag)}</span><small class="lang">${e ? esc(e[1]) + " · " + esc(e[3]) + " · " : ""}${tag} · ${refs.length} occurrence${refs.length === 1 ? "" : "s"}</small></h2>`
    + (e && e[4] ? `<p class="empty" style="margin:0 0 1rem">${esc(e[4])}</p>` : "") + `<div id="results">${hitsHtml(refs, 800)}</div>`;
  window.scrollTo(0, 0);
}
/* ---- grammar search: words by form, over the tagged text of the whole Bible (loaded on first use) ---- */
const GS = {
  H: {fn: {V:"Verb", N:"Noun", A:"Adjective", P:"Pronoun", R:"Preposition", C:"Conjunction", D:"Adverb", T:"Particle", S:"Suffix"},
      stem: {q:"Qal", N:"Niphal", p:"Piel", P:"Pual", h:"Hiphil", H:"Hophal", t:"Hithpael", o:"Polel", O:"Polal", r:"Hithpolel", m:"Poel", M:"Poal", k:"Palel", K:"Pulal", Q:"Qal passive", l:"Pilpel", L:"Polpal", f:"Hithpalpel", D:"Nithpael", j:"Pealal", i:"Pilel", u:"Hothpaal", c:"Tiphil", v:"Hishtaphel", w:"Nithpalel", y:"Nithpoel", z:"Hithpoel"},
      form: {p:"Perfect", q:"Sequential perfect", i:"Imperfect", w:"Sequential imperfect", h:"Cohortative", j:"Jussive", v:"Imperative", r:"Participle active", s:"Participle passive", a:"Infinitive absolute", c:"Infinitive construct"},
      person: {1:"1st", 2:"2nd", 3:"3rd"}, gender: {m:"masculine", f:"feminine", c:"common", b:"both"}, number: {s:"singular", p:"plural", d:"dual"}, state: {a:"absolute", c:"construct", d:"determined"}},
  G: {fn: {N:"Noun", A:"Adjective", T:"Article", V:"Verb", P:"Personal pronoun", R:"Relative pronoun", D:"Demonstrative pronoun", C:"Reciprocal pronoun", F:"Reflexive pronoun", S:"Possessive pronoun", I:"Interrogative pronoun", X:"Indefinite pronoun", K:"Correlative pronoun", Q:"Correlative/interrogative", PREP:"Preposition", CONJ:"Conjunction", ADV:"Adverb", PRT:"Particle", INJ:"Interjection", COND:"Conditional", HEB:"Hebrew word", ARAM:"Aramaic word"},
      tense: {P:"Present", I:"Imperfect", F:"Future", A:"Aorist", R:"Perfect", L:"Pluperfect"}, voice: {A:"Active", M:"Middle", P:"Passive", E:"Middle or passive", D:"Middle deponent", O:"Passive deponent", N:"Middle/passive deponent"},
      mood: {I:"Indicative", S:"Subjunctive", O:"Optative", M:"Imperative", N:"Infinitive", P:"Participle"}, person: {1:"1st", 2:"2nd", 3:"3rd"},
      kase: {N:"Nominative", G:"Genitive", D:"Dative", A:"Accusative", V:"Vocative"}, number: {S:"singular", P:"plural"}, gender: {M:"masculine", F:"feminine", N:"neuter"}}
};
const sel = (id, label, opts, val) => `<label>${label}<select id="gs_${id}"><option value="">any</option>${Object.entries(opts).map(([k, v]) => `<option value="${k}" ${k === val ? "selected" : ""}>${v}</option>`).join("")}</select></label>`;
function gsOpen(tag, code){
  hidePop(); navRender(null);
  const lang = (tag && /^G/.test(tag)) || (code && !/^[HA]/.test(code)) ? "G" : (code && code[0] === "A" ? "A" : "H");
  const main = $("#main"); main.className = ""; main.setAttribute("dir", "ltr");
  main.innerHTML = `<h2>Grammar search<small class="lang">words by form, whole Bible</small></h2><div class="gs" id="gsform"></div><div id="results"></div>`;
  const form = $("#gsform");
  const render = () => {
    const L = $("#gs_lang") ? $("#gs_lang").value : lang, g = GS[L === "G" ? "G" : "H"];
    let h = `<label>language<select id="gs_lang"><option value="H" ${L==="H"?"selected":""}>Hebrew</option><option value="A" ${L==="A"?"selected":""}>Aramaic</option><option value="G" ${L==="G"?"selected":""}>Greek</option></select></label>`;
    h += sel("fn", "function", g.fn, "");
    if (L !== "G") h += sel("stem", "stem (verbs)", g.stem, "") + sel("form", "form (verbs)", g.form, "") + sel("person", "person", g.person, "") + sel("gender", "gender", g.gender, "") + sel("number", "number", g.number, "") + sel("state", "state (nouns)", g.state, "");
    else h += sel("tense", "tense", g.tense, "") + sel("voice", "voice", g.voice, "") + sel("mood", "mood", g.mood, "") + sel("person", "person", g.person, "") + sel("kase", "case", g.kase, "") + sel("number", "number", g.number, "") + sel("gender", "gender", g.gender, "");
    h += `<label>lexeme tag (from a word's popup)<input id="gs_tag" value="${tag ? attr(tag) : ""}" placeholder="e.g. H1288A or G5485"></label>`;
    h += `<label>book<select id="gs_book"><option value="">all</option>${srcBooks.map(b => `<option value="${b}">${disp(b)}</option>`).join("")}</select></label>`;
    h += `<button id="gs_run">Search</button>`;
    form.innerHTML = h;
    $("#gs_lang").onchange = render;
    $("#gs_run").onclick = gsRun;
    if (code) { for (const f of gsFieldsFromCode(code)) { const el = $("#gs_" + f[0]); if (el) el.value = f[1]; } code = null; }
  };
  render();
}
function gsFieldsFromCode(code){                         // prefill the form from a word's code: "HVqp3ms" / "V-AAI-3S" / "N-NSF"
  const out = [];
  if (/^[HA]/.test(code)) { const c = code.split("/").pop().replace(/^[HA]/, ""), fn = c[0]; out.push(["fn", fn]);
    if (fn === "V") { out.push(["stem", c[1]], ["form", c[2]]); const t = c.slice(3); const p = t.match(/[123]/); if (p) out.push(["person", p[0]]); const g = t.match(/[mfcb]/); if (g) out.push(["gender", g[0]]); const n = t.match(/[spd]/); if (n) out.push(["number", n[0]]); }
    else if (fn === "N" || fn === "A") { const t = c.slice(2); if (t[0]) out.push(["gender", t[0]]); if (t[1]) out.push(["number", t[1]]); if (t[2]) out.push(["state", t[2]]); } }
  else { const parts = code.split("-"); out.push(["fn", parts[0]]);
    if (parts[0] === "V" && parts[1]) { const tvm = parts[1].replace(/^2/, ""); out.push(["tense", tvm[0]], ["voice", tvm[1]], ["mood", tvm[2]]); const t = parts[2] || ""; if (/^[123]/.test(t)) { out.push(["person", t[0]], ["number", t[1]]); } else if (t) { out.push(["kase", t[0]], ["number", t[1]], ["gender", t[2]]); } }
    else if (parts[1] && /^[NGDAV][SP][MFN]$/.test(parts[1])) out.push(["kase", parts[1][0]], ["number", parts[1][1]], ["gender", parts[1][2]]); }
  return out;
}
function gsMatch(code, q){                               // does a word's code satisfy the form
  if (!code) return false;
  if (q.lang !== "G") {
    const c = code.split("/").pop(); if (c[0] !== q.lang && !(code[0] === q.lang && code.split("/").length === 1)) { if (code[0] !== q.lang) return false; }
    const body = c.replace(/^[HA]/, "");
    if (q.fn && body[0] !== q.fn) return false;
    if (body[0] === "V") { if (q.stem && body[1] !== q.stem) return false; if (q.form && body[2] !== q.form) return false;
      const t = body.slice(3); if (q.person && !t.includes(q.person)) return false; if (q.gender && !t.includes(q.gender)) return false; if (q.number && !t.includes(q.number)) return false; }
    else { const t = body.slice(1); if (q.stem || q.form) return false; if (q.person && !t.includes(q.person)) return false; if (q.gender && !t.includes(q.gender)) return false; if (q.number && !t.includes(q.number)) return false; if (q.state && !t.endsWith(q.state)) return false; }
    return true;
  }
  const parts = code.split("-");
  if (q.fn && parts[0] !== q.fn) return false;
  if (parts[0] === "V") { const tvm = (parts[1] || "").replace(/^2/, ""); if (q.tense && tvm[0] !== q.tense) return false; if (q.voice && tvm[1] !== q.voice) return false; if (q.mood && tvm[2] !== q.mood) return false;
    const t = parts[2] || ""; if (q.person && t[0] !== q.person) return false; if (q.kase && !(t.length === 3 && t[0] === q.kase)) return false;
    if (q.number && !(t.length === 2 ? t[1] === q.number : t[1] === q.number)) return false; if (q.gender && t[2] !== q.gender) return false; }
  else { const t = parts[1] || ""; if (q.tense || q.voice || q.mood || q.person) return false; if (q.kase && t[0] !== q.kase) return false; if (q.number && t[1] !== q.number) return false; if (q.gender && t[2] !== q.gender) return false; }
  return true;
}
async function gsRun(){
  const val = id => ($("#gs_" + id) || {}).value || "";
  const q = {lang: val("lang"), fn: val("fn"), stem: val("stem"), form: val("form"), person: val("person"), gender: val("gender"), number: val("number"), state: val("state"),
             tense: val("tense"), voice: val("voice"), mood: val("mood"), kase: val("kase"), tag: val("tag").trim(), book: val("book")};
  const res = $("#results"); res.innerHTML = `<p class="empty">Loading the tagged text…</p>`;
  const books = q.book ? [q.book] : srcBooks.filter(b => (q.lang === "G") === (ORDER[b] > 39));
  let loadedN = 0;
  for (const b of books) { try { await morphLoad(b); } catch (e) {} loadedN++; if (loadedN % 8 === 0) res.innerHTML = `<p class="empty">Loading the tagged text… ${loadedN}/${books.length}</p>`; }
  const hits = [];
  for (const b of books) { const m = MORPH[disp(b)]; if (!m) continue;
    for (const ch in m) for (const v in m[ch]) { const ws = m[ch][v];
      for (let i = 0; i < ws.length; i++) { const w = ws[i]; if (!w) continue;
        if (q.tag && rootTag(w[0]) !== q.tag && !(w[0].match(TAGRE) || []).includes(q.tag)) continue;
        if (!gsMatch(w[1], q)) continue;
        hits.push([ORDER[b], +ch, +v, i]); if (hits.length >= 5000) break; } } }
  hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
  res.innerHTML = `<p class="empty">${hits.length}${hits.length >= 5000 ? "+" : ""} word${hits.length === 1 ? "" : "s"} found.</p>` + hitsHtml(hits, 600);
}
const vtag = (src, n) => src._lang ? `<span class="lt">${LANGS[src._lang[n]].name}</span>` : "";
const ruby = h => h.replace(/\{([^{}|\]]+)\|([^{}\]]+)[}\]]/g, "<ruby>$1<rt>$2</rt></ruby>");   // {漢字|かんじ} furigana notation
const flat = t => ruby(esc(t)).replace(/\n\n/g,"\n").trim();
const tdir = t => (TARGETS[t] && TARGETS[t].dir) || "ltr";

function renderChapter(book, ch, highlightVerse) {
  const chData = DATA[book] && DATA[book][ch];
  const main = $("#main");
  navRender(book);
  if (!chData) { main.innerHTML = `<p class="empty">${disp(book)} ${ch} is not in the source texts.</p>`; return; }
  const trs = chData.tr || {};
  const avail = Object.keys(TARGETS).filter(t => trs[t]);
  const shown = trs[tl] ? tl : avail[0];              // fall back to any translation this chapter has
  const tr = !!shown;
  const chs = chapterList(book);
  const src = chData.src, lang = chData.lang || "hbo", L = LANGS[lang];
  const rtl = L.dir === "rtl", ocls = "orig " + L.script.toLowerCase();
  const lxx = src && src._lxx;
  let v = view;
  if (!src) v = "tr";
  else if (!tr) v = ((v === "lxx" || v === "hl") && lxx) ? v : "orig";
  else if (v === "all" && avail.length < 2 && !lxx) v = "par";
  if ((v === "lxx" || v === "hl") && !lxx) v = "orig";
  let html = `<h2>${disp(book)} ${ch}<small class="lang">${L.name}${lxx ? " + Septuagint" : ""}${tr ? " → " + TARGETS[shown].name : ""}</small></h2>`;
  html += `<div class="chnav">` + chs.map(c =>
    `<a href="#${book}/${c}" class="${c==ch?'on':''} ${trOf(book,c)[tl]?'':'untr'}">${c}</a>`).join("") + `</div>`;
  if (src) {
    html += `<div class="tabs"><a class="${v==='orig'?'on':''}" onclick="setView('orig')">${L.name}</a>`;
    if (lxx) html += `<a class="${v==='lxx'?'on':''}" onclick="setView('lxx')" title="Swete's Septuagint">Septuagint</a><a class="${v==='hl'?'on':''}" onclick="setView('hl')" title="Hebrew and the Septuagint side by side">Hebrew · Septuagint</a>`;
    html += `<span class="sep"></span>`;
    for (const t of haveTargets)
      html += `<a class="${v==='tr'&&shown===t?'on':''} ${trs[t]?'':'off'}" onclick="setTl('${t}');setView('tr')">${TARGETS[t].native}</a>`;
    html += `<span class="sep"></span><a class="${v==='par'?'on':''} ${tr?'':'off'}" onclick="setView('par')">Side by side</a>`;
    html += `<a class="${v==='all'?'on':''} ${(avail.length + (lxx?1:0))>1?'':'off'}" onclick="setView('all')">Compare</a><a class="tool ${inter?'on':''}" onclick="toggleInter()" title="gloss and parsing under every Hebrew / Greek word">interlinear</a><a class="tool" onclick="gsOpen()" title="find words by grammatical form">grammar search</a></div>`;
  }
  main.className = ((v === "par" || v === "all" || v === "hl") ? "wide" : "") + (inter && src && (v === "orig" || v === "par" || v === "all" || v === "hl") ? " inter" : "");
  if (src && !MORPH[disp(book)]) morphLoad(book).then(() => { if (location.hash.slice(1).split("/").slice(0, 2).join("/") === `${book}/${ch}`) route(); }).catch(() => {});
  main.setAttribute("lang", (v === "orig" || v === "lxx" || v === "hl") ? "" : (shown || "en"));
  main.setAttribute("dir", (v === "tr" && shown) ? tdir(shown) : "ltr");
  if (!tr) html += `<p class="empty" style="margin:0 0 1.2rem">Not translated yet${src ? ` — showing the ${v === "lxx" ? "Septuagint" : L.name}.` : "."}</p>`;
  if (!tr && v !== "orig" && v !== "lxx" && v !== "hl" && v !== "all") { main.innerHTML = html; return; }
  const nums = Object.keys(v === "tr" ? trs[shown].verses : src).filter(k => !k.startsWith("_")).map(Number).sort((a,b)=>a-b);
  if (v === "orig") {
    for (const n of nums)
      html += `<p class="ov ${ocls}" dir="${rtl?'rtl':'ltr'}" id="v-${book}-${ch}-${n}"><sup class="v">${n}</sup>${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</p>`;
  } else if (v === "lxx") {
    for (const n of nums)
      html += `<p class="ov orig greek" id="v-${book}-${ch}-${n}"><sup class="v">${n}</sup>${lxx[n] ? esc(lxx[n]) : "<i style='color:var(--muted)'>— no aligned verse</i>"}</p>`;
  } else if (v === "hl") {                                   // Hebrew and Septuagint side by side
    html += `<div class="par">`;
    for (const n of nums)
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup class="v">${n}</sup>${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</div>
        <div class="o orig greek" id="v-${book}-${ch}-${n}"><sup class="v">${n}</sup>${lxx[n] ? esc(lxx[n]) : "<i style='color:var(--muted)'>— no aligned verse</i>"}</div>`;
    html += `</div>`;
  } else if (v === "par") {
    html += `<div class="par">`;
    for (const n of nums) {
      const e = trs[shown].verses[n];
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup class="v">${n}</sup>${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</div>
        <div class="e" lang="${shown}" dir="${tdir(shown)}" id="v-${book}-${ch}-${n}"><sup class="v">${n}</sup>${e ? flat(e) : "<i style='color:var(--muted)'>—</i>"}</div>`;
    }
    html += `</div>`;
  } else if (v === "all") {
    for (const n of nums) {
      html += `<div class="cmp" id="v-${book}-${ch}-${n}"><div class="row"><span class="lab">${L.name} ${n}</span><span class="txt ${ocls}" dir="${rtl?'rtl':'ltr'}">${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</span></div>`;
      if (lxx && lxx[n]) html += `<div class="row"><span class="lab">LXX</span><span class="txt orig greek">${esc(lxx[n])}</span></div>`;
      for (const t of avail) {
        const e = trs[t].verses[n];
        html += `<div class="row"><span class="lab">${TARGETS[t].native}</span><span class="txt" lang="${t}" dir="${tdir(t)}">${e ? flat(e) : "<i style='color:var(--muted)'>—</i>"}</span></div>`;
      }
      html += `</div>`;
    }
  } else {
    let para = [];
    const flush = () => { if (para.length) { html += `<p class="vv">${para.join(" ")}</p>`; para = []; } };
    for (const n of nums) {
      const t = trs[shown].verses[n];
      const vid = `v-${book}-${ch}-${n}`;
      if (t.includes("\n")) {
        flush();
        html += `<div class="poetry" id="${vid}"><sup class="v">${n}</sup>${ruby(esc(t)).replace(/\n\n/g,"\n").trimEnd()}</div>`;
      } else {
        para.push(`<span id="${vid}"><sup class="v">${n}</sup>${ruby(esc(t))}</span>`);
      }
    }
    flush();
    if (trs[shown].notes) {
      html += `<div class="notes">${ruby(esc(trs[shown].notes)).replace(/^Notes:?/i,"<b>Translator's notes</b>").replace(/\n/g,"<br>")}</div>`;
    }
  }
  const {prev, next} = neighbours(book, ch);
  html += `<div class="pn">
    <a class="${prev?'':'off'}" href="${prev?`#${prev.b}/${prev.c}`:'#'}">← ${prev?`${disp(prev.b)} ${prev.c}`:''}</a>
    <a class="${next?'':'off'}" href="${next?`#${next.b}/${next.c}`:'#'}">${next?`${disp(next.b)} ${next.c}`:''} →</a>
  </div>`;
  main.innerHTML = html;
  if (highlightVerse) {
    const el = document.getElementById(`v-${book}-${ch}-${highlightVerse}`);
    if (el) { el.scrollIntoView({block:"center"}); el.classList.add("flash"); }
  } else window.scrollTo(0,0);
}

/* ---------- reference finder ---------- */
function goRef(input) {
  const m = input.trim().toLowerCase().match(/^([1-3]?\s*[a-z ]+?)\s*(\d+)?(?::(\d+))?$/);
  if (!m) return false;
  let book = ABBREV[m[1].replace(/\s+/g,"")];
  if (!book) {
    const t = m[1].trim().replace(/\s+/g,"_").toLowerCase();
    book = allBooks.find(b => b.toLowerCase().startsWith(t));
  }
  if (!book) return false;
  location.hash = `#${book}/${m[2]||1}${m[3] ? "/"+m[3] : ""}`;
  return true;
}

/* ---------- search (in the selected translation) ---------- */
function search(q) {
  navRender(null);
  q = q.trim();
  const main = $("#main");
  main.className = ""; main.setAttribute("lang", tl);
  if (q.length < 2) { main.innerHTML = `<p class="empty">Type at least two characters.</p>`; return; }
  const rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"), "gi");
  const hits = [];
  outer:
  for (const book of booksWith(tl)) {
    for (const ch of chapterList(book)) {
      const t = trOf(book, ch)[tl];
      if (!t) continue;
      for (const [v, s] of Object.entries(t.verses)) {
        rx.lastIndex = 0;
        if (rx.test(s)) { hits.push({book, ch, v, t:s}); if (hits.length >= 200) break outer; }
      }
    }
  }
  let html = `<h2>Search: “${esc(q)}”<small class="lang">${TARGETS[tl].name}</small></h2><div id="results">`;
  html += `<p class="empty">${hits.length}${hits.length>=200?"+":""} verse${hits.length===1?"":"s"} found.</p>`;
  for (const h of hits) {
    rx.lastIndex = 0;
    html += `<div class="hit" lang="${tl}" dir="${tdir(tl)}" onclick="location.hash='#${h.book}/${h.ch}/${h.v}'">
      <div class="ref">${disp(h.book)} ${h.ch}:${h.v}</div>
      ${ruby(esc(h.t).replace(rx, m => `<mark>${m}</mark>`))}</div>`;
  }
  main.innerHTML = html + "</div>";
}

/* ---------- routing ---------- */
function route() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h) { const b = booksWith(tl)[0] || srcBooks[0]; if (b) location.hash = `#${b}/1`; return; }
  const [book, ch, v] = h.split("/");
  $("#q").value = "";
  renderChapter(book, ch, v ? +v : null);
}
let refDeb;                                   // the page follows the reference as it is typed; Enter is optional
$("#ref").addEventListener("input", e => {
  clearTimeout(refDeb);
  const val = e.target.value;
  refDeb = setTimeout(() => { if (val.trim()) goRef(val); }, 350);
});
$("#ref").addEventListener("keydown", e => {
  if (e.key === "Enter") { clearTimeout(refDeb); if (goRef(e.target.value)) e.target.value = ""; }
});
$("#ref").addEventListener("blur", e => { e.target.value = ""; });
let deb;
$("#q").addEventListener("input", e => {
  clearTimeout(deb);
  const val = e.target.value;
  deb = setTimeout(() => val.trim() ? search(val) : route(), 250);
});
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  const h = location.hash.slice(1).split("/");
  if (h.length < 2 || !DATA[h[0]]) return;
  const {prev, next} = neighbours(h[0], h[1]);
  if (e.key === "ArrowLeft" && prev) location.hash = `#${prev.b}/${prev.c}`;
  if (e.key === "ArrowRight" && next) location.hash = `#${next.b}/${next.c}`;
});
window.addEventListener("hashchange", route);
$("#sources").onclick = () => $("#credits").scrollIntoView({behavior:"smooth", block:"start"});
route();
__READALOUD_JS__
</script>
</body>
</html>
"""

_norm_cache = {}


def source_chapter(book_key, ch):
    """Original-language verses {n: text} and language code for one chapter."""
    meta = BY_SLUG.get(book_key)
    if not meta:
        return None, None
    if book_key not in _norm_cache:
        f = NORM_DIR / f"{meta['num']:02d}_{book_key}.json"
        _norm_cache[book_key] = json.loads(f.read_text(encoding="utf-8"))["chapters"] if f.exists() else {}
    verses = _norm_cache[book_key].get(str(ch))
    if not verses:
        return None, None
    lang = chapter_lang(meta, verses)
    src = {str(v["v"]): v["text"] for v in verses}
    if lang == "mixed":      # per-verse tags only where a chapter switches language
        src["_lang"] = {str(v["v"]): verse_lang(meta, v) for v in verses}
    lxx = {str(v["v"]): v["lxx"] for v in verses if v.get("lxx")}
    if lxx:
        src["_lxx"] = lxx    # Septuagint column, Greek, same verse numbers
    return src, lang


def main():
    data = {}
    # every chapter of every book: original text always, translations when present
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        key = slug(meta["name"])
        f = NORM_DIR / f"{meta['num']:02d}_{key}.json"
        if not f.exists():
            continue
        for ch in sorted(json.loads(f.read_text(encoding="utf-8"))["chapters"], key=int):
            src, lang = source_chapter(key, ch)
            data.setdefault(key, {})[str(ch)] = {"src": src, "lang": lang, "tr": {}}
    counts = {}
    for code in TARGETS:
        for f in sorted((OUT_ROOT / code / "json").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            entry = data.setdefault(slug(d["book"]), {}).setdefault(str(d["chapter"]), {"src": None, "lang": None, "tr": {}})
            entry["tr"][code] = {"verses": d["verses"], "notes": d.get("notes", "")}
            counts[code] = counts.get(code, 0) + 1
    SITE.mkdir(exist_ok=True)
    page = (PAGE
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__ORDER__", json.dumps(ORDER))
            .replace("__LANGS__", json.dumps({**LANGS, "mixed": MIXED}))
            .replace("__TARGETS__", json.dumps({c: {"name": t["name"], "native": t["native"], "dir": t.get("dir", "ltr")} for c, t in TARGETS.items()}, ensure_ascii=False))
            .replace("__ABBREV__", json.dumps(
                {k: v.replace(" ", "_") for k, v in ABBREV.items()}))
            .replace("__READALOUD_CSS__", RA.CSS)
            .replace("__READALOUD_JS__", RA.js('main', '.par .o, .par .e, .cmp .row .txt, p.ov, .poetry, .vv span, .hit, .notes')))
    out = SITE / "index.html"
    out.write_text(page, encoding="utf-8")
    nch = sum(len(v) for v in data.values())
    tr = ", ".join(f"{c}={n}" for c, n in counts.items()) or "none"
    print(f"site built: {out} ({len(data)} books, {nch} chapters of original text; "
          f"translated chapters: {tr}; {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
