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
#wpop .syn { margin:.35rem 0; font-size:12px; } #wpop .syn b { color:var(--fg); font-weight:600; }
#wpop .syn a { color:var(--accent); cursor:pointer; } #wpop .dom { font-size:12px; color:var(--muted); margin-top:.25rem; }
#wpop .dom .orig { color:var(--fg); } .w.ante { outline:2px solid var(--accent); border-radius:3px; }
#wpop .ours { border-top:1px solid var(--border); margin-top:.55rem; padding-top:.5rem; }
#wpop .ours h5 { font:600 10px system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:0 0 .3rem; }
#wpop .sense { margin:0 0 .3rem; } #wpop .sense b { font-weight:600; } #wpop .sense i { color:var(--muted); font-style:normal; font-size:11px; }
#wpop .sense a, #wpop .idiom a { color:var(--accent); cursor:pointer; margin-left:.3em; }
#wpop .idiom, #wpop .near, #wpop .usage, #wpop .cav { font-size:12px; color:var(--muted); margin-top:.3rem; }
.tabs a.tool { border-style:dashed; }
.gs { display:grid; grid-template-columns:repeat(auto-fill,minmax(11rem,1fr)); gap:.5rem .8rem; margin:.6rem 0 1rem; font:13px system-ui,sans-serif; }
.gs label { display:flex; flex-direction:column; gap:.2rem; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }
.gs select, .gs input { font:14px system-ui,sans-serif; padding:.35rem .5rem; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--fg); }
.gs button { grid-column:1 / -1; justify-self:start; font:14px system-ui,sans-serif; padding:.45rem 1rem; border:1px solid var(--accent); border-radius:8px; background:var(--accent); color:#fff; cursor:pointer; }
.hit .orig { display:block; margin-top:.15rem; } .hit mark { background:var(--hl); color:inherit; border-radius:3px; }
sup.v { cursor:pointer; } sup.v:hover { text-decoration:underline; }
#vpop { position:fixed; z-index:40; width:min(30rem,92vw); max-height:70vh; overflow:auto; background:var(--card); color:var(--fg);
  border:1px solid var(--border); border-radius:10px; box-shadow:0 10px 30px rgba(0,0,0,.25); padding:.7rem .9rem;
  font:13px/1.5 system-ui,sans-serif; white-space:normal; direction:ltr; text-align:left; }
#vpop h4 { font:600 11px system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:.6rem 0 .3rem; }
#vpop h4:first-child { margin-top:0; }
#vpop .r { padding:.25rem .4rem; border-radius:6px; cursor:pointer; display:grid; grid-template-columns:7.5rem 1fr; gap:.5rem; align-items:baseline; }
#vpop .r:hover { background:var(--soft); } #vpop .r b { font:600 12px system-ui,sans-serif; color:var(--accent); }
#vpop .r span { color:var(--muted); overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
#vpop .cls { float:right; cursor:pointer; color:var(--muted); }
.harm { border-bottom:1px solid var(--border); padding:.6rem 0; }
.harm .vs { display:grid; gap:.4rem 1.2rem; align-items:start; }
.harm .vs > div { min-width:0; }
.harm .lab { font:600 11px system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.15rem; cursor:pointer; }
.harm .lab:hover { color:var(--accent); } .harm .lab small { text-transform:none; letter-spacing:0; opacity:.7; }
.harm .txt { white-space:pre-wrap; } .harm .txt.dim { color:var(--muted); }
#map { width:100%; height:auto; background:var(--card); border:1px solid var(--border); border-radius:10px; touch-action:none; cursor:grab; }
#map.drag { cursor:grabbing; }
#map .coast { fill:none; stroke:var(--border); stroke-width:1.2; }
#map .land { fill:var(--soft); }
#map .water { fill:var(--bg); stroke:var(--border); stroke-width:.8; }
#map .river { fill:none; stroke:var(--border); stroke-width:.7; opacity:.8; }
#map .pin { fill:var(--accent); stroke:var(--card); stroke-width:1.2; cursor:pointer; }
#map .pin.on { fill:var(--err); }
#map .plab { font:10px system-ui,sans-serif; fill:var(--fg); pointer-events:none; paint-order:stroke; stroke:var(--bg); stroke-width:2.5px; }
.mapbar { display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.5rem 0; font:13px system-ui,sans-serif; color:var(--muted); }
.mapbar button { font:13px system-ui,sans-serif; padding:.25rem .6rem; border:1px solid var(--border); border-radius:7px; background:var(--card); color:var(--fg); cursor:pointer; }
.plist { display:grid; grid-template-columns:repeat(auto-fill,minmax(13rem,1fr)); gap:.2rem .8rem; margin:.6rem 0 1rem; font:13px system-ui,sans-serif; }
.plist a { cursor:pointer; padding:.15rem .3rem; border-radius:5px; } .plist a:hover { background:var(--soft); }
.plist a small { color:var(--muted); }
.chron { margin:.8rem 0 1.4rem; font:13px/1.5 system-ui,sans-serif; }
.chron h3 { font:600 11px system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:1.1rem 0 .4rem; }
.chron .row { display:grid; grid-template-columns:7rem 1fr; gap:.6rem; padding:.25rem .4rem; border-radius:6px; align-items:baseline; }
.chron .row:hover { background:var(--soft); } .chron .row b { color:var(--accent); font:600 12px system-ui,sans-serif; cursor:pointer; }
.chron .row .q { color:var(--muted); } .chron .num { font-variant-numeric:tabular-nums; color:var(--fg); font-weight:600; }
.chron .anch { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.3rem .4rem; border-bottom:1px solid var(--border); }
.chron .anch .y { font-variant-numeric:tabular-nums; font-weight:600; }
.chron .anch .basis { color:var(--muted); font-size:12px; }
.chron .note { color:var(--muted); margin:.4rem 0 0; }
#vpop .pl { font-size:12px; } #vpop .pl a { color:var(--accent); cursor:pointer; margin-right:.6em; }
#vpop .ap { font-size:12px; padding:.2rem .4rem; }
#vpop .ap .rd { font-size:1.15em; } #vpop .ap .ed { color:var(--muted); }
#vpop .ap .kind { font:600 10px system-ui,sans-serif; text-transform:uppercase; letter-spacing:.05em; color:var(--accent); margin-right:.4em; }
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
  <p><b>Cross-references:</b> the <i>Treasury of Scripture Knowledge</i> (1830s, public domain) as extended and voted on by readers at
    <a href="https://www.openbible.info/labs/cross-references/">OpenBible.info</a>, <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
    Parallel passages are computed from the word tags above, not taken from any harmony.</p>
  <p><b>Places and the map:</b> place identifications and coordinates from the <a href="https://www.openbible.info/geo/">OpenBible.info</a> Bible geocoding data,
    <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> (the 2007 tab-delimited release; the newer dataset mixing in OpenStreetMap geometry is not used).
    Coastlines, lakes and rivers from <a href="https://www.naturalearthdata.com/">Natural Earth</a>, public domain — drawn here as vectors, with no map service or tiles.</p>
  <p><b>Text notes:</b> which printed editions carry each reading, and the scribal Qere against the written Ketiv, are from the STEPBible data above
    (CC BY 4.0). Editions compared: Nestle-Aland 27 and 28, Tyndale House 2017, SBLGNT, Westcott-Hort 1881, Tregelles, Scrivener's Textus Receptus 1894 and the
    Robinson-Pierpont Byzantine text. This is an apparatus of editions, not of manuscripts: no manuscript is cited, because no openly licensed manuscript apparatus exists for this project to use.</p>
  <p><b>Clause roles, participants and semantic domains (Greek New Testament):</b> the
    <a href="https://github.com/Clear-Bible/macula-greek">MACULA Greek linguistic datasets</a> © 2022-2024 Biblica, Inc.,
    <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> — syntactic role, word class, the word a pronoun refers back to, and the
    Louw-Nida domain number. Only the domain number is used; the domain titles are copyrighted and are not reproduced, so the reader shows the words that share a domain instead.</p>
  <p><b>Chronology:</b> the numbers are extracted from this project's own English translation by pattern, each shown with its verse; nothing is summed into a date.
    The anchor dates are entered by hand from Assyrian, Babylonian, Persian and Roman records and are marked as externally attested. No copyrighted chronology
    (Thiele, Finegan or any other) is used.</p>
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

/* ---------- chronology: what the text counts, and the dates outside records fix ---------- */
const chronLoad = () => typeof CHRON !== "undefined" ? Promise.resolve() : loadJs("morph/chron.js");
const KIND = {"age-father": "age at fathering", "age-at": "age at the time", "lifespan": "length of life",
              "reigned": "length of reign", "synchronism": "dated by another reign", "since": "years since an event", "span": "a span of years"};
async function renderChron(book, ch, head){
  const main = $("#main");
  main.innerHTML = head + `<p class="empty">Loading chronology…</p>`;
  try { await chronLoad(); } catch (e) { main.innerHTML = head + `<p class="empty">Chronology is not built — run scripts/build_chronology.py.</p>`; return; }
  const here = CHRON.data.filter(r => r[0] === disp(book) && r[1] == ch);
  const inBook = CHRON.data.filter(r => r[0] === disp(book));
  let html = head + `<div class="chron">`;
  html += `<p class="note">Every line below is a number the text itself states, with the verse it stands in. Nothing here is added up into a date: totals depend on choices this project does not make for you.</p>`;
  html += `<h3>In ${disp(book)} ${ch}</h3>`;
  html += here.length ? here.map(r => chronRow(r)).join("")
    : `<p class="empty">No chronological statement in this chapter.</p>`;
  if (inBook.length > here.length) {
    html += `<h3>Elsewhere in ${disp(book)} <span style="text-transform:none;font-weight:400">(${inBook.length - here.length})</span></h3>`;
    html += inBook.filter(r => r[1] != ch).slice(0, 60).map(r => chronRow(r, true)).join("");
    if (inBook.length - here.length > 60) html += `<p class="empty">… and ${inBook.length - here.length - 60} more</p>`;
  }
  html += `<h3>Dates fixed by records outside the Bible</h3>`;
  html += `<p class="note">These are the only absolute years this project asserts. They come from Assyrian, Babylonian, Persian and Roman records, not from the biblical text, and several are still argued over.</p>`;
  html += CHRON.anchors.map(([y, label, basis]) =>
    `<div class="anch"><span class="y">${y < 0 ? Math.abs(y) + " BC" : "AD " + y}</span><span>${esc(label)}<div class="basis">${esc(basis)}</div></span></div>`).join("");
  main.innerHTML = html + `</div>`;
}
function chronRow(r, withRef){
  const [b, c, v, kind, who, n, unit, of, text] = r;
  return `<div class="row"><b onclick="location.hash='#${b.replace(/ /g, "_")}/${c}/${v}'">${withRef ? esc(b) + " " : ""}${c}:${v}</b>
    <span><span class="num">${n}</span> ${esc(unit)} — ${esc(KIND[kind] || kind)}${who ? " · " + esc(who) : ""}${of ? " · of " + esc(of) : ""}
    <div class="q">“${esc(text)}”</div></span></div>`;
}

/* ---------- places: where the chapter happens, drawn offline (OpenBible.info CC BY 4.0 + Natural Earth, public domain) ---------- */
const placesLoad = () => typeof PLACES !== "undefined" ? Promise.resolve() : loadJs("morph/places.js");
const SYN = {}, synLoad = book => SYN[disp(book)] ? Promise.resolve() : loadJs(`morph/syn_${book}.js`);
const domLoad = () => typeof DOMAINS !== "undefined" ? Promise.resolve() : loadJs("morph/domains.js");
function synHtml(book, ch, v, i){
  const w = (((SYN[disp(book)] || {})[ch] || {})[v] || [])[i]; if (!w) return "";
  const [role, cls, dom, refTo] = w;
  let h = "";
  if (role || cls) h += `<div class="syn">In the clause: <b>${esc(role || cls)}</b>${role && cls && role !== cls ? ` (${esc(cls)})` : ""}`;
  if (refTo) { const [b2, c2, v2, i2] = refTo.split("|");
    const t = (((SYN[disp(b2)] || {})[c2] || {})[v2] || [])[i2];
    h += `${h ? " · " : `<div class="syn">`}refers to <a onclick="gotoWord('${b2.replace(/ /g, "_")}',${c2},${v2},${i2})">${esc((t && t[4]) || "the earlier word")} (${esc(b2)} ${c2}:${v2})</a>`; }
  if (h) h += `</div>`;
  if (dom && typeof DOMAINS !== "undefined" && DOMAINS[dom]) {
    const others = DOMAINS[dom].slice(0, 12);
    h += `<div class="dom">Same semantic domain (${esc(dom)}): ${others.map(o => `<span class="orig greek">${esc(o[1])}</span> <i>${esc(o[2])}</i>`).join(" · ")}</div>`;
  }
  return h;
}
function gotoWord(book, ch, v, i){
  hidePop();
  location.hash = `#${book}/${ch}/${v}`;
  setTimeout(() => { const el = document.querySelector(`main .w[data-k="${book}/${ch}/${v}/${i}"]`); if (el) { el.classList.add("ante"); el.scrollIntoView({block: "center"}); setTimeout(() => el.classList.remove("ante"), 4000); } }, 500);
}
const APP = {}, appLoad = book => APP[disp(book)] ? Promise.resolve() : Promise.all([loadJs(`morph/app_${book}.js`), typeof APPED !== "undefined" ? 0 : loadJs("morph/app_meta.js")]);
const edName = e => (typeof APPED !== "undefined" && APPED[e]) || e;
function appHtml(book, ch, v, script){
  const rows = ((APP[disp(book)] || {})[ch] || {})[v] || []; if (!rows.length) return "";
  let h = `<h4>Text notes <span style="font-weight:400;text-transform:none">(printed editions and the scribal tradition — not manuscripts)</span></h4>`;
  for (const [kind, reading, have, lack, note] of rows) {
    if (kind === "var") h += `<div class="ap"><span class="kind">reading</span><span class="rd orig ${script}">${esc(reading)}</span>`
      + `<div class="ed">in ${esc(have.split("+").map(edName).join(", "))}${lack ? `; not in ${esc(lack.split("+").map(edName).join(", "))}` : ""}</div></div>`;
    else if (kind === "qere") h += `<div class="ap"><span class="kind">qere</span><span class="rd orig ${script}">${esc(reading)}</span> <span class="ed">read for the written text${note ? " — " + esc(note) : ""}</span></div>`;
    else h += `<div class="ap"><span class="kind">${kind === "sp" ? "spelling" : "variant"}</span><span class="rd orig ${script}">${esc(reading)}</span> <span class="ed">${esc(note)}</span></div>`;
  }
  return h;
}
const placesOf = (b, c, v) => (typeof VPLACES !== "undefined" && VPLACES[`${disp(b)}|${c}|${v}`]) || [];
function chapterPlaces(book, ch){
  const out = new Map(), src = (DATA[book] && DATA[book][ch] || {}).src || {};
  for (const n of Object.keys(src).filter(k => !k.startsWith("_"))) for (const name of placesOf(book, ch, n)) {
    if (!PLACES[name]) continue;
    if (!out.has(name)) out.set(name, []);
    out.get(name).push(+n);
  }
  return out;
}
let mapView = null;                                      // {x, y, k} pan and zoom
function mapXY(name){ const p = PLACES[name], b = MAPSVG.box; return [(p[1] - b[0]) / (b[2] - b[0]) * MAPSVG.w, (b[3] - p[0]) / (b[3] - b[1]) * MAPSVG.h]; }
function drawMap(names, focus){
  const pts = names.map(n => mapXY(n));
  let vb;
  if (mapView) vb = mapView;
  else if (pts.length) {                                 // frame the chapter's places with a margin
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const pad = Math.max(60, (Math.max(...xs) - Math.min(...xs)) * .25, (Math.max(...ys) - Math.min(...ys)) * .25);
    let x0 = Math.min(...xs) - pad, y0 = Math.min(...ys) - pad, x1 = Math.max(...xs) + pad, y1 = Math.max(...ys) + pad;
    const w = Math.max(x1 - x0, (y1 - y0) * 1.6), h = w / 1.6;
    vb = mapView = {x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2, w, h};
  } else vb = mapView = {x: 0, y: 0, w: MAPSVG.w, h: MAPSVG.h};
  const scale = MAPSVG.w / vb.w, lab = names.length <= 40 || scale > 2;
  return `<svg id="map" viewBox="${vb.x.toFixed(1)} ${vb.y.toFixed(1)} ${vb.w.toFixed(1)} ${vb.h.toFixed(1)}" preserveAspectRatio="xMidYMid meet" style="aspect-ratio:1.6">
    <g>${MAPSVG.coast.map(d => `<path class="coast" d="${d}"/>`).join("")}
       ${MAPSVG.rivers.map(d => `<path class="river" d="${d}"/>`).join("")}
       ${MAPSVG.lakes.map(d => `<path class="water" d="${d}"/>`).join("")}</g>
    <g>${names.map((n, i) => { const [x, y] = pts[i]; const on = n === focus;
      return `<circle class="pin ${on ? "on" : ""}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(on ? 5 : 3.5) / Math.sqrt(scale)}" data-p="${attr(n)}"><title>${esc(n)}</title></circle>`
        + (lab ? `<text class="plab" x="${(x + 5 / Math.sqrt(scale)).toFixed(1)}" y="${(y + 3 / Math.sqrt(scale)).toFixed(1)}" style="font-size:${(10 / Math.sqrt(scale)).toFixed(1)}px">${esc(n)}</text>` : "");
    }).join("")}</g></svg>`;
}
function mapControls(){
  const svg = $("#map"); if (!svg) return;
  const apply = () => { svg.setAttribute("viewBox", `${mapView.x.toFixed(1)} ${mapView.y.toFixed(1)} ${mapView.w.toFixed(1)} ${mapView.h.toFixed(1)}`); };
  svg.onwheel = e => { e.preventDefault(); const r = svg.getBoundingClientRect();
    const mx = mapView.x + (e.clientX - r.left) / r.width * mapView.w, my = mapView.y + (e.clientY - r.top) / r.height * mapView.h;
    const k = e.deltaY > 0 ? 1.2 : 1 / 1.2; const w = Math.min(MAPSVG.w * 2, Math.max(30, mapView.w * k)), h = w / 1.6;
    mapView = {x: mx - (mx - mapView.x) * (w / mapView.w), y: my - (my - mapView.y) * (h / mapView.h), w, h}; apply(); };
  let drag = null;
  svg.onpointerdown = e => { drag = {x: e.clientX, y: e.clientY, vx: mapView.x, vy: mapView.y}; svg.setPointerCapture(e.pointerId); svg.classList.add("drag"); };
  svg.onpointermove = e => { if (!drag) return; const r = svg.getBoundingClientRect();
    mapView.x = drag.vx - (e.clientX - drag.x) / r.width * mapView.w; mapView.y = drag.vy - (e.clientY - drag.y) / r.height * mapView.h; apply(); };
  svg.onpointerup = svg.onpointercancel = () => { drag = null; svg.classList.remove("drag"); };
  svg.addEventListener("click", e => { const c = e.target.closest(".pin"); if (c) showPlace(c.dataset.p); });
}
function showPlace(name, book, ch){
  const p = PLACES[name]; if (!p) return;
  const cur = location.hash.slice(1).split("/");
  mapView = {x: mapXY(name)[0] - 90, y: mapXY(name)[1] - 56, w: 180, h: 112};
  renderMapInto(book || cur[0], ch || cur[1], name);
}
async function renderMap(book, ch, head){
  const main = $("#main");
  main.innerHTML = head + `<p class="empty">Loading places…</p>`;
  try { await placesLoad(); } catch (e) { main.innerHTML = head + `<p class="empty">Place data is not built — run scripts/build_places.py.</p>`; return; }
  mapView = null;
  renderMapInto(book, ch, null, head);
}
function renderMapInto(book, ch, focus, head){
  const main = $("#main");
  const found = chapterPlaces(book, ch);
  const names = [...found.keys()];
  head = head || main.dataset.head || "";
  main.dataset.head = head;
  if (!names.length) { main.innerHTML = head + `<p class="empty">No identified places in ${disp(book)} ${ch}. Place names come from the OpenBible.info geocoding data; many chapters mention none.</p>`; return; }
  let html = head + `<div class="mapbar"><b style="color:var(--fg)">${names.length} place${names.length === 1 ? "" : "s"}</b> in ${disp(book)} ${ch}
      <button onclick="mapView=null;renderMapInto('${book}',${ch},null)">fit</button>
      <button onclick="mapView={x:0,y:0,w:MAPSVG.w,h:MAPSVG.h};renderMapInto('${book}',${ch},null)">whole map</button>
      <span>scroll to zoom, drag to pan</span></div>`;
  html += drawMap(names, focus);
  html += `<div class="plist">` + names.sort().map(n => {
    const vs = found.get(n), p = PLACES[n];
    return `<a onclick="showPlace('${attr(n)}','${book}',${ch})">${esc(n)} <small>${vs.slice(0, 4).join(", ")}${vs.length > 4 ? "…" : ""}${p[3] ? " · " + esc(p[3]) : ""}</small></a>`;
  }).join("") + `</div>`;
  const f = focus && PLACES[focus];
  if (f) html += `<p class="empty">${esc(focus)} — ${f[0].toFixed(3)}°N, ${f[1].toFixed(3)}°E${f[2] ? " · located from " + esc(f[2]) : ""}${f[3] ? " · " + esc(f[3]) : ""}</p>`;
  main.innerHTML = html;
  mapControls();
}

/* ---------- cross-references (OpenBible.info, CC BY 4.0) and parallels (computed from the word tags) ---------- */
const XREF = {}, xrefLoad = book => XREF[disp(book)] ? Promise.resolve() : loadJs(`morph/xref_${book}.js`);
const parLoad = () => typeof PAR !== "undefined" ? Promise.resolve() : loadJs("morph/parallels.js");
const vnum = (b, c, n) => `<sup class="v" onclick="showRefs('${b}',${c},${n},event)">${n}</sup>`;
function verseText(b, c, v){                            // the shown translation if there is one, else the original
  const d = DATA[b] && DATA[b][c]; if (!d) return ["", "en", "ltr"];
  const t = d.tr && (d.tr[tl] || d.tr[Object.keys(d.tr)[0]]);
  if (t && t.verses[v]) return [t.verses[v].replace(/\n+/g, " "), d.tr[tl] ? tl : Object.keys(d.tr)[0], "ltr"];
  const src = d.src && d.src[v]; const L = LANGS[d.lang || "hbo"];
  return src ? [src, "", L.dir] : ["", "", "ltr"];
}
const vpop = document.createElement("div"); vpop.id = "vpop"; vpop.hidden = true; document.body.appendChild(vpop);
function hideRefs(){ vpop.hidden = true; }
function refRow(b, c, v, end, note){
  const [txt, lang, dir] = verseText(b, c, v);
  return `<div class="r" onclick="location.hash='#${b}/${c}/${v}';hideRefs()"><b>${disp(b)} ${c}:${v}${end && end > v ? "–" + end : ""}${note ? ` <span style="font-weight:400;color:var(--muted)">${note}</span>` : ""}</b><span lang="${lang}" dir="${dir}">${ruby(esc(txt))}</span></div>`;
}
async function showRefs(book, ch, v, ev){
  if (ev) ev.stopPropagation();
  await Promise.all([xrefLoad(book).catch(() => {}), parLoad().catch(() => {}), placesLoad().catch(() => {}), appLoad(book).catch(() => {})]);
  const xr = ((XREF[disp(book)] || {})[ch] || {})[v] || [];
  const pr = typeof PAR !== "undefined" ? (((PAR[disp(book)] || {})[ch] || {})[v] || []) : [];
  let html = `<span class="cls" onclick="hideRefs()">✕</span><h4>${disp(book)} ${ch}:${v}</h4>`;
  const pls = (typeof PLACES !== "undefined" ? placesOf(book, ch, v).filter(n => PLACES[n]) : []);
  if (pls.length) html += `<div class="pl">Places: ${pls.map(n => `<a onclick="hideRefs();setView('map');setTimeout(()=>showPlace('${attr(n)}','${book}',${ch}),300)">${esc(n)}</a>`).join("")}</div>`;
  if (pr.length) html += `<h4>Parallel passages</h4>` + pr.map(r => refRow(r[0].replace(/ /g, "_"), r[1], r[2], 0, Math.round(r[3] * 100) + "% shared wording")).join("");
  if (xr.length) html += `<h4>Cross-references <span style="font-weight:400;text-transform:none">(Treasury of Scripture Knowledge via OpenBible.info)</span></h4>`
    + xr.slice(0, 25).map(r => refRow(r[0].replace(/ /g, "_"), r[1], r[2], r[3], "")).join("");
  html += appHtml(book, ch, v, ((LANGS[(DATA[book] && DATA[book][ch] || {}).lang || "hbo"] || {}).script || "hebrew").toLowerCase());
  if (!pr.length && !xr.length && !((APP[disp(book)] || {})[ch] || {})[v]) html += `<p class="empty">No cross-references, parallels or text notes for this verse.</p>`;
  vpop.innerHTML = html; vpop.hidden = false;
  const el = ev && ev.target, r = el ? el.getBoundingClientRect() : {left: 40, bottom: 80, top: 80};
  const W = vpop.offsetWidth, H = vpop.offsetHeight;
  let x = Math.min(r.left, window.innerWidth - W - 10), y = r.bottom + 6;
  if (y + H > window.innerHeight - 8) y = Math.max(8, window.innerHeight - H - 8);
  vpop.style.left = Math.max(8, x) + "px"; vpop.style.top = y + "px";
}
document.addEventListener("click", e => { if (!e.target.closest("#vpop") && !e.target.closest("sup.v")) hideRefs(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") hideRefs(); });
window.addEventListener("hashchange", hideRefs);
async function renderHarmony(book, ch, head, shown){    // the chapter beside its parallels, verse by verse
  const main = $("#main");
  main.innerHTML = head + `<p class="empty">Loading parallels…</p>`;
  await parLoad().catch(() => {});
  const P = typeof PAR !== "undefined" ? (PAR[disp(book)] || {})[ch] || {} : {};
  const src = (DATA[book][ch] || {}).src || {};
  const nums = Object.keys(src).filter(k => !k.startsWith("_")).map(Number).sort((a, b) => a - b);
  const freq = {}; for (const r of Object.values(P).flat()) freq[r[0]] = (freq[r[0]] || 0) + 1;      // the books this chapter most parallels, at most four columns
  const others = Object.keys(freq).sort((a, b) => freq[b] - freq[a]).slice(0, 4).sort((a, b) => ORDER[a.replace(/ /g, "_")] - ORDER[b.replace(/ /g, "_")]);
  let html = head;
  if (!others.length) { main.innerHTML = head + `<p class="empty">No parallel passages found for ${disp(book)} ${ch}. Parallels are computed for the Gospels, for Samuel–Kings–Chronicles with Isaiah, Jeremiah, Psalms and Micah, and within the Torah.</p>`; return; }
  const cols = [disp(book), ...others];
  html += `<p class="empty" style="margin:0 0 .6rem">Verses sharing wording with ${others.join(", ")}. Percentages are shared vocabulary, weighted by how rare each word is.</p>`;
  html += `<div class="harm" style="position:sticky;top:3.2rem;background:var(--bg);z-index:2;padding-top:.2rem"><div class="vs" style="grid-template-columns:repeat(${cols.length},1fr)">`
    + cols.map(c => `<div class="lab" style="cursor:default">${c}</div>`).join("") + `</div></div>`;
  for (const n of nums) {
    const hits = P[n] || [];
    const cells = cols.map(cname => {
      if (cname === disp(book)) {
        const [txt, lang, dir] = verseText(book, ch, n);
        return `<div><div class="lab" onclick="location.hash='#${book}/${ch}/${n}'">${disp(book)} ${ch}:${n}</div><div class="txt" lang="${lang}" dir="${dir}">${ruby(esc(txt))}</div></div>`;
      }
      const h = hits.filter(r => r[0] === cname).sort((a, b) => b[3] - a[3])[0];
      if (!h) return `<div></div>`;
      const b2 = h[0].replace(/ /g, "_"), [txt, lang, dir] = verseText(b2, h[1], h[2]);
      return `<div><div class="lab" onclick="location.hash='#${b2}/${h[1]}/${h[2]}'">${h[0]} ${h[1]}:${h[2]} <small>${Math.round(h[3] * 100)}%</small></div><div class="txt dim" lang="${lang}" dir="${dir}">${ruby(esc(txt))}</div></div>`;
    }).join("");
    html += `<div class="harm" id="v-${book}-${ch}-${n}"><div class="vs" style="grid-template-columns:repeat(${cols.length},1fr)">${cells}</div></div>`;
  }
  main.innerHTML = html;
}

/* ---------- morphology: every Hebrew, Aramaic and Greek word tagged (STEPBible data, CC BY 4.0), loaded per book on demand ---------- */
const MORPH = {};                                        // morph/<Book>.js fills MORPH["Book name"]
const _loaded = {};
function loadJs(src){ return _loaded[src] || (_loaded[src] = new Promise((ok, no) => { const el = document.createElement("script"); el.src = src; el.onload = ok; el.onerror = () => { delete _loaded[src]; no(new Error(src)); }; document.head.appendChild(el); })); }
const morphLoad = book => MORPH[disp(book)] ? Promise.resolve() : loadJs(`morph/${book}.js`);
const lexLoad = () => typeof LEX !== "undefined" ? Promise.resolve() : loadJs("morph/lex.js");
const concLoad = () => typeof CONC !== "undefined" ? Promise.resolve() : loadJs("morph/conc.js");
const lexxLoad = () => typeof LEXX !== "undefined" ? Promise.resolve() : loadJs("morph/lexx.js");
const LEXXT = {};                                        // our entries in the target languages
const lexxtLoad = t => (t === "en" || LEXXT[t]) ? Promise.resolve() : loadJs(`morph/lexx_${t}.js`);
const refLink = r => { const m = r.match(/^(.+?) (\d+):(\d+)$/); return m ? `<a onclick="hidePop();location.hash='#${m[1].replace(/ /g, "_")}/${m[2]}/${m[3]}'">${r}</a>` : esc(r); };
function oursHtml(tag){                                  // our own entry, written by the model from the concordance
  const base = typeof LEXX !== "undefined" ? LEXX[tag] : null; if (!base) return "";
  const tr = (LEXXT[tl] || {})[tag];                     // shown in the reading language when that translation exists
  const e = tr ? {...base, ...tr} : base;
  let h = `<div class="ours"><h5>This project's entry <span style="text-transform:none;font-weight:400">· written by the model from ${base.count} occurrence${base.count === 1 ? "" : "s"}${tr ? " · " + esc(TARGETS[tl].native) : ""}</span></h5>`;
  for (const s of e.senses || []) h += `<div class="sense"><b>${esc(s.sense)}</b> — ${esc(s.definition)} ${(s.refs || []).map(refLink).join(" ")}</div>`;
  if (e.usage) h += `<div class="usage">${esc(e.usage)}</div>`;
  for (const i of e.idioms || []) h += `<div class="idiom"><span class="orig">${esc(i.phrase)}</span> — ${esc(i.meaning)} ${(i.refs || []).map(refLink).join(" ")}</div>`;
  if ((e.near || []).length) h += `<div class="near">compare ${e.near.map(n => `<span class="orig">${esc(n.word)}</span> (${esc(n.difference)})`).join("; ")}</div>`;
  if (e.note) h += `<div class="cav">${esc(e.note)}</div>`;
  return h + `</div>`;
}
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
  await morphLoad(book); await lexLoad(); await Promise.all([lexxLoad().catch(() => {}), lexxtLoad(tl).catch(() => {}), synLoad(book).catch(() => {}), domLoad().catch(() => {})]);
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
    html += synHtml(book, ch, v, +i);
    html += `<div>gloss: <b>${esc(d[2])}</b>${greek && d[3] && d[3] !== d[2] ? ` · <span class="tl">${esc(d[3])}</span>` : ""}</div>`;
    const extra = (d[0].match(TAGRE) || []).filter(t => t !== root && LEX[t]);
    if (extra.length) html += `<div class="pre">with: ${extra.map(t => `${esc(LEX[t][0])} <i>${esc(LEX[t][3])}</i>`).join(", ")}</div>`;
    if (e && e[4]) html += `<div class="meaning">${esc(e[4])}</div>`;
    html += oursHtml(root);
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
    html += `<a class="${v==='all'?'on':''} ${(avail.length + (lxx?1:0))>1?'':'off'}" onclick="setView('all')">Compare</a><a class="${v==='harm'?'on':''}" onclick="setView('harm')" title="this chapter beside its parallels elsewhere">parallels</a><a class="${v==='map'?'on':''}" onclick="setView('map')" title="the places this chapter mentions, on a map">places</a><a class="${v==='chron'?'on':''}" onclick="setView('chron')" title="the chronological statements in this chapter, and the dated anchors">chronology</a><a class="tool ${inter?'on':''}" onclick="toggleInter()" title="gloss and parsing under every Hebrew / Greek word">interlinear</a><a class="tool" onclick="gsOpen()" title="find words by grammatical form">grammar search</a></div>`;
  }
  main.className = ((v === "par" || v === "all" || v === "hl" || v === "harm" || v === "map" || v === "chron") ? "wide" : "") + (inter && src && (v === "orig" || v === "par" || v === "all" || v === "hl") ? " inter" : "");
  if (src && !MORPH[disp(book)]) morphLoad(book).then(() => { if (location.hash.slice(1).split("/").slice(0, 2).join("/") === `${book}/${ch}`) route(); }).catch(() => {});
  main.setAttribute("lang", (v === "orig" || v === "lxx" || v === "hl") ? "" : (shown || "en"));
  main.setAttribute("dir", (v === "tr" && shown) ? tdir(shown) : "ltr");
  if (!tr) html += `<p class="empty" style="margin:0 0 1.2rem">Not translated yet${src ? ` — showing the ${v === "lxx" ? "Septuagint" : L.name}.` : "."}</p>`;
  if (v === "harm") { renderHarmony(book, ch, html, shown); return; }
  if (v === "map") { renderMap(book, ch, html); return; }
  if (v === "chron") { renderChron(book, ch, html); return; }
  if (!tr && v !== "orig" && v !== "lxx" && v !== "hl" && v !== "all") { main.innerHTML = html; return; }
  const nums = Object.keys(v === "tr" ? trs[shown].verses : src).filter(k => !k.startsWith("_")).map(Number).sort((a,b)=>a-b);
  if (v === "orig") {
    for (const n of nums)
      html += `<p class="ov ${ocls}" dir="${rtl?'rtl':'ltr'}" id="v-${book}-${ch}-${n}">${vnum(book,ch,n)}${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</p>`;
  } else if (v === "lxx") {
    for (const n of nums)
      html += `<p class="ov orig greek" id="v-${book}-${ch}-${n}">${vnum(book,ch,n)}${lxx[n] ? esc(lxx[n]) : "<i style='color:var(--muted)'>— no aligned verse</i>"}</p>`;
  } else if (v === "hl") {                                   // Hebrew and Septuagint side by side
    html += `<div class="par">`;
    for (const n of nums)
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}">${vnum(book,ch,n)}${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</div>
        <div class="o orig greek" id="v-${book}-${ch}-${n}">${vnum(book,ch,n)}${lxx[n] ? esc(lxx[n]) : "<i style='color:var(--muted)'>— no aligned verse</i>"}</div>`;
    html += `</div>`;
  } else if (v === "par") {
    html += `<div class="par">`;
    for (const n of nums) {
      const e = trs[shown].verses[n];
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}">${vnum(book,ch,n)}${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</div>
        <div class="e" lang="${shown}" dir="${tdir(shown)}" id="v-${book}-${ch}-${n}">${vnum(book,ch,n)}${e ? flat(e) : "<i style='color:var(--muted)'>—</i>"}</div>`;
    }
    html += `</div>`;
  } else if (v === "all") {
    for (const n of nums) {
      html += `<div class="cmp" id="v-${book}-${ch}-${n}"><div class="row"><span class="lab">${L.name} ${vnum(book,ch,n)}</span><span class="txt ${ocls}" dir="${rtl?'rtl':'ltr'}">${vtag(src,n)}${wrapSrc(src[n], book, ch, n)}</span></div>`;
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
        html += `<div class="poetry" id="${vid}">${vnum(book,ch,n)}${ruby(esc(t)).replace(/\n\n/g,"\n").trimEnd()}</div>`;
      } else {
        para.push(`<span id="${vid}">${vnum(book,ch,n)}${ruby(esc(t))}</span>`);
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
