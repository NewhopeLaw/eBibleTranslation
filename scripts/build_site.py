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
<!-- viewport-fit=cover so the bars can sit under a phone's rounded corners and
     gesture bar; no maximum-scale, because pinching is how a reader who cannot
     see the text at its set size makes it bigger. -->
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#faf8f4">
<meta name="color-scheme" content="light dark">
<title>eBible Translation</title>
<style>
/* Skins. Every colour in the page comes from the tokens below, so choosing a
   skin is setting data-theme on <html> and nothing else — no reload, no second
   stylesheet. --border is the hairline between verses and cards, which carries
   no meaning; --edge is the outline of a control, which a reader has to be able
   to see, so it is held at 3:1 against the paper where --border is not. */
:root {
  --bg:#faf8f4; --fg:#22201c; --muted:#635c52; --accent:#654aa8; --on-accent:#ffffff;
  --card:#ffffff; --border:#d7cfc2; --edge:#8a8176; --hl:#f6e7a6; --soft:#f0ece4;
  --err:#ad2317; --warn:#7d5000; --scrim:rgba(28,22,14,.5); --shadow:rgba(44,34,18,.26);
  --fs:20px; --lh:1.72; --barH:56px;
  /* The labels, buttons and trays around the text were set in 10-14 px, which
     is small print on a phone. Every one of them is written as its old size
     times --ui, so the whole of the chrome grows together: 1.2 by default, and
     further as the reader turns the text itself up (see applyType). */
  --ui:1.2;
}
/* With no skin chosen the phone decides, which is what a reader expects the
   first time the page opens. A chosen skin sets data-theme and wins here. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --bg:#181614; --fg:#eae6df; --muted:#a8a094; --accent:#bda5f2; --on-accent:#1c1230;
    --card:#221f1c; --border:#413a32; --edge:#847b6f; --hl:#4f4320; --soft:#2b2723;
    --err:#ff9d92; --warn:#e4b75f; --scrim:rgba(0,0,0,.62); --shadow:rgba(0,0,0,.6);
  }
}
:root[data-theme="light"] {
  --bg:#faf8f4; --fg:#22201c; --muted:#635c52; --accent:#654aa8; --on-accent:#ffffff;
  --card:#ffffff; --border:#d7cfc2; --edge:#8a8176; --hl:#f6e7a6; --soft:#f0ece4;
  --err:#ad2317; --warn:#7d5000; --scrim:rgba(28,22,14,.5); --shadow:rgba(44,34,18,.26);
}
:root[data-theme="sepia"] {
  --bg:#f3ead6; --fg:#33291b; --muted:#5f5340; --accent:#7a3d0e; --on-accent:#fff7e8;
  --card:#fbf4e4; --border:#d4c5a4; --edge:#8a7b5e; --hl:#e9d692; --soft:#eae0c8;
  --err:#98200f; --warn:#6d4600; --scrim:rgba(48,36,18,.5); --shadow:rgba(70,54,24,.28);
}
:root[data-theme="dark"] {
  --bg:#181614; --fg:#eae6df; --muted:#a8a094; --accent:#bda5f2; --on-accent:#1c1230;
  --card:#221f1c; --border:#413a32; --edge:#847b6f; --hl:#4f4320; --soft:#2b2723;
  --err:#ff9d92; --warn:#e4b75f; --scrim:rgba(0,0,0,.62); --shadow:rgba(0,0,0,.6);
}
:root[data-theme="black"] {
  --bg:#000000; --fg:#eaeaea; --muted:#a6a6a6; --accent:#c3a8ff; --on-accent:#150a28;
  --card:#101010; --border:#3a3a3a; --edge:#767676; --hl:#4c4118; --soft:#1a1a1a;
  --err:#ff9a90; --warn:#e2b75e; --scrim:rgba(0,0,0,.75); --shadow:rgba(0,0,0,.8);
}
:root[data-theme="contrast"] {
  --bg:#ffffff; --fg:#000000; --muted:#2b2b2b; --accent:#3d1785; --on-accent:#ffffff;
  --card:#ffffff; --border:#000000; --edge:#000000; --hl:#ffe74a; --soft:#ededed;
  --err:#9b0000; --warn:#5d3600; --scrim:rgba(0,0,0,.6); --shadow:rgba(0,0,0,.4);
}
* { box-sizing:border-box; margin:0; }
html { scroll-behavior:smooth; }
body { background:var(--bg); color:var(--fg);
  font:var(--fs)/var(--lh) Georgia, "Times New Roman", serif;
  -webkit-text-size-adjust:100%; }
/* A reader who has asked the system for less movement gets none of ours: the
   trays appear where they would have slid to, and a verse jump does not glide. */
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior:auto; }
  *, *::before, *::after { animation-duration:.001ms !important; animation-iteration-count:1 !important;
    transition-duration:.001ms !important; }
}
:focus-visible { outline:3px solid var(--accent); outline-offset:2px; border-radius:5px; }
/* The top bar is sticky rather than fixed so that hiding it shifts nothing
   underneath it; the same trick carries the bottom bar down out of the way. */
header { position:sticky; top:0; background:var(--bg); z-index:30;
  border-bottom:1px solid var(--border); padding:.45rem .6rem;
  padding-top:calc(.45rem + env(safe-area-inset-top));
  display:flex; gap:.4rem; flex-wrap:wrap; align-items:center;
  transition:transform .22s cubic-bezier(.2,0,0,1); }
html.chrome-off header { transform:translateY(-115%); }
html.chrome-off #tabbar { transform:translateY(115%); }
header .brand { font-size:calc(15px * var(--ui)); font-style:italic; color:var(--muted);
  margin-right:auto; white-space:nowrap; }
input, select, button.fs { font:calc(14px * var(--ui)) system-ui, sans-serif; padding:.45rem .6rem;
  min-height:44px; border:1px solid var(--edge); border-radius:10px;
  background:var(--card); color:var(--fg); }
input:focus { outline:3px solid var(--accent); outline-offset:1px; }
#ref { width:9rem; } #q { width:13rem; }
.goto { display:flex; align-items:center; gap:.4rem; font:calc(12px * var(--ui)) system-ui, sans-serif; color:var(--muted); white-space:nowrap; }
button.fs { cursor:pointer; min-width:2.6rem; }
button.fs:hover:not(:disabled) { border-color:var(--accent); }
button.fs:disabled { opacity:.35; cursor:default; }
select#bookSel { max-width:11rem; display:none; }
/* Icon buttons: 44px of tappable area whatever the glyph inside measures. */
.ib { display:inline-flex; align-items:center; justify-content:center; flex:none;
  min-width:44px; min-height:44px; padding:.35rem; border:1px solid transparent;
  border-radius:12px; background:none; color:var(--fg); cursor:pointer; }
.ib:hover:not(:disabled) { background:var(--soft); }
.ib:disabled { opacity:.32; cursor:default; }
.ib svg, #tabbar svg { fill:none; stroke:currentColor; stroke-width:1.85;
  stroke-linecap:round; stroke-linejoin:round; }
.ib svg { width:22px; height:22px; }
/* The current reference, as a button: on a phone it is both the title and the
   way into the navigation tray, which saves a row of chrome. */
#title { display:none; flex:1 1 auto; min-width:0; min-height:44px; text-align:left;
  background:none; border:1px solid transparent; border-radius:12px; color:var(--fg);
  cursor:pointer; padding:.15rem .5rem; font:600 calc(16px * var(--ui))/1.2 system-ui,sans-serif; }
#title:hover { background:var(--soft); }
#title .main { display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#title .main::after { content:" \25BE"; color:var(--muted); font-size:.85em; }
#title .sub { display:block; font:400 calc(12px * var(--ui))/1.35 system-ui,sans-serif; color:var(--muted);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
main { max-width:42rem; margin:0 auto; padding:1.4rem 1.2rem 5rem; }
main.wide { max-width:66rem; }
.layout { display:flex; }
/* ---------- bottom bar: the actions a thumb can reach without moving ---------- */
#tabbar { display:none; position:fixed; left:0; right:0; bottom:0; z-index:30;
  background:var(--card); border-top:1px solid var(--border);
  padding-bottom:env(safe-area-inset-bottom);
  transition:transform .22s cubic-bezier(.2,0,0,1); }
#tabbar .row { display:flex; }
#tabbar button { flex:1 1 0; min-width:0; min-height:56px; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:.1rem; padding:.3rem .15rem; overflow:hidden;
  background:none; border:0; color:var(--muted); cursor:pointer;
  font:500 calc(11px * var(--ui)) system-ui,sans-serif; }
#tabbar button .ic { display:flex; align-items:center; justify-content:center; flex:none;
  width:100%; max-width:56px; height:28px; border-radius:14px; }
#tabbar button .lb { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#tabbar button svg { width:23px; height:23px; }
#tabbar button[aria-expanded="true"] { color:var(--accent); font-weight:700; }
#tabbar button[aria-expanded="true"] .ic { background:var(--hl); color:var(--fg); }
/* ---------- trays ---------- */
dialog.sheet { border:0; padding:0; margin:0; width:100%; max-width:none;
  position:fixed; inset:auto 0 0 0; max-height:88vh; max-height:88dvh;
  background:var(--card); color:var(--fg); border-radius:22px 22px 0 0;
  box-shadow:0 -6px 34px var(--shadow); display:none; flex-direction:column; overflow:hidden; }
dialog.sheet[open] { display:flex; animation:sheetin .24s cubic-bezier(.2,0,0,1); }
dialog.sheet::backdrop { background:var(--scrim); }
@keyframes sheetin { from { transform:translateY(100%); } }
.sheet .grab { padding:.55rem 0 .15rem; display:flex; justify-content:center;
  touch-action:none; cursor:grab; flex:none; }
.sheet .grab i { width:36px; height:4px; border-radius:2px; background:var(--edge); display:block; }
.sheet .sh { display:flex; align-items:center; gap:.4rem; padding:.1rem .6rem .4rem 1rem;
  flex:none; touch-action:none; }
.sheet .sh .st { flex:1; min-width:0; font:600 calc(17px * var(--ui)) system-ui,sans-serif;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.sheet .bd { overflow-y:auto; overscroll-behavior:contain; flex:1 1 auto;
  padding:0 1rem calc(1.4rem + env(safe-area-inset-bottom)); }
.shead { margin:1.1rem 0 .35rem; font:600 calc(11px * var(--ui)) system-ui,sans-serif; text-transform:uppercase;
  letter-spacing:.07em; color:var(--muted); }
.rowlist { display:flex; flex-direction:column; }
.rowlist a, .rowlist button { display:flex; width:100%; align-items:center; gap:.6rem;
  min-height:48px; padding:.5rem .7rem; border:0; border-radius:12px; background:none;
  color:var(--fg); font:calc(15px * var(--ui)) system-ui,sans-serif; text-align:left; cursor:pointer;
  text-decoration:none; }
.rowlist a:hover, .rowlist button:hover { background:var(--soft); }
.rowlist .on { background:var(--hl); font-weight:700; }
.rowlist .nm { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rowlist .ct { flex:0 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; text-align:end; font:calc(12px * var(--ui)) system-ui,sans-serif; color:var(--muted); }
.rowlist .tk { flex:none; font-weight:700; color:var(--accent); }
.rowlist .missing { color:var(--muted); opacity:.5; pointer-events:none; }
.chgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(48px,1fr)); gap:.4rem; }
.chgrid a { display:flex; align-items:center; justify-content:center; min-height:48px;
  border:1px solid var(--edge); border-radius:12px; text-decoration:none; color:var(--fg);
  font:calc(15px * var(--ui)) system-ui,sans-serif; }
.chgrid a.on { background:var(--accent); color:var(--on-accent); border-color:var(--accent); font-weight:700; }
.chgrid a.untr { color:var(--muted); border-style:dashed; }
.seg { display:flex; gap:.3rem; padding:.25rem; background:var(--soft); border-radius:14px; }
.seg button { flex:1 1 0; min-width:0; min-height:44px; border:1px solid transparent;
  border-radius:11px; background:none; color:var(--fg); cursor:pointer;
  font:500 calc(14px * var(--ui)) system-ui,sans-serif; }
.seg button[aria-pressed="true"] { background:var(--card); border-color:var(--edge); font-weight:700; }
.seg button:disabled { opacity:.4; cursor:default; }
.seg .val { flex:0 0 5.5rem; display:flex; align-items:center; justify-content:center;
  font:600 calc(14px * var(--ui)) system-ui,sans-serif; font-variant-numeric:tabular-nums; }
.skins { display:grid; grid-template-columns:repeat(auto-fill,minmax(9rem,1fr)); gap:.5rem; }
.skins button { display:flex; align-items:center; gap:.55rem; min-height:52px; padding:.5rem .6rem;
  border:1px solid var(--edge); border-radius:14px; background:var(--card); color:var(--fg);
  font:calc(14px * var(--ui)) system-ui,sans-serif; cursor:pointer; text-align:left; }
.skins button[aria-pressed="true"] { border:2px solid var(--accent); font-weight:700; padding:calc(.5rem - 1px) calc(.6rem - 1px); }
.skins .sw { width:26px; height:26px; border-radius:50%; flex:none; border:1px solid var(--edge); }
.skins .tick { margin-left:auto; font-weight:700; color:var(--accent); }
.tools { display:grid; grid-template-columns:repeat(auto-fill,minmax(9.5rem,1fr)); gap:.5rem; }
.tools button { min-height:64px; display:flex; flex-direction:column; align-items:flex-start;
  justify-content:center; gap:.1rem; padding:.6rem .7rem; border:1px solid var(--edge);
  border-radius:14px; background:var(--card); color:var(--fg); cursor:pointer;
  font:600 calc(14px * var(--ui)) system-ui,sans-serif; text-align:left; }
.tools button small { font:400 calc(11.5px * var(--ui))/1.3 system-ui,sans-serif; color:var(--muted); }
.tools button[aria-pressed="true"] { border:2px solid var(--accent); background:var(--hl);
  padding:calc(.6rem - 1px) calc(.7rem - 1px); }
.tools button:disabled { opacity:.45; cursor:default; }
.tools button:hover:not(:disabled) { background:var(--soft); }
.sheet .hint { font:calc(12.5px * var(--ui))/1.5 system-ui,sans-serif; color:var(--muted); margin:.4rem 0 0; }
.sheet .primary { display:flex; width:100%; align-items:center; justify-content:center;
  min-height:52px; border:1px solid var(--accent); border-radius:14px; margin:.6rem 0 .2rem;
  background:var(--accent); color:var(--on-accent); cursor:pointer; font:700 calc(15px * var(--ui)) system-ui,sans-serif; }
/* ---------- the magnifier's way back, and a place to say a file did not load ---------- */
#zoomchip, #toast { position:fixed; left:50%; transform:translateX(-50%); z-index:36;
  background:var(--card); color:var(--fg); border:1px solid var(--edge);
  box-shadow:0 6px 22px var(--shadow); font:calc(13px * var(--ui))/1.45 system-ui,sans-serif; }
#zoomchip { bottom:calc(var(--chipUp,14px) + env(safe-area-inset-bottom));
  display:flex; align-items:center; gap:.5rem; padding:.35rem .4rem .35rem .9rem;
  border-radius:999px; white-space:nowrap; }
#zoomchip button { min-height:40px; padding:0 .95rem; border:0; border-radius:999px;
  background:var(--accent); color:var(--on-accent); cursor:pointer; white-space:nowrap;
  font:600 calc(13px * var(--ui)) system-ui,sans-serif; }
#toast { bottom:calc(var(--chipUp,14px) + env(safe-area-inset-bottom)); max-width:min(24rem,92vw);
  padding:.7rem 1rem; border-radius:14px; }
#zoomchip[hidden], #toast[hidden] { display:none; }
footer#credits { border-top:1px solid var(--border); margin-top:2rem; padding:1.2rem 1.2rem 2rem; color:var(--muted);
  font:calc(12px * var(--ui))/1.55 system-ui, sans-serif; }
footer#credits h2 { font:600 calc(12px * var(--ui)) system-ui, sans-serif; text-transform:uppercase; letter-spacing:.06em; margin:0 0 .5rem; }
footer#credits p { margin:0 0 .45rem; max-width:66rem; }
/* The attributions carry bare URLs, which have no break in them and push a
   narrow screen sideways unless they are allowed to break anywhere. */
footer#credits a { color:inherit; } footer#credits, code { overflow-wrap:anywhere; }
header .sources { margin-left:auto; font:calc(12px * var(--ui)) system-ui, sans-serif; color:var(--muted); cursor:pointer; background:none; border:0; text-decoration:underline; }
/* --barH is measured from the header, which wraps to two rows at some widths;
   the sidebar used to assume it never did and lost its last book behind it. */
nav#books { width:210px; flex:none; padding:1rem .6rem; font:calc(14px * var(--ui)) system-ui,sans-serif;
  border-right:1px solid var(--border); height:calc(100vh - var(--barH));
  overflow-y:auto; position:sticky; top:var(--barH); }
nav#books a { display:block; padding:.35rem .55rem; color:var(--fg);
  text-decoration:none; border-radius:6px; }
nav#books a:hover { background:var(--card); }
nav#books a.on { background:var(--accent); color:#fff; }
nav#books .t { margin:.7rem 0 .25rem; font-weight:600; color:var(--muted);
  font-size:calc(12px * var(--ui)); text-transform:uppercase; letter-spacing:.06em; }
nav#books a.missing { color:var(--muted); opacity:.4; pointer-events:none; }
nav#books a.untr { color:var(--muted); }
nav#books a .ct { float:right; font-size:calc(11px * var(--ui)); color:var(--muted); margin-top:.15rem; }
nav#books a.on .ct { color:#fff; opacity:.85; }
.chnav { font:calc(14px * var(--ui)) system-ui,sans-serif; margin:.9rem 0 1.6rem;
  display:flex; flex-wrap:wrap; gap:.3rem; }
.chnav a { display:inline-flex; align-items:center; justify-content:center;
  min-width:2.4rem; min-height:40px; padding:.22rem .6rem; border:1px solid var(--edge);
  border-radius:9px; text-decoration:none; color:var(--fg); }
.chnav a.on { background:var(--accent); color:var(--on-accent); border-color:var(--accent); font-weight:700; }
.chnav a.untr { color:var(--muted); border-style:dashed; }
h2 { font-size:1.65em; font-weight:normal; margin:.3rem 0 .4rem; }
h2 .lang { font:calc(13px * var(--ui)) system-ui,sans-serif; color:var(--muted); margin-left:.6rem; vertical-align:middle; }
sup.v { color:var(--accent); font:600 .58em system-ui,sans-serif;
  margin:0 .18em 0 .05em; user-select:none; vertical-align:.55em; }
p.vv { margin:0 0 1.05em; text-align:justify; hyphens:auto; }
.poetry { margin:0 0 1.05em 1.3em; text-indent:-1.3em; white-space:pre-wrap; }
.notes { margin-top:2.4rem; padding:1rem 1.2rem; background:var(--card);
  border:1px solid var(--border); border-radius:10px;
  font:calc(14px * var(--ui))/1.6 system-ui,sans-serif; color:var(--muted); }
.notes b { color:var(--fg); }
/* Moving to the next chapter costs no reading space: it waits at the end of
   the one being read, where a reader arrives anyway, and in the tray. */
.pn { display:flex; justify-content:space-between; gap:.6rem; margin-top:2.6rem;
  font:calc(15px * var(--ui)) system-ui,sans-serif; }
.pn a { display:inline-flex; align-items:center; min-height:48px; color:var(--accent);
  text-decoration:none; padding:.5rem .9rem; border:1px solid var(--edge); border-radius:12px; }
.pn a:hover { border-color:var(--accent); background:var(--soft); }
.pn .off { visibility:hidden; }
#results { font:calc(15px * var(--ui))/1.5 system-ui,sans-serif; }
#results .hit { background:var(--card); border:1px solid var(--border);
  border-radius:10px; padding:.7rem .9rem; margin:.6rem 0; cursor:pointer; }
#results .hit:hover { border-color:var(--accent); }
#results .ref { color:var(--accent); font-weight:600; font-size:calc(13px * var(--ui)); }
mark { background:var(--hl); color:inherit; border-radius:3px; padding:0 .1em; }
.flash { animation:flash 2.5s; }
@keyframes flash { 0%,55% { background:var(--hl); } 100% { background:transparent; } }
.empty { color:var(--muted); font:calc(15px * var(--ui)) system-ui,sans-serif; margin-top:2rem; }
.tabs { display:flex; flex-wrap:wrap; gap:.3rem; font:calc(14px * var(--ui)) system-ui,sans-serif; margin:-.8rem 0 1.3rem; align-items:center; }
.tabs a { display:inline-flex; align-items:center; min-height:40px; padding:.25rem .8rem;
  border:1px solid var(--edge); border-radius:999px;
  cursor:pointer; color:var(--fg); user-select:none; }
.tabs a:hover { border-color:var(--accent); background:var(--soft); }
.tabs a.on { background:var(--accent); color:var(--on-accent); border-color:var(--accent); font-weight:600; }
.tabs a.off { opacity:.45; cursor:default; pointer-events:none; }
.tabs .sep { width:1px; height:1.2rem; background:var(--border); margin:0 .3rem; }
.orig { font-family:"SBL Hebrew","Ezra SIL","Taamey Frank CLM","Times New Roman",serif; line-height:calc(var(--lh) * 1.134); }
.orig.greek { font-family:"Gentium Plus","SBL Greek","Palatino Linotype","Times New Roman",serif; }
.orig[dir=rtl] { text-align:right; }
.orig sup.v { vertical-align:.7em; }
.w { cursor:pointer; border-radius:3px; } .w:hover { background:var(--soft); } .w.sel { background:var(--hl); }
main.inter .orig .w { display:inline-block; text-align:center; margin:0 .2em .45em 0; vertical-align:top; line-height:1.4; }
main.inter .orig .w::after { content:attr(data-g); display:block; font:calc(11px * var(--ui))/1.25 system-ui,sans-serif; color:var(--muted); direction:ltr; max-width:9em; white-space:normal; margin-top:.1em; }
main.inter .orig .w[data-m]::before { content:attr(data-m); display:block; font:calc(9.5px * var(--ui))/1.2 ui-monospace,Consolas,monospace; color:var(--accent); direction:ltr; }
#wpop { position:fixed; z-index:40; max-width:26rem; background:var(--card); color:var(--fg); border:1px solid var(--border); border-radius:10px;
  box-shadow:0 10px 30px rgba(0,0,0,.25); padding:.7rem .9rem; font:calc(13px * var(--ui))/1.45 system-ui,sans-serif; white-space:normal; direction:ltr; text-align:left; }
#wpop .hw { font-size:1.35em; } #wpop .hw .orig { font-size:1em; } #wpop .tl { color:var(--muted); margin-left:.4em; } #wpop .pos { color:var(--muted); font-size:calc(11px * var(--ui)); margin-left:.4em; }
#wpop .parse { margin:.35rem 0; } #wpop .parse code { font:calc(11px * var(--ui)) ui-monospace,Consolas,monospace; color:var(--accent); margin-left:.4em; }
#wpop .meaning { color:var(--muted); font-size:calc(12px * var(--ui)); margin-top:.35rem; max-height:9em; overflow:auto; }
#wpop .acts { margin-top:.5rem; display:flex; flex-wrap:wrap; gap:.2rem 1rem; }
#wpop .acts a { display:inline-flex; align-items:center; min-height:44px; cursor:pointer; color:var(--accent); text-decoration:underline; }
#wpop .pre { color:var(--muted); font-size:calc(12px * var(--ui)); }
#wpop .syn { margin:.35rem 0; font-size:calc(12px * var(--ui)); } #wpop .syn b { color:var(--fg); font-weight:600; }
#wpop .syn a { color:var(--accent); cursor:pointer; } #wpop .dom { font-size:calc(12px * var(--ui)); color:var(--muted); margin-top:.25rem; } #wpop .dom a { color:var(--accent); cursor:pointer; }
#wpop .dom .orig { color:var(--fg); } .w.ante { outline:2px solid var(--accent); border-radius:3px; }
#wpop .ours { border-top:1px solid var(--border); margin-top:.55rem; padding-top:.5rem; }
#wpop .ours h5 { font:600 calc(10px * var(--ui)) system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:0 0 .3rem; }
#wpop .sense { margin:0 0 .3rem; } #wpop .sense b { font-weight:600; } #wpop .sense i { color:var(--muted); font-style:normal; font-size:calc(11px * var(--ui)); }
#wpop .sense a, #wpop .idiom a { color:var(--accent); cursor:pointer; margin-left:.3em; }
#wpop .idiom, #wpop .near, #wpop .usage, #wpop .cav { font-size:calc(12px * var(--ui)); color:var(--muted); margin-top:.3rem; }
.tabs a.tool { border-style:dashed; }
.tabs i.sep { width:1px; height:1.1rem; background:var(--border); margin:0 .35rem; align-self:center; }
.gs { display:grid; grid-template-columns:repeat(auto-fill,minmax(11rem,1fr)); gap:.5rem .8rem; margin:.6rem 0 1rem; font:calc(13px * var(--ui)) system-ui,sans-serif; }
.gs label { display:flex; flex-direction:column; gap:.2rem; color:var(--muted); font-size:calc(11px * var(--ui)); text-transform:uppercase; letter-spacing:.05em; }
.gs select, .gs input { font:calc(14px * var(--ui)) system-ui,sans-serif; padding:.35rem .5rem; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--fg); }
.gs button { grid-column:1 / -1; justify-self:start; font:calc(14px * var(--ui)) system-ui,sans-serif; padding:.45rem 1rem; border:1px solid var(--accent); border-radius:8px; background:var(--accent); color:#fff; cursor:pointer; }
.hit .orig { display:block; margin-top:.15rem; } .hit mark { background:var(--hl); color:inherit; border-radius:3px; }
/* The verse number is the button that takes the verse: one tap holds it, a
   second lets it go, and as many as wanted can be held at once. Held, it is
   pressed in - filled and set down into the page - so a glance down the
   margin says which verses the bar at the foot of the screen is talking
   about, without reading the reference. */
sup.v { cursor:pointer; border-radius:4px; padding:0 .14em; border:1px solid transparent;
  transition:background .12s, color .12s, box-shadow .12s; }
sup.v:hover { background:var(--soft); }
sup.v:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
sup.v[aria-pressed="true"], sup.v[aria-pressed="true"]:hover {
  background:var(--accent); color:var(--on-accent); border-color:var(--accent);
  box-shadow:inset 0 1.5px 2.5px rgba(0,0,0,.45); }
#vpop { position:fixed; z-index:40; width:min(30rem,92vw); max-height:70vh; overflow:auto; background:var(--card); color:var(--fg);
  border:1px solid var(--border); border-radius:10px; box-shadow:0 10px 30px rgba(0,0,0,.25); padding:.7rem .9rem;
  font:calc(13px * var(--ui))/1.5 system-ui,sans-serif; white-space:normal; direction:ltr; text-align:left; }
#vpop h4 { font:600 calc(11px * var(--ui)) system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:.6rem 0 .3rem; }
#vpop h4:first-child { margin-top:0; }
#vpop .r { padding:.25rem .4rem; border-radius:6px; cursor:pointer; display:grid; grid-template-columns:7.5rem 1fr; gap:.5rem; align-items:baseline; }
#vpop .r:hover { background:var(--soft); } #vpop .r b { font:600 calc(12px * var(--ui)) system-ui,sans-serif; color:var(--accent); }
#vpop .r span { color:var(--muted); overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
#vpop .cls { float:right; cursor:pointer; color:var(--muted); }
.harm { border-bottom:1px solid var(--border); padding:.6rem 0; }
.harm .vs { display:grid; gap:.4rem 1.2rem; align-items:start; }
.harm .vs > div { min-width:0; }
.harm .lab { font:600 calc(11px * var(--ui)) system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.15rem; cursor:pointer; }
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
#map .plab { font:calc(10px * var(--ui)) system-ui,sans-serif; fill:var(--fg); pointer-events:none; paint-order:stroke; stroke:var(--bg); stroke-width:2.5px; }
.mapbar { display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.5rem 0; font:calc(13px * var(--ui)) system-ui,sans-serif; color:var(--muted); }
.mapbar button { font:calc(13px * var(--ui)) system-ui,sans-serif; padding:.25rem .6rem; border:1px solid var(--border); border-radius:7px; background:var(--card); color:var(--fg); cursor:pointer; }
.plist { display:grid; grid-template-columns:repeat(auto-fill,minmax(13rem,1fr)); gap:.2rem .8rem; margin:.6rem 0 1rem; font:calc(13px * var(--ui)) system-ui,sans-serif; }
.plist a { cursor:pointer; padding:.15rem .3rem; border-radius:5px; } .plist a:hover { background:var(--soft); }
.plist a small { color:var(--muted); }
.chron { margin:.8rem 0 1.4rem; font:calc(13px * var(--ui))/1.5 system-ui,sans-serif; }
.chron h3 { font:600 calc(11px * var(--ui)) system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:1.1rem 0 .4rem; }
.chron .row { display:grid; grid-template-columns:7rem 1fr; gap:.6rem; padding:.25rem .4rem; border-radius:6px; align-items:baseline; }
.chron .row:hover { background:var(--soft); } .chron .row b { color:var(--accent); font:600 calc(12px * var(--ui)) system-ui,sans-serif; cursor:pointer; }
.chron .row .q { color:var(--muted); } .chron .num { font-variant-numeric:tabular-nums; color:var(--fg); font-weight:600; }
.chron .anch { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.3rem .4rem; border-bottom:1px solid var(--border); }
.chron .anch .y { font-variant-numeric:tabular-nums; font-weight:600; }
.chron .anch .basis { color:var(--muted); font-size:calc(12px * var(--ui)); }
.chron .note { color:var(--muted); margin:.4rem 0 0; }
.thm { margin:.8rem 0 1.4rem; font:calc(14px * var(--ui))/1.6 system-ui,sans-serif; }
.thm .t { padding:.5rem .6rem; border-bottom:1px solid var(--border); }
.thm .t b { font:600 calc(15px * var(--ui)) system-ui,sans-serif; cursor:pointer; color:var(--fg); }
.thm .t b:hover { color:var(--accent); }
.thm .t .vv { color:var(--accent); font-size:calc(12px * var(--ui)); margin-left:.5rem; cursor:pointer; }
.thm .t .w { color:var(--muted); font-size:calc(13px * var(--ui)); }
.thm .cav { color:var(--muted); font-size:calc(12px * var(--ui)); margin:.5rem 0 1rem; padding:.5rem .7rem; border-left:2px solid var(--border); }
.vocab { display:grid; grid-template-columns:repeat(auto-fill,minmax(12rem,1fr)); gap:.15rem .8rem; margin:.5rem 0 1rem; font-size:calc(13px * var(--ui)); }
.vocab a { cursor:pointer; padding:.1rem .3rem; border-radius:5px; } .vocab a:hover { background:var(--soft); }
.vocab a small { color:var(--muted); }
.arg { margin:.6rem 0 1.2rem; font:calc(14px * var(--ui))/1.65 system-ui,sans-serif; }
.arg .lead { padding:.6rem .8rem; background:var(--card); border:1px solid var(--border); border-radius:10px; }
.arg h3 { font:600 calc(11px * var(--ui)) system-ui,sans-serif; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:1.2rem 0 .35rem; }
.arg .sec { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.25rem .4rem; border-radius:6px; align-items:baseline; }
.arg .sec:hover { background:var(--soft); } .arg .sec b { color:var(--accent); font:600 calc(12px * var(--ui)) system-ui,sans-serif; cursor:pointer; }
.arg .tags { display:flex; flex-wrap:wrap; gap:.3rem; margin-top:.4rem; }
.arg .tags span { font-size:calc(12px * var(--ui)); padding:.1rem .5rem; border:1px solid var(--border); border-radius:999px; color:var(--muted); }
.arg .stage { padding:.3rem .4rem; border-bottom:1px solid var(--border); }
.arg .stage b { font:600 calc(13px * var(--ui)) system-ui,sans-serif; } .arg .stage .r { color:var(--accent); font-size:calc(12px * var(--ui)); margin-left:.4rem; }
.arg .tension { padding:.35rem .5rem; border-left:2px solid var(--warn); margin:.3rem 0; color:var(--fg); }
.arg .tension .r { color:var(--muted); font-size:calc(12px * var(--ui)); }
.arg .derived { color:var(--muted); font-size:calc(12px * var(--ui)); margin:.2rem 0 .8rem; }
#vpop .pl { font-size:calc(12px * var(--ui)); } #vpop .pl a { color:var(--accent); cursor:pointer; margin-right:.6em; }
#vpop .ap { font-size:calc(12px * var(--ui)); padding:.2rem .4rem; }
#vpop .ap .rd { font-size:1.15em; } #vpop .ap .ed { color:var(--muted); }
#vpop .ap .kind { font:600 calc(10px * var(--ui)) system-ui,sans-serif; text-transform:uppercase; letter-spacing:.05em; color:var(--accent); margin-right:.4em; }
.lt { font:600 calc(10px * var(--ui)) system-ui,sans-serif; color:var(--muted); text-transform:uppercase;
  letter-spacing:.05em; margin:0 .3em; vertical-align:.5em; user-select:none; }
p.ov { margin:0 0 .6em; }
.par { display:grid; grid-template-columns:1fr 1fr; gap:0 1.6rem; align-items:start; }
.par > div { padding:.45rem 0; border-bottom:1px solid var(--border); }
.par .e { white-space:pre-wrap; }
.cmp { border-bottom:1px solid var(--border); padding:.6rem 0 .5rem; }
.cmp .row { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.15rem 0; align-items:baseline; }
.cmp .row .lab { font:600 calc(11px * var(--ui)) system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; text-align:right; }
.cmp .row .txt { white-space:pre-wrap; }
/* Each script keeps the leading it needs, but as a multiple of the reader's
   chosen line spacing rather than a fixed number, or the spacing control would
   do nothing at all in Chinese, Thai, Korean or Persian. */
[lang="zh"], [lang="ja"] { font-family:Georgia, "Noto Serif CJK SC", "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", "SimSun", "Songti SC", serif; line-height:calc(var(--lh) * 1.134); }
[lang="th"] { font-family:"Noto Serif Thai", "Leelawadee UI", "Tahoma", sans-serif; line-height:calc(var(--lh) * 1.163); }
[lang="yue"], [lang="nan"], [lang="hak"] { font-family:Georgia, "Noto Serif CJK TC", "Source Han Serif TC", "PMingLiU", "Microsoft JhengHei", "Songti TC", serif; line-height:calc(var(--lh) * 1.134); }
[lang="ja-easy"] { font-family:Georgia, "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", serif; line-height:calc(var(--lh) * 1.337); }
ruby rt { font-size:.55em; color:var(--muted); letter-spacing:0; }
[lang="ko"] { font-family:"Noto Serif KR", "Batang", "Malgun Gothic", "Apple SD Gothic Neo", serif; line-height:calc(var(--lh) * 1.105); }
[lang="fa"] { font-family:"Vazirmatn", "Noto Naskh Arabic", "Tahoma", "Segoe UI", serif; line-height:calc(var(--lh) * 1.221); font-size:1.06em; }
[dir="rtl"] { text-align:right; }
/* ---------- what a phone shows, and what it does not ---------- */
@media (max-width:760px){
  .par { grid-template-columns:1fr; }
  .par .o { border-bottom:0; padding-bottom:.1rem; }
  nav#books { display:none }
  header .brand, header .goto, header .sources, header #bookSel, header #tlSel,
  header #q, header #fsMinus, header #fsPlus, header #toolsBtn, header #gear { display:none }
  #title { display:block }
  #tabbar { display:block }
  main { padding:1.1rem 1rem calc(6rem + env(safe-area-inset-bottom)); }
  /* The bottom bar floats over the page, so the last thing on it needs room
     to be read — the attributions were ending underneath the bar. */
  footer#credits { padding-bottom:calc(5.5rem + env(safe-area-inset-bottom)); }
  /* The chapter grid and the view tabs live in the trays on a phone; on the
     page they were two rows of chrome above every chapter. The heading keeps
     its reference — a reader scrolled halfway down wants to see where they
     are — but drops the languages, which the bar above is already saying. */
  .chnav, .tabs { display:none }
  h2 { font-size:1.35em; }
  main > h2 .lang { display:none }
  /* Justified type on a narrow column opens rivers of white space. */
  p.vv { text-align:start; }
  /* Two-column rows meant for a wide screen stack instead of overflowing. */
  .cmp .row, .chron .row, .chron .anch, .arg .sec, #vpop .r { grid-template-columns:1fr; gap:.1rem; }
  .cmp .row .lab { text-align:start; }
  .harm .vs { grid-template-columns:1fr !important; }
  .harm .vs > div:empty { display:none }
  /* Stacked, every passage already carries its own label, so the row of column
     headings is a list of names above nothing. */
  .harm.hdr { display:none }
  #wpop, #vpop { left:8px !important; right:8px; width:auto; max-width:none; }
}
/* A finger is not a mouse pointer: the verse number stays the size it is set
   in, and gains an invisible margin of target around it. */
@media (pointer:coarse){
  sup.v { position:relative; }
  sup.v::before { content:""; position:absolute; inset:-14px -10px; }
}
/* On a tablet the header wraps to two rows and takes a tenth of the screen
   with it. The strapline goes, the boxes narrow, and the sources link goes
   too — the settings tray behind the gear already has it. */
@media (max-width:1040px){
  header .brand, header .sources { display:none }
  #q { width:10rem } #ref { width:7rem }
}
/* On a wide screen the same tray is a dialog in the middle of the page: it is
   the sheet's content that matters, not the gesture it arrived by. */
@media (min-width:761px){
  dialog.sheet { inset:0; margin:auto; width:min(34rem,92vw); max-height:82vh;
    border-radius:18px; border:1px solid var(--border); }
  dialog.sheet[open] { animation:none; }
  .sheet .grab { display:none }
  .sheet .sh { padding-top:.9rem }
}
/* Basic mode: the page is a book and nothing else. Every study layer is put
   away, popups included, so that a mis-tap in the middle of a verse does
   nothing at all. Advanced mode is one tap away and is remembered. */
:root[data-mode="basic"] .adv { display:none !important; }
:root[data-mode="basic"] main .w { cursor:inherit; }
:root[data-mode="basic"] main .w:hover { background:none; }
/* The two inputs move between the header and a tray as the screen narrows, so
   they are laid out by where they are rather than by a second copy of each. */
#hdrSlot, #hdrSlot > #qWrap { display:contents; }
#qslot #qWrap { display:block; margin:.2rem 0; }
#refslot #gotoWrap { display:flex; flex-direction:column; align-items:stretch;
  gap:.25rem; margin:.2rem 0 .6rem; font-size:calc(11px * var(--ui)); text-transform:uppercase; letter-spacing:.07em; }
#refslot #ref, #qslot #q { width:100%; font-size:calc(16px * var(--ui)); min-height:52px; }
@media (max-width:760px){ #zoomchip, #toast, #vbar { --chipUp:74px; } }
/* The bars slide away while the reader is reading, and with them every way to
   change anything. This stays: bottom right, out of the text, one tap to the
   display tray - the type size, the skin, the voice and the rest. */
#quick { position:fixed; z-index:31; right:calc(.7rem + env(safe-area-inset-right));
  bottom:calc(.9rem + env(safe-area-inset-bottom)); width:52px; height:52px; padding:13px;
  border-radius:999px; border:1px solid var(--border); background:var(--card); color:var(--fg);
  box-shadow:0 6px 20px var(--shadow); cursor:pointer;
  visibility:hidden; opacity:0; transform:translateY(10px); transition:opacity .2s, transform .2s; }
#quick svg { width:100%; height:100%; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; }
/* Only once the bars have gone: while they are there the same tray is one tap
   away on the bar itself, and two gears in a corner is one too many. Hidden by
   visibility rather than opacity, so it cannot be tabbed to while invisible. */
html.chrome-off #quick { visibility:visible; opacity:1; transform:none; }
@media (min-width:761px){ #quick { display:none; } }
.try { font:inherit; color:var(--accent); background:none; border:0; padding:0 .1rem; min-height:0;
  text-decoration:underline; cursor:pointer; }
/* A verse taken hold of, and the bar of what can be done with it. The hold is
   marked with the same wash as a search hit, plus a ring, so it reads as held
   rather than merely highlighted. */
.held { background:var(--hl); border-radius:5px; box-shadow:0 0 0 .18em var(--hl); }
#vbar { position:fixed; left:50%; bottom:calc(var(--chipUp,14px) + env(safe-area-inset-bottom));
  transform:translateX(-50%); z-index:60; display:flex; align-items:center; justify-content:center;
  flex-wrap:wrap; gap:.15rem; padding:.3rem;
  max-width:min(96vw,36rem); background:var(--card); border:1px solid var(--border); border-radius:14px;
  box-shadow:0 8px 28px var(--shadow); }
#vbar .ref { padding:0 .55rem; color:var(--muted); white-space:nowrap; min-width:0;
  overflow:hidden; text-overflow:ellipsis;
  font:600 calc(12px * var(--ui)) system-ui,sans-serif; }
/* On a phone the bar is a band across the foot of the screen rather than a
   pill in the middle of it, and a reference to several verses - the long kind,
   "Psalms 23:1-3, 5" - takes the line above the buttons rather than being
   squeezed in beside them and cut to "Psalms 23:1...". So does a short one
   when the study button is there too and five things will not fit; one verse
   with three buttons stays on the one row. */
@media (max-width:560px){
  #vbar { left:8px; right:8px; transform:none; max-width:none; }
  #vbar button { padding:.4rem .55rem; }
  #vbar.wide .ref { flex:1 0 100%; text-align:center; padding:.15rem .4rem .1rem; }
}
#vbar button { font:calc(13px * var(--ui)) system-ui,sans-serif; min-height:44px; padding:.4rem .7rem;
  border:0; border-radius:10px; background:transparent; color:var(--fg); cursor:pointer; white-space:nowrap; }
#vbar button:hover { background:var(--soft); }
#vbar button.x { color:var(--muted); padding:.4rem .6rem; }
__READALOUD_CSS__
/* readaloud.py is shared with the dashboard, where the menu is used with a
   mouse; here a finger opens it by pressing and holding, and needs the room. */
#ctx .it { min-height:48px; display:flex; flex-direction:column; justify-content:center; }
</style>
<script>
/* The skin, the mode and the type size are put on the page before anything is
   painted: a reader who chose the night skin should not be shown a white page
   first while the rest of the script parses. */
try {
  var _s = localStorage.getItem("skin");
  if (_s && _s !== "auto") document.documentElement.setAttribute("data-theme", _s);
  var _m = localStorage.getItem("mode");
  document.documentElement.setAttribute("data-mode", __READER_ONLY__ ? "basic" :
    _m === "advanced" ? "advanced" : _m === "basic" ? "basic"
      : (localStorage.getItem("view") || localStorage.getItem("tl")) ? "advanced" : "basic");
  var _f = localStorage.getItem("fs");
  if (_f) { document.documentElement.style.setProperty("--fs", _f + "px");
            document.documentElement.style.setProperty("--ui", String(Math.min(1.45, Math.max(1.15, .8 + _f / 50)))); }
  var _l = localStorage.getItem("lh"); if (_l) document.documentElement.style.setProperty("--lh", _l);
} catch (e) {}
</script>
</head>
<body>
<header>
  <button class="ib" id="back" aria-label="Back to what you were looking at" title="Back to what you were looking at (Backspace)" disabled><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>
  <button id="title" aria-haspopup="dialog" aria-expanded="false" aria-controls="navSheet">
    <span class="main" id="titleMain">eBible</span><span class="sub" id="titleSub"></span></button>
  <span class="brand">eBible — from the Hebrew, Aramaic &amp; Greek</span>
  <select id="bookSel" aria-label="Book"></select>
  <select id="tlSel" title="Translation language" aria-label="Translation language"></select>
  <span id="hdrSlot"><label class="goto" id="gotoWrap" title="Type a reference: Genesis 2:7, 1 Sam 3, Ps 23 — the page follows as you type"><span>Go to</span><input id="ref" placeholder="Genesis 2:7"></label><span id="qWrap"><input id="q" placeholder="Search the text…" aria-label="Search the text" type="search"></span></span>
  <button class="fs" id="fsMinus" title="Smaller text" aria-label="Smaller text">A−</button>
  <button class="fs" id="fsPlus" title="Larger text" aria-label="Larger text">A+</button>
  <button class="ib adv" id="toolsBtn" aria-label="Tools and study views" title="Tools and study views" aria-haspopup="dialog" aria-expanded="false" aria-controls="toolsSheet"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h5M13 7h7M4 17h9M17 17h3"/><circle cx="11" cy="7" r="2.2"/><circle cx="15" cy="17" r="2.2"/></svg></button>
  <button class="ib" id="gear" aria-label="Display and reading settings" title="Display and reading settings" aria-haspopup="dialog" aria-expanded="false" aria-controls="setSheet"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6M18.4 18.4l-1.6-1.6M7.2 7.2L5.6 5.6"/></svg></button>
  <button class="sources" id="sources" title="Source texts, licenses and attributions">Sources &amp; licenses</button>
</header>
<div class="layout">
<nav id="books" aria-label="Books of the Bible"></nav>
<main id="main"></main>
</div>
<button id="quick" class="adv-hide" aria-label="Display and reading settings" title="Display and reading settings" aria-haspopup="dialog" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6M18.4 18.4l-1.6-1.6M7.2 7.2L5.6 5.6"/></svg></button>
<nav id="tabbar" aria-label="Reader actions"><div class="row">
  <button id="tbBooks" aria-haspopup="dialog" aria-expanded="false" aria-controls="navSheet"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5h6.5v14H4zM13.5 5.5H20v14h-6.5z"/></svg></span><span class="lb">Books</span></button>
  <button id="tbSearch" aria-haspopup="dialog" aria-expanded="false" aria-controls="searchSheet"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.6"/><path d="M16 16l4.4 4.4"/></svg></span><span class="lb">Search</span></button>
  <button id="tbTools" class="adv" aria-haspopup="dialog" aria-expanded="false" aria-controls="toolsSheet"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h5M13 7h7M4 17h9M17 17h3"/><circle cx="11" cy="7" r="2.2"/><circle cx="15" cy="17" r="2.2"/></svg></span><span class="lb">Tools</span></button>
  <button id="tbDisp" aria-haspopup="dialog" aria-expanded="false" aria-controls="setSheet"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 19l5-14 5 14M5.3 14.4h6.4M21 19v-6.6a2.6 2.6 0 0 0-5 -1M16 19a2.4 2.4 0 0 1 0-4.8h5"/></svg></span><span class="lb">Display</span></button>
</div></nav>
<dialog class="sheet" id="navSheet" aria-labelledby="navSheetT">
  <div class="grab"><i></i></div>
  <div class="sh"><span class="st" id="navSheetT">Go to</span>
    <button class="ib" data-close aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
  <div class="bd" id="navBody"><div id="refslot"></div><div id="navDyn"></div></div>
</dialog>
<dialog class="sheet" id="searchSheet" aria-labelledby="searchSheetT">
  <div class="grab"><i></i></div>
  <div class="sh"><span class="st" id="searchSheetT">Search the text</span>
    <button class="ib" data-close aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
  <div class="bd" id="searchBody"><div id="qslot"></div><div id="searchDyn"></div></div>
</dialog>
<dialog class="sheet" id="toolsSheet" aria-labelledby="toolsSheetT">
  <div class="grab"><i></i></div>
  <div class="sh"><span class="st" id="toolsSheetT">Tools</span>
    <button class="ib" data-close aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
  <div class="bd" id="toolsBody"><div id="toolsDyn"></div></div>
</dialog>
<dialog class="sheet" id="setSheet" aria-labelledby="setSheetT">
  <div class="grab"><i></i></div>
  <div class="sh"><span class="st" id="setSheetT">Display and reading</span>
    <button class="ib" data-close aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
  <div class="bd" id="setBody"><div id="setDyn"></div></div>
</dialog>
<div id="zoomchip" hidden><span id="zoomlvl" role="status"></span><button id="zoomreset" type="button">Reset</button></div>
<div id="toast" hidden role="status"></div>
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
  <p><b>This project's lexeme inventory:</b> grown from the text by the local model — every distinct word form is analysed in context and the dictionary words it
    implies become the inventory, numbered in order of first appearance (<code>scripts/build_lexemes.py</code>). It is independent of Strong's and of any published
    dictionary; the reference tagging above is used only to measure how cleanly our inventory groups the text (<code>logs/lexeme_report.md</code>).</p>
  <p><b>Text notes:</b> which printed editions carry each reading, and the scribal Qere against the written Ketiv, are from the STEPBible data above
    (CC BY 4.0). Editions compared: Nestle-Aland 27 and 28, Tyndale House 2017, SBLGNT, Westcott-Hort 1881, Tregelles, Scrivener's Textus Receptus 1894 and the
    Robinson-Pierpont Byzantine text. This is an apparatus of editions, not of manuscripts: no manuscript is cited, because no openly licensed manuscript apparatus exists for this project to use.</p>
  <p><b>Clause roles, participants and glosses:</b> the <a href="https://github.com/Clear-Bible/macula-greek">MACULA Greek</a> and
    <a href="https://github.com/Clear-Bible/macula-hebrew">MACULA Hebrew</a> linguistic datasets © 2022-2024 Biblica, Inc.,
    <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> — word class, the word a pronoun refers back to, a gloss, and for Greek the role in the clause.
    The semantic-domain fields in those datasets are United Bible Societies material (Louw-Nida for Greek, the Semantic Dictionary of Biblical Hebrew for Hebrew),
    used by permission rather than licensed onward, so this project does not use them. The fields of meaning shown in the word popup are this project's own: the model sorts
    each lexeme by its usage and gloss into a list of fields written for this project (<code>scripts/build_domains.py</code>).</p>
  <p><b>Book arguments and theme trajectories:</b> built by the model from the themes above and nothing else — a book's sections and line of thought from the themes
    of its own chapters, a theme's development from its own passages in canonical order, including the places where those passages pull against each other. These are
    readings, labelled as such in the reader, and they cite the layer they are built on so a reader can disagree at the step where they actually disagree. No published
    theology, commentary or topical Bible is consulted.</p>
  <p><b>Themes:</b> each theme is named in the language of the text — a short Hebrew, Aramaic or Greek phrase built from words that actually stand in its passages —
    with a plain-language gloss beside it, because a reader should see what the text says and what it means at the same time. The model reads each chapter and says what it is about, and those chapter themes are then folded into one list for the whole Bible. Nothing is
    taken from a systematic theology or a topical Bible, and every theme names the verses it came from. Themes are a reading, not a tagged fact, and they are kept
    apart from the data layers for that reason. The vocabulary shown with a theme is evidence about its passages, not a definition of it: one theme runs on many
    unrelated words, and one word serves many themes.</p>
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
/* Every link to a reference goes through here. A theme, an entry or a list of
   hits is drawn over the chapter without changing the address, so a link back
   to the chapter already in the address would otherwise do nothing at all. */
function goto(h){ if (location.hash === h) route(); else location.hash = h; }
function setTl(t){ tl = t; localStorage.setItem("tl", t); $("#tlSel").value = t; if (view === "orig") view = "tr"; route(); }
const tlSel = $("#tlSel");
tlSel.innerHTML = haveTargets.map(t => `<option value="${t}">${TARGETS[t].native}</option>`).join("");
tlSel.value = tl;
tlSel.addEventListener("change", e => setTl(e.target.value));
if (haveTargets.length < 2) tlSel.style.display = "none";

/* ---------- skins: a set of colour tokens on <html>, remembered, no reload ----------
   The swatch beside each name is drawn from that skin's own paper and accent,
   so the list shows what it is offering rather than describing it. */
const SKINS = [["auto", "Match phone", "", ""],
               ["light", "Paper white", "#faf8f4", "#654aa8"],
               ["sepia", "Sepia", "#f3ead6", "#7a3d0e"],
               ["dark", "Dark", "#181614", "#bda5f2"],
               ["black", "Night, true black", "#000000", "#c3a8ff"],
               ["contrast", "High contrast", "#ffffff", "#3d1785"]];
const SKINBAR = {light: "#faf8f4", sepia: "#f3ead6", dark: "#181614", black: "#000000", contrast: "#ffffff"};
const prefersDark = matchMedia("(prefers-color-scheme: dark)");
let skin = localStorage.getItem("skin") || "auto";
if (!SKINS.some(s => s[0] === skin)) skin = "auto";
function applySkin(){
  const r = document.documentElement;
  if (skin === "auto") r.removeAttribute("data-theme"); else r.setAttribute("data-theme", skin);
  const m = document.querySelector('meta[name="theme-color"]');
  if (m) m.content = SKINBAR[skin === "auto" ? (prefersDark.matches ? "dark" : "light") : skin];
  // In the app, the bars around the page are the shell's to paint: tell it at
  // once, or they sit in the old colour until it notices.
  if (m && typeof AndroidApp !== "undefined" && AndroidApp && AndroidApp.theme) {
    try { AndroidApp.theme(m.content); } catch (e) {}
  }
}
function setSkin(s){ skin = s; localStorage.setItem("skin", s); applySkin(); redrawSheet(); }
prefersDark.addEventListener("change", () => { if (skin === "auto") { applySkin(); redrawSheet(); } });
applySkin();

/* ---------- basic or advanced ----------
   Basic mode is the book: a chapter, a language, the size of the type. Advanced
   adds every layer this project has built on top of the text. A reader arriving
   for the first time gets basic; anyone whose browser already remembers a view
   or a language has been using the study tools, so they keep them. */
/* The reader-only build (the Android reader APK) ships the text without the
   study layers in morph/, so advanced mode would open onto empty views: it is
   basic, always, and the switch is not offered. */
const READER_ONLY = __READER_ONLY__;
let mode = localStorage.getItem("mode");
if (mode !== "basic" && mode !== "advanced")
  mode = (localStorage.getItem("view") || localStorage.getItem("tl")) ? "advanced" : "basic";
if (READER_ONLY) mode = "basic";
const adv = () => mode === "advanced";
function applyMode(){ document.documentElement.setAttribute("data-mode", mode); }
function setMode(m){ if (READER_ONLY) m = "basic"; mode = m; localStorage.setItem("mode", m); applyMode(); route(); redrawSheet(); }
applyMode();

/* ---------- text size and line spacing ---------- */
const SPACING = [[1.5, "Tight"], [1.72, "Normal"], [1.95, "Roomy"], [2.2, "Loose"]];
const FS_MIN = 16, FS_MAX = 40;         // 40 px is large print on a phone held at arm's length
let fs = +(localStorage.getItem("fs") || 20);
let lh = +(localStorage.getItem("lh") || 1.72);
function applyType(){
  const s = document.documentElement.style;
  s.setProperty("--fs", fs + "px"); s.setProperty("--lh", String(lh));
  // A reader who needs bigger text needs bigger buttons too, but the bars have
  // to fit a phone: the chrome grows with the text, more slowly, and stops.
  s.setProperty("--ui", String(Math.min(1.45, Math.max(1.15, .8 + fs / 50))));
  $("#fsMinus").disabled = fs <= FS_MIN; $("#fsPlus").disabled = fs >= FS_MAX;
  if (typeof measureBar === "function") measureBar();
}
function fsStep(d){ fs = Math.min(FS_MAX, Math.max(FS_MIN, fs + 2 * d)); localStorage.setItem("fs", fs); applyType(); redrawSheet(); }
function setLh(v){ lh = v; localStorage.setItem("lh", v); applyType(); redrawSheet(); }
applyType();
$("#fsMinus").onclick = () => fsStep(-1);
$("#fsPlus").onclick  = () => fsStep(1);

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
$("#bookSel").addEventListener("change", e => goto(`#${e.target.value}/1`));

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

/* ---------- themes: what the chapters are about, gathered across the canon ---------- */
const themesLoad = () => typeof THEMES !== "undefined" ? Promise.resolve() : loadJs("morph/themes.js");
const theolLoad = () => typeof BOOKARG !== "undefined" ? Promise.resolve() : loadJs("morph/theology.js");
const DERIVED = "Built from the layer below it and citing what it is built on: a reading, not a tagged fact. Nothing here is taken from a published theology.";
function bookArgHtml(book){
  const a = typeof BOOKARG !== "undefined" ? BOOKARG[disp(book)] : null; if (!a) return "";
  const [sections, argument, concerns] = a;
  let h = `<div class="arg"><h3>What ${esc(disp(book))} is doing</h3><div class="derived">${esc(DERIVED)}</div>`;
  if (argument) h += `<div class="lead">${esc(argument)}</div>`;
  if ((concerns || []).length) h += `<div class="tags">${concerns.map(c => `<span>${esc(c)}</span>`).join("")}</div>`;
  if ((sections || []).length) { h += `<h3>Its sections</h3>`;
    h += sections.map(sc => `<div class="sec"><b onclick="goto('#${book}/${(String(sc.chapters).match(/\d+/) || [1])[0]}')">${esc(sc.chapters)}</b><span><b style="font-weight:600">${esc(sc.section)}</b> — ${esc(sc.what)}</span></div>`).join(""); }
  return h + `</div>`;
}
function trajHtml(id){
  const t = typeof TRAJ !== "undefined" ? TRAJ[id] : null; if (!t) return "";
  const [beginning, stages, culmination, tensions, unresolved] = t;
  let h = `<div class="arg"><h3>How it develops across the canon</h3><div class="derived">${esc(DERIVED)}</div>`;
  if (beginning) h += `<div class="lead">${esc(beginning)}</div>`;
  if ((stages || []).length) h += `<h3>Stages</h3>` + stages.map(st =>
    `<div class="stage"><b>${esc(st.stage)}</b><span class="r">${esc(st.refs)}</span><div>${esc(st.what)}</div></div>`).join("");
  if (culmination) h += `<h3>Where it comes to a head</h3><div>${esc(culmination)}</div>`;
  if ((tensions || []).length) h += `<h3>Where the passages pull against each other</h3>` + tensions.map(tn =>
    `<div class="tension">${esc(tn.tension)}<div class="r">${esc(tn.refs)}</div></div>`).join("");
  if (unresolved) h += `<h3>Left open</h3><div>${esc(unresolved)}</div>`;
  return h + `</div>`;
}
const themeName = t => (t && t[4] && t[4][0]) ? t[4][0] : "";
const themeGloss = t => (t && t[4] && t[4][2]) ? t[4][2] : (t ? t[0] : "");
const BARR = `A theme is not a word. One theme runs on many unrelated words, and one word serves many themes — the caution James Barr pressed on word studies. The vocabulary below is what these passages happen to use, ranked by how much more often each word stands here than elsewhere. It is evidence about the passages, not a definition of the theme.`;
async function renderThemes(book, ch, head){
  const main = $("#main");
  main.innerHTML = head + `<p class="empty">Loading themes…</p>`;
  try { await themesLoad(); } catch (e) { main.innerHTML = head + `<p class="empty">Themes are not built yet — run scripts/build_themes.py.</p>`; return; }
  try { await theolLoad(); } catch (e) {}
  const here = (typeof CHTHEME !== "undefined" && CHTHEME[`${disp(book)}|${ch}`]) || [];
  let html = head + `<div class="thm">`;
  html += `<p class="empty" style="margin:0 0 .6rem">What the model found this chapter to be about, read chapter by chapter and then gathered across the whole Bible. This is a reading, not a tagged fact: every theme names the verses it came from, so it can be checked.</p>`;
  if (!here.length) html += `<p class="empty">No themes recorded for ${disp(book)} ${ch} yet.</p>`;
  for (const [id, verses, label] of here) {
    const t = THEMES[id];
    const nm = themeName(t);
    html += `<div class="t"><b onclick="showTheme('${id}')">${nm ? `<span class="orig">${esc(nm)}</span> <span style="font-weight:400;color:var(--muted)">${esc(themeGloss(t))}</span>` : esc((t && t[0]) || label)}</b>
      <span class="vv" onclick="goto('#${book}/${ch}${/^\d+$/.test(verses) ? "/" + verses : ""}')">${esc(verses || "")}</span>
      <div class="w">${esc(label && t && label !== t[0] ? "in this chapter: " + label : ((t && t[1]) || ""))}</div>
      ${t ? `<div class="w">${t[2].length} passage${t[2].length === 1 ? "" : "s"} in all</div>` : ""}</div>`;
  }
  main.innerHTML = html + `</div>` + bookArgHtml(book);
}
async function showTheme(id){
  hidePop(); hideRefs(); await themesLoad(); await lexLoad(); await theolLoad().catch(() => {}); navRender(null);
  const t = THEMES[id]; if (!t) return;
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr");
  const nm = themeName(t), face = t[4] || [];
  let html = `<h2>${nm ? `<span class="orig">${esc(nm)}</span>` : esc(t[0])}<small class="lang">${nm ? esc(themeGloss(t)) + " · " : ""}${t[2].length} passage${t[2].length === 1 ? "" : "s"} · a reading, not a tagged fact</small></h2>`;
  if (nm) html += `<p class="empty" style="margin:0 0 .8rem">Named in the language of the text${face[1] ? ` (${esc(face[1])})` : ""}${face[3] ? ` — ${esc(face[3])}` : ""}${t[0] && t[0] !== themeGloss(t) ? ` · read in English as “${esc(t[0])}”` : ""}</p>`;
  if (t[1]) html += `<p class="empty" style="margin:0 0 1rem">${esc(t[1])}</p>`;
  html += trajHtml(id);
  html += `<h3 style="font:600 calc(11px * var(--ui)) system-ui,sans-serif;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:1.4rem 0 .3rem">The passages it was read from</h3>`;
  html += `<div class="thm">` + t[2].map(([b, c, vv]) => {
    const bb = b.replace(/ /g, "_");
    const [txt] = verseText(bb, c, (String(vv).match(/\d+/) || [1])[0]);
    return `<div class="t"><b onclick="goto('#${bb}/${c}')">${esc(b)} ${c}${vv ? ":" + esc(String(vv)) : ""}</b>
      <div class="w">${esc(String(txt).slice(0, 170))}</div></div>`;
  }).join("") + `</div>`;
  if ((t[3] || []).length) {
    html += `<h3 style="font:600 calc(11px * var(--ui)) system-ui,sans-serif;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:1.4rem 0 .3rem">The words these passages use</h3>`;
    html += `<div class="thm"><div class="cav">${esc(BARR)}</div></div>`;
    html += `<div class="vocab">` + t[3].map(([tag, head, gloss, lift, n]) =>
      `<a onclick="showConc('${tag}')"><span class="orig">${esc(head)}</span> <small>${esc(gloss)} · ${n}× here, ${lift}× as often as elsewhere</small></a>`).join("") + `</div>`;
  }
  main.innerHTML = html;
  window.scrollTo(0, 0);
}
function themeWordHtml(tag){                             // in the word popup: the themes this word turns up under
  if (typeof THEMEWORD === "undefined") return "";
  const ids = THEMEWORD[tag]; if (!ids || !ids.length) return "";
  return `<div class="dom">Turns up under: ${ids.slice(0, 6).map(id => `<a onclick="showTheme('${id}')">${esc(themeGloss(THEMES[id]) || "?")}</a>`).join(" · ")}${ids.length > 6 ? ` and ${ids.length - 6} more` : ""}</div>`;
}

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
  return `<div class="row"><b onclick="goto('#${b.replace(/ /g, "_")}/${c}/${v}')">${withRef ? esc(b) + " " : ""}${c}:${v}</b>
    <span><span class="num">${n}</span> ${esc(unit)} — ${esc(KIND[kind] || kind)}${who ? " · " + esc(who) : ""}${of ? " · of " + esc(of) : ""}
    <div class="q">“${esc(text)}”</div></span></div>`;
}

/* ---------- places: where the chapter happens, drawn offline (OpenBible.info CC BY 4.0 + Natural Earth, public domain) ---------- */
const placesLoad = () => typeof PLACES !== "undefined" ? Promise.resolve() : loadJs("morph/places.js");
const SYN = {}, synLoad = book => SYN[disp(book)] ? Promise.resolve() : loadJs(`morph/syn_${book}.js`);
function synHtml(book, ch, v, i){
  const w = (((SYN[disp(book)] || {})[ch] || {})[v] || [])[i]; if (!w) return "";
  const [role, cls, dom, refTo] = w;
  let h = "";
  if (role || cls) h += `<div class="syn">In the clause: <b>${esc(role || cls)}</b>${role && cls && role !== cls ? ` (${esc(cls)})` : ""}`;
  if (refTo) { const [b2, c2, v2, i2] = refTo.split("|");
    const t = (((SYN[disp(b2)] || {})[c2] || {})[v2] || [])[i2];
    h += `${h ? " · " : `<div class="syn">`}refers to <a onclick="gotoWord('${b2.replace(/ /g, "_")}',${c2},${v2},${i2})">${esc((t && t[4]) || "the earlier word")} (${esc(b2)} ${c2}:${v2})</a>`; }
  if (h) h += `</div>`;
  return h;
}
function gotoWord(book, ch, v, i){
  hidePop();
  goto(`#${book}/${ch}/${v}`);
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
/* A button rather than a label, with the verse it stands for written on it:
   the same verse is numbered twice in the side-by-side views, and both copies
   have to show the same held state. */
const vnum = (b, c, n) => `<sup class="v" role="button" tabindex="-1" aria-pressed="false"`
  + ` data-v="${b}|${c}|${n}" aria-label="Verse ${n}">${n}</sup>`;
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
  return `<div class="r" onclick="goto('#${b}/${c}/${v}');hideRefs()"><b>${disp(b)} ${c}:${v}${end && end > v ? "–" + end : ""}${note ? ` <span style="font-weight:400;color:var(--muted)">${note}</span>` : ""}</b><span lang="${lang}" dir="${dir}">${ruby(esc(txt))}</span></div>`;
}
async function showRefs(book, ch, v, ev){
  if (ev) ev.stopPropagation();
  if (!adv()) return;                     // in basic mode a verse number is a verse number
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
  reachable(vpop);
  const el = ev && ev.target, r = el ? el.getBoundingClientRect() : {left: 40, bottom: 80, top: 80};
  const W = vpop.offsetWidth, H = vpop.offsetHeight;
  // The verse bar is what opens this, and it sits at the foot of the screen:
  // the popup stops above it rather than having its last lines covered.
  const floor = (vbar && !vbar.hidden ? vbar.getBoundingClientRect().top : window.innerHeight) - 8;
  let x = Math.min(r.left, window.innerWidth - W - 10), y = r.bottom + 6;
  if (y + H > floor) y = Math.max(8, floor - H);
  vpop.style.left = Math.max(8, x) + "px"; vpop.style.top = y + "px";
}
document.addEventListener("click", e => { if (!e.target.closest("#vpop") && !e.target.closest("#vbar")) hideRefs(); });
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
  html += `<div class="harm hdr" style="position:sticky;top:var(--barH);background:var(--bg);z-index:2;padding-top:.2rem"><div class="vs" style="grid-template-columns:repeat(${cols.length},1fr)">`
    + cols.map(c => `<div class="lab" style="cursor:default">${c}</div>`).join("") + `</div></div>`;
  for (const n of nums) {
    const hits = P[n] || [];
    const cells = cols.map(cname => {
      if (cname === disp(book)) {
        const [txt, lang, dir] = verseText(book, ch, n);
        return `<div><div class="lab" onclick="goto('#${book}/${ch}/${n}')">${disp(book)} ${ch}:${n}</div><div class="txt" lang="${lang}" dir="${dir}">${ruby(esc(txt))}</div></div>`;
      }
      const h = hits.filter(r => r[0] === cname).sort((a, b) => b[3] - a[3])[0];
      if (!h) return `<div></div>`;
      const b2 = h[0].replace(/ /g, "_"), [txt, lang, dir] = verseText(b2, h[1], h[2]);
      return `<div><div class="lab" onclick="goto('#${b2}/${h[1]}/${h[2]}')">${h[0]} ${h[1]}:${h[2]} <small>${Math.round(h[3] * 100)}%</small></div><div class="txt dim" lang="${lang}" dir="${dir}">${ruby(esc(txt))}</div></div>`;
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
const domLoad = () => typeof DOMTAG !== "undefined" ? Promise.resolve() : loadJs("morph/domains.js");
const lexemeLoad = () => typeof FORM2LEX !== "undefined" ? Promise.resolve() : loadJs("morph/lexemes.js");
function oursLexeme(form){                               // our own inventory, grown from the text by the model
  if (typeof FORM2LEX === "undefined") return "";
  const id = FORM2LEX[form]; if (!id) return "";
  const [head, pos, gloss, root] = LEXEME[id];
  return `<div class="syn">This project's lexeme <b>${esc(id)}</b>: <span class="orig">${esc(head)}</span> — ${esc(gloss)}${pos ? " (" + esc(pos) + ")" : ""}${root ? ` · root <span class="orig">${esc(root)}</span>` : ""}</div>`;
}
function domHtml(tag){                                   // our own fields of meaning, assigned by the model from the glosses
  if (typeof DOMTAG === "undefined") return "";
  const ds = DOMTAG[tag]; if (!ds || !ds.length) return "";
  return `<div class="dom">Fields of meaning: ${ds.map(d => `<a onclick="showDomain('${attr(d)}')">${esc(d)}</a>`).join(" · ")}</div>`;
}
/* ---------- one entry point per layer, so the dashboard's work bar can open what a job produced ---------- */
async function openView(key){
  /* The dashboard opens a layer by name. Everything but the search box belongs
     to advanced mode, so asking for one is asking to be in it. */
  if (READER_ONLY && key !== "search-index") return;
  if (key !== "search-index" && !adv()) { mode = "advanced"; localStorage.setItem("mode", "advanced"); applyMode(); }
  const go = {
    "lexeme-inventory": browseLexemes, "concordance": browseLexemes,
    "lexicon": browseLexicon, "lexicon-brief": browseLexicon, "lexicon-translated": browseLexicon,
    "fields": browseFields, "themes": browseThemes, "trajectories": browseThemes,
    "book-arguments": browseArguments,
    "morphology": () => { if (!inter) toggleInter(); setView("orig"); },
    "clause-data": () => { if (!inter) toggleInter(); setView("orig"); },
    "search-index": () => focusSearch(),
    "text-notes": () => { setView("orig"); showFirstRefs(); },
    "cross-references": () => { setView("tr"); showFirstRefs(); },
    "parallels": () => setView("harm"), "places": () => setView("map"), "chronology": () => setView("chron"),
  }[key];
  if (go) await go();
}
const shelf = (title, note, items) => `<h2>${esc(title)}<small class="lang">${esc(note)}</small></h2>`
  + `<div class="plist">` + items.join("") + `</div>`;

async function browseThemes(){                           // every theme, most attested first
  hidePop(); hideRefs(); navRender(null);
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  try { await themesLoad(); await theolLoad().catch(() => {}); } catch (e) {
    main.innerHTML = `<h2>Themes</h2><p class="empty">Not built yet — run scripts/build_themes.py.</p>`; return; }
  const ids = Object.keys(THEMES).sort((a, b) => THEMES[b][2].length - THEMES[a][2].length);
  const withTraj = typeof TRAJ !== "undefined" ? ids.filter(i => TRAJ[i]).length : 0;
  main.innerHTML = shelf("Themes", `${ids.length} themes · ${withTraj} traced across the canon · read out of the chapters`,
    ids.map(id => { const t = THEMES[id];
      const nm = themeName(t);
      return `<a onclick="showTheme('${id}')">${nm ? `<span class="orig">${esc(nm)}</span> ` : ""}${esc(nm ? themeGloss(t) : t[0])} <small>${t[2].length} passage${t[2].length === 1 ? "" : "s"}${typeof TRAJ !== "undefined" && TRAJ[id] ? " · traced" : ""}</small></a>`; }));
  window.scrollTo(0, 0);
}
async function browseArguments(){                        // the books whose argument has been written
  hidePop(); navRender(null);
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  try { await theolLoad(); } catch (e) {
    main.innerHTML = `<h2>What each book argues</h2><p class="empty">Not built yet — run scripts/build_theology.py --books.</p>`; return; }
  const names = Object.keys(BOOKARG).sort((a, b) => ORDER[a.replace(/ /g, "_")] - ORDER[b.replace(/ /g, "_")]);
  if (!names.length) { main.innerHTML = `<h2>What each book argues</h2><p class="empty">No book arguments yet.</p>`; return; }
  main.innerHTML = shelf("What each book argues", `${names.length} of 66 books · built from their chapters' themes`,
    names.map(n => `<a onclick="showArgument('${n.replace(/ /g, "_")}')">${esc(n)} <small>${(BOOKARG[n][0] || []).length} sections</small></a>`));
  window.scrollTo(0, 0);
}
async function showArgument(book){
  await theolLoad().catch(() => {});
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  main.innerHTML = `<h2>${esc(disp(book))}<small class="lang">what the book argues</small></h2>` + bookArgHtml(book)
    + `<p class="empty"><a style="cursor:pointer;color:var(--accent)" onclick="browseArguments()">all books</a> · <a style="cursor:pointer;color:var(--accent)" onclick="goto('#${book}/1')">read it</a></p>`;
  window.scrollTo(0, 0);
}
async function browseLexicon(){                          // our own entries, the fullest first
  hidePop(); navRender(null);
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  try { await lexLoad(); await lexxLoad(); await lexxtLoad(tl).catch(() => {}); } catch (e) {
    main.innerHTML = `<h2>Our lexicon</h2><p class="empty">Not built yet — run scripts/build_lexicon.py.</p>`; return; }
  const tags = Object.keys(LEXX).sort((a, b) => (LEXX[b].count || 0) - (LEXX[a].count || 0));
  main.innerHTML = shelf("Our lexicon", `${tags.length} entries written from the text${(LEXXT[tl] ? " · shown in " + TARGETS[tl].native + " where translated" : "")}`,
    tags.map(t => { const e = LEXX[t], tr = (LEXXT[tl] || {})[t];
      return `<a onclick="showLexEntry('${t}')"><span class="orig">${esc(e.headword)}</span> <small>${esc((tr && tr.gloss) || e.gloss)} · ${e.count}×</small></a>`; }));
  window.scrollTo(0, 0);
}
async function showLexEntry(tag){
  await lexLoad(); await lexxLoad().catch(() => {}); await domLoad().catch(() => {}); await themesLoad().catch(() => {});
  const e = LEX[tag] || ["", "", "", "", ""];
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  main.innerHTML = `<h2><span class="orig">${esc(e[0] || tag)}</span><small class="lang">${esc(e[1] || "")} ${esc(e[2] || "")} · ${tag}</small></h2>`
    + `<div id="wpopinline">${oursHtml(tag)}${domHtml(tag)}${themeWordHtml(tag)}</div>`
    + `<p class="empty"><a style="cursor:pointer;color:var(--accent)" onclick="showConc('${tag}')">every occurrence</a> · <a style="cursor:pointer;color:var(--accent)" onclick="browseLexicon()">all entries</a></p>`;
  window.scrollTo(0, 0);
}
async function browseLexemes(){                          // the inventory grown from the word forms
  hidePop(); navRender(null);
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  try { await lexemeLoad(); } catch (e) {
    main.innerHTML = `<h2>Our lexeme inventory</h2><p class="empty">Not built yet — run scripts/build_lexemes.py.</p>`; return; }
  const ids = Object.keys(LEXEME).sort((a, b) => LEXEME[b][4] - LEXEME[a][4]);
  main.innerHTML = shelf("Our lexeme inventory", `${ids.length} dictionary words grown from ${Object.keys(FORM2LEX).length} word forms`,
    ids.slice(0, 1200).map(id => { const [head, pos, gloss, root, count] = LEXEME[id];
      return `<a onclick="showLexeme('${id}')"><span class="orig">${esc(head)}</span> <small>${esc(gloss)}${pos ? " · " + esc(pos) : ""} · ${count}×</small></a>`; }));
  if (ids.length > 1200) main.innerHTML += `<p class="empty">Showing the 1,200 commonest of ${ids.length}.</p>`;
  window.scrollTo(0, 0);
}
async function showLexeme(id){
  await lexemeLoad();
  const [head, pos, gloss, root, count] = LEXEME[id];
  const forms = Object.keys(FORM2LEX).filter(f => FORM2LEX[f] === id);
  const main = $("#main"); main.className = "wide"; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  main.innerHTML = `<h2><span class="orig">${esc(head)}</span><small class="lang">${esc(gloss)}${pos ? " · " + esc(pos) : ""}${root ? " · root " + root : ""} · ${id} · ${count} occurrence${count === 1 ? "" : "s"}</small></h2>`
    + `<p class="empty" style="margin:0 0 1rem">Grown from the text: the model read each of these written forms in its verse and gave this dictionary word for it.</p>`
    + `<div class="plist">` + forms.map(f => `<a onclick="searchSource('${attr(f)}')"><span class="orig">${esc(f)}</span> <small>find it in the text</small></a>`).join("") + `</div>`
    + `<p class="empty"><a style="cursor:pointer;color:var(--accent)" onclick="browseLexemes()">all lexemes</a></p>`;
  window.scrollTo(0, 0);
}
async function searchSource(form){                       // find a Hebrew or Greek form through the source index
  const name = /[\u0590-\u05ff]/.test(form) ? "hbo" : "grc";
  try { await idxLoad(name); } catch (e) {}
  const ids = idxVerses(name, foldTerm(form)) || [];
  const main = $("#main"); main.className = ""; main.setAttribute("dir", "ltr"); main.setAttribute("lang", "en");
  main.innerHTML = `<h2><span class="orig">${esc(form)}</span><small class="lang">${ids.length} verse${ids.length === 1 ? "" : "s"} in the original</small></h2>`
    + `<div id="results">` + ids.slice(0, 400).map(id => {
        const b = byNumBook[Math.floor(id / 1000000)], c = Math.floor(id / 1000) % 1000, v = id % 1000;
        return b ? `<div class="hit" onclick="goto('#${b}/${c}/${v}')"><div class="ref">${disp(b)} ${c}:${v}</div>${verseHtml(b, c, v, -1)}</div>` : "";
      }).join("") + `</div>`;
  window.scrollTo(0, 0);
}

async function browseFields(){                           // the fields of meaning, as a list to pick from
  hidePop(); await domLoad().catch(() => {}); navRender(null);
  const main = $("#main"); main.className = ""; main.setAttribute("dir", "ltr");
  if (typeof DOMLIST === "undefined") { main.innerHTML = `<h2>Fields of meaning</h2><p class="empty">Not built yet — run scripts/build_domains.py.</p>`; return; }
  const used = DOMLIST.filter(d => (DOMAINS[d] || []).length);
  main.innerHTML = `<h2>Fields of meaning<small class="lang">${used.length} fields · this project's own grouping</small></h2>`
    + `<p class="empty" style="margin:0 0 1rem">Each lexeme is sorted by its usage and gloss into fields written for this project. No published domain lexicon is used.</p>`
    + `<div class="plist">` + used.map(d => `<a onclick="showDomain('${attr(d)}')">${esc(d)} <small>${(DOMAINS[d] || []).length} words</small></a>`).join("") + `</div>`;
  window.scrollTo(0, 0);
}
async function showDomain(name){
  hidePop(); await domLoad(); await lexLoad(); navRender(null);
  const members = (DOMAINS[name] || []);
  const main = $("#main"); main.className = ""; main.setAttribute("dir", "ltr");
  main.innerHTML = `<h2>${esc(name)}<small class="lang">${members.length} word${members.length === 1 ? "" : "s"} · this project's own grouping</small></h2>`
    + `<p class="empty" style="margin:0 0 1rem">Assigned by the model from each word's usage and gloss. The fields are this project's own wording; no published domain lexicon is used.</p>`
    + `<div class="plist">` + members.map(([t, head, gloss]) =>
        `<a onclick="showConc('${attr(t)}')"><span class="orig">${esc(head)}</span> <small>${esc(gloss)}</small></a>`).join("") + `</div>`
    + `<p class="empty">Other fields: ${DOMLIST.filter(d => d !== name && (DOMAINS[d] || []).length).map(d => `<a style="cursor:pointer;color:var(--accent)" onclick="showDomain('${attr(d)}')">${esc(d)}</a>`).join(" · ")}</p>`;
  window.scrollTo(0, 0);
}
const refLink = r => { const m = r.match(/^(.+?) (\d+):(\d+)$/); return m ? `<a onclick="hidePop();goto('#${m[1].replace(/ /g, "_")}/${m[2]}/${m[3]}')">${r}</a>` : esc(r); };
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
  await morphLoad(book); await lexLoad(); await Promise.all([lexxLoad().catch(() => {}), lexxtLoad(tl).catch(() => {}), synLoad(book).catch(() => {}), domLoad().catch(() => {}), lexemeLoad().catch(() => {}), themesLoad().catch(() => {})]);
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
    html += domHtml(root);
    html += themeWordHtml(root);
    html += oursLexeme(el.textContent);
    html += `<div>gloss: <b>${esc(d[2])}</b>${greek && d[3] && d[3] !== d[2] ? ` · <span class="tl">${esc(d[3])}</span>` : ""}</div>`;
    const extra = (d[0].match(TAGRE) || []).filter(t => t !== root && LEX[t]);
    if (extra.length) html += `<div class="pre">with: ${extra.map(t => `${esc(LEX[t][0])} <i>${esc(LEX[t][3])}</i>`).join(", ")}</div>`;
    if (e && e[4]) html += `<div class="meaning">${esc(e[4])}</div>`;
    html += oursHtml(root);
    html += `<div class="acts"><a onclick="showConc('${root}')">all occurrences</a><a onclick="gsOpen('${root}', '${attr(d[1])}')">this form elsewhere</a><a onclick="hidePop()">close</a></div>`;
  }
  wpop.innerHTML = html; wpop.hidden = false;
  reachable(wpop);
  const r = el.getBoundingClientRect(), W = wpop.offsetWidth, H = wpop.offsetHeight;
  let x = Math.min(r.left, window.innerWidth - W - 10), y = r.bottom + 6; if (y + H > window.innerHeight - 8) y = Math.max(8, r.top - H - 6);
  wpop.style.left = Math.max(8, x) + "px"; wpop.style.top = y + "px";
}
document.addEventListener("click", e => { const w = e.target.closest("main .w"); if (w && adv()) { showPop(w); return; } if (!e.target.closest("#wpop")) hidePop(); });
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
    if (b !== lastBook) { html += `<h3 style="font:600 calc(13px * var(--ui)) system-ui,sans-serif;color:var(--muted);margin:1rem 0 .3rem">${disp(b)}</h3>`; lastBook = b; }
    html += `<div class="hit" onclick="goto('#${b}/${ch}/${v}')"><div class="ref">${disp(b)} ${ch}:${v}</div>${verseHtml(b, ch, v, i)}</div>`;
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
  /* The analysis views read the original text, not the translation, so an
     untranslated chapter is no reason to refuse them — the Gospels are exactly
     where a reader wants the parallels, and they were unreachable there. */
  const analysis = v === "themes" || v === "harm" || v === "map" || v === "chron";
  if (!src) v = "tr";
  else if (!tr && !analysis) v = ((v === "lxx" || v === "hl") && lxx) ? v : "orig";
  else if (v === "all" && avail.length < 2 && !lxx) v = "par";
  if ((v === "lxx" || v === "hl") && !lxx) v = "orig";
  /* Basic mode is the book: the translation, or the text it was made from. */
  if (!adv() && v !== "tr" && v !== "orig") v = tr ? "tr" : "orig";
  /* The heading says what is actually on the screen rather than everything the
     chapter has, because the bar repeats it and a reader in the Septuagint
     should not be told they are reading Hebrew. */
  const sub = v === "orig" ? L.name : v === "lxx" ? "Septuagint" : v === "hl" ? `${L.name} · Septuagint`
    : v === "all" ? `${L.name}${lxx ? " + Septuagint" : ""} → ${avail.length} language${avail.length === 1 ? "" : "s"}`
    : tr ? `${L.name} → ${TARGETS[shown].name}` : L.name;
  setTitle(`${disp(book)} ${ch}`, sub);
  let html = `<h2>${disp(book)} ${ch}<small class="lang">${esc(sub)}</small></h2>`;
  html += `<div class="chnav">` + chs.map(c =>
    `<a href="#${book}/${c}" class="${c==ch?'on':''} ${trOf(book,c)[tl]?'':'untr'}">${c}</a>`).join("") + `</div>`;
  if (src && adv()) {
    html += `<div class="tabs"><a class="${v==='orig'?'on':''}" onclick="setView('orig')">${L.name}</a>`;
    if (lxx) html += `<a class="${v==='lxx'?'on':''}" onclick="setView('lxx')" title="Swete's Septuagint">Septuagint</a><a class="${v==='hl'?'on':''}" onclick="setView('hl')" title="Hebrew and the Septuagint side by side">Hebrew · Septuagint</a>`;
    html += `<span class="sep"></span>`;
    for (const t of haveTargets)
      html += `<a class="${v==='tr'&&shown===t?'on':''} ${trs[t]?'':'off'}" onclick="setTl('${t}');setView('tr')">${TARGETS[t].native}</a>`;
    html += `<span class="sep"></span><a class="${v==='par'?'on':''} ${tr?'':'off'}" onclick="setView('par')">Side by side</a>`;
    html += `<a class="${v==='all'?'on':''} ${(avail.length + (lxx?1:0))>1?'':'off'}" onclick="setView('all')">Compare</a>`;
    // the analysis tabs, in the order the layers are built: words, then lexemes and meaning, then themes, then arguments, then notes on a verse
    html += `<i class="sep" title="analysis"></i>`;
    html += `<a class="tool ${inter?'on':''}" onclick="toggleInter()" title="words: gloss and parsing under every Hebrew or Greek word">interlinear</a>`;
    html += `<a class="tool" onclick="gsOpen()" title="words: find words by grammatical form">grammar search</a>`;
    html += `<a class="tool" onclick="browseFields()" title="meaning: the fields this project sorts its lexemes into">fields of meaning</a>`;
    html += `<a class="tool ${v==='themes'?'on':''}" onclick="setView('themes')" title="themes: what this chapter is about, where else it is taken up, and what the book argues">themes</a>`;
    html += `<a class="tool ${v==='harm'?'on':''}" onclick="setView('harm')" title="notes: this chapter beside the passages that share its wording">parallels</a>`;
    html += `<a class="tool ${v==='map'?'on':''}" onclick="setView('map')" title="notes: the places this chapter mentions, on a map">places</a>`;
    html += `<a class="tool ${v==='chron'?'on':''}" onclick="setView('chron')" title="notes: the chronological statements here, and the dated anchors">chronology</a></div>`;
  }
  main.className = ((v === "par" || v === "all" || v === "hl" || v === "harm" || v === "map" || v === "chron" || v === "themes") ? "wide" : "") + (inter && adv() && src && (v === "orig" || v === "par" || v === "all" || v === "hl") ? " inter" : "");
  /* The word tags are a file per book, fetched the first time the book is
     opened. Until it arrives the text reads normally with no glosses under it,
     which is silent and puzzling in interlinear; and if it never arrives the
     reader should be told rather than left staring at a view that never fills.
     Basic mode never uses them - a tap on a word does nothing there - so it
     does not fetch them either; the reader-only build does not even carry
     them, and would warn on every book. setMode re-routes, which fetches them
     the moment advanced mode is chosen. */
  if (src && adv() && !MORPH[disp(book)]) {
    if (inter && adv()) html += `<p class="empty" role="status">Loading the word tags for ${disp(book)}…</p>`;
    morphLoad(book)
      .then(() => { if (location.hash.slice(1).split("/").slice(0, 2).join("/") === `${book}/${ch}`) route(); })
      .catch(() => toast(`The word tags for ${disp(book)} could not be loaded, so there are no glosses or parsing here. The text itself is unaffected.`));
  }
  main.setAttribute("lang", (v === "orig" || v === "lxx" || v === "hl") ? "" : (shown || "en"));
  main.setAttribute("dir", (v === "tr" && shown) ? tdir(shown) : "ltr");
  if (!tr) html += `<p class="empty" style="margin:0 0 1.2rem">Not translated yet${src ? ` — showing the ${v === "lxx" ? "Septuagint" : L.name}.` : "."}</p>`;
  /* A chapter the chosen language has not reached falls back to whatever
     translation the chapter does have, which is better than an empty page -
     but it used to do it in silence. The language menu still said 日本語
     while the page was in English, and a reader was left to decide whether
     the app was broken or that was what Japanese looked like. */
  else if (shown !== tl && TARGETS[tl]) html += `<p class="empty" style="margin:0 0 1.2rem">`
    + `${esc(TARGETS[tl].native || TARGETS[tl].name)}: not translated this far yet`
    + ` — showing the ${esc(TARGETS[shown].name)}.</p>`;
  if (v === "harm") { renderHarmony(book, ch, html, shown); return; }
  if (v === "map") { renderMap(book, ch, html); return; }
  if (v === "chron") { renderChron(book, ch, html); return; }
  if (v === "themes") { renderThemes(book, ch, html); return; }
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
  goto(`#${book}/${m[2]||1}${m[3] ? "/"+m[3] : ""}`);
  return true;
}

/* ---------- search (in the selected translation) ---------- */
const BUILD = "__BUILT__";               // when this page was built, so a phone can say which copy it is running
const IDX = {};
const idxLoad = name => IDX[name] ? Promise.resolve() : loadJs(`morph/idx_${name}.js`);
const foldTerm = t => t.normalize("NFD").replace(/[\u0300-\u036f\u0591-\u05c7]/g, "").normalize("NFC").toLowerCase();
function idxVerses(name, term){                          // -> verse ids for one term, or null when it is not indexed
  const enc = IDX[name] && IDX[name][term]; if (!enc) return null;
  const out = []; let p = 0;
  for (const x of enc.split(".")) { p += parseInt(x, 16); out.push(p); }
  return out;
}
const byNumBook = {}; for (const b in ORDER) byNumBook[ORDER[b]] = b;
function idxCandidates(name, q){                         // verses holding every term of the query, or null to fall back
  if (!IDX[name]) return null;
  const words = q.split(/[^\p{L}\p{M}\p{N}]+/u).filter(Boolean).map(foldTerm);
  if (!words.length) return null;
  let acc = null;
  for (const w of words) {
    const got = idxVerses(name, w) || idxVerses(name, w.slice(0, 3)) || idxVerses(name, w.slice(0, 2));
    if (!got) return IDX[name][w] === undefined && w.length > 3 ? null : [];   // a word the index knows is absent means no hits
    const set = new Set(got);
    acc = acc === null ? set : new Set([...acc].filter(v => set.has(v)));
    if (!acc.size) break;
  }
  return acc ? [...acc].sort((a, b) => a - b) : [];
}
/* Typing ?diag into the search box says what this copy of the reader actually
   has in it. On a phone there is no console and no way to look inside the app,
   so when something does not work this is what can be read out. */
async function diagnostics(){
  let idxState = "not loaded";
  try { await idxLoad(tl); idxState = `${Object.keys(IDX[tl] || {}).length} indexed words`; }
  catch (e) { idxState = `could not load morph/idx_${tl}.js (${e && e.message || e})`; }
  const chapters = srcBooks.reduce((n, b) => n + Object.keys(DATA[b]).length, 0);
  const translated = srcBooks.reduce((n, b) => n + Object.values(DATA[b]).filter(c => c.tr && c.tr[tl]).length, 0);
  let store = "working";
  try { localStorage.setItem("_t", "1"); localStorage.removeItem("_t"); } catch (e) { store = `blocked (${e.name})`; }
  const rows = [["Built", BUILD], ["Address", location.href], ["Reading language", tl],
                ["Languages in this copy", Object.keys(TARGETS).join(", ") || "none"],
                ["Books / chapters", `${srcBooks.length} / ${chapters}`],
                ["Chapters in " + tl, translated], ["Search index", idxState],
                ["Study layers", READER_ONLY ? "not in this build (the reader alone)"
                    : `${Object.keys(typeof MORPH === "undefined" ? {} : MORPH).length} books of word tags loaded`],
                ["Settings storage", store], ["Browser", navigator.userAgent]];
  return `<h2>What this copy holds<small class="lang">type ?diag in the search box to see this</small></h2>`
    + `<div class="cmp">` + rows.map(([k, v]) =>
        `<div class="row"><span class="lab">${esc(k)}</span><span class="txt">${esc(String(v))}</span></div>`).join("")
    + `</div>`;
}

async function search(q) {
  navRender(null);
  q = q.trim();
  const main = $("#main");
  main.className = ""; main.setAttribute("lang", "en"); main.setAttribute("dir", "ltr");
  if (q === "?diag") { main.innerHTML = await diagnostics(); return; }
  main.setAttribute("lang", tl);
  if (q.length < 2) { main.innerHTML = `<p class="empty">Type at least two characters.</p>`; return; }
  try { await idxLoad(tl); } catch (e) {}
  const rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  const hits = [];
  const cand = idxCandidates(tl, q);
  if (cand) {
    for (const id of cand) {
      const book = byNumBook[Math.floor(id / 1000000)], ch = String(Math.floor(id / 1000) % 1000), v = String(id % 1000);
      const t = book && trOf(book, ch)[tl];
      const sv = t && t.verses[v];
      if (!sv) continue;
      rx.lastIndex = 0;
      if (rx.test(sv)) { hits.push({book, ch, v, t: sv}); if (hits.length >= 500) break; }
    }
  } else {
    outer:
    for (const book of booksWith(tl)) {
      for (const ch of chapterList(book)) {
        const t = trOf(book, ch)[tl];
        if (!t) continue;
        for (const [v, sv] of Object.entries(t.verses)) {
          rx.lastIndex = 0;
          if (rx.test(sv)) { hits.push({book, ch, v, t: sv}); if (hits.length >= 200) break outer; }
        }
      }
    }
  }
  let html = `<h2>Search: “${esc(q)}”<small class="lang">${TARGETS[tl].name}</small></h2><div id="results">`;
  html += `<p class="empty">${hits.length}${hits.length >= 500 ? "+" : ""} verse${hits.length === 1 ? "" : "s"} found${cand ? "" : " · scanned, this text has no index yet"}.</p>`;
  for (const h of hits) {
    rx.lastIndex = 0;
    html += `<div class="hit" lang="${tl}" dir="${tdir(tl)}" onclick="goto('#${h.book}/${h.ch}/${h.v}')">
      <div class="ref">${disp(h.book)} ${h.ch}:${h.v}</div>
      ${ruby(esc(h.t).replace(rx, m => `<mark>${m}</mark>`))}</div>`;
  }
  main.innerHTML = html + "</div>";
}

/* ---------- a verse in the hand ----------
   Tapping a verse takes hold of it: the whole verse lights up, and a bar says
   what can be done with it - copy it with its reference, send it to someone,
   or hear it read. In the app those three go to the phone itself through the
   shell's AndroidApp; in a browser they go to whatever the browser has, and
   the buttons that have nothing behind them are not offered. */
const PHONE = (typeof AndroidApp !== "undefined" && AndroidApp) ? AndroidApp : null;   // APP is the apparatus; this is the shell
/* How fast and how high the reading voice is. A phone left to itself speaks at
   whatever rate its accessibility settings ask for, which is often far too
   quick for a text being read rather than skimmed, so the page always says. */
const SPEEDS = [[0.6, "Slow"], [0.8, "Steady"], [1, "Normal"], [1.25, "Quick"]];
const PITCHES = [[0.85, "Low"], [1, "Middle"], [1.15, "High"]];
const VOICE = {rate: +(localStorage.getItem("ttsRate") || 0.8), pitch: +(localStorage.getItem("ttsPitch") || 1)};
const voiceKey = lang => "ttsVoice_" + lang;
const chosenVoice = lang => localStorage.getItem(voiceKey(lang)) || "";
function setChosenVoice(lang, name){
  if (name) localStorage.setItem(voiceKey(lang), name); else localStorage.removeItem(voiceKey(lang));
  redrawSheet();
}
function voicesFor(lang){                                 // the phone's, best first; [] in a browser
  if (!(PHONE && PHONE.voices)) return [];
  try { return JSON.parse(PHONE.voices(lang) || "[]").sort((a, b) => b.quality - a.quality); }
  catch (e) { return []; }
}
if (!(VOICE.rate > 0)) VOICE.rate = 0.8;
if (!(VOICE.pitch > 0)) VOICE.pitch = 1;
function setVoice(k, v){ VOICE[k] = v; localStorage.setItem(k === "rate" ? "ttsRate" : "ttsPitch", v); redrawSheet(); }
const vbar = document.createElement("div"); vbar.id = "vbar"; vbar.hidden = true;
vbar.setAttribute("role", "toolbar"); vbar.setAttribute("aria-label", "What to do with this verse");
document.body.appendChild(vbar);
/* Which verses are held, in the order they were taken. A reference - book,
   chapter and verse - keeps its place in the set when the view around it is
   redrawn and the verse is a different element afterwards. */
let vsel = [];
const vkey = r => r.book + "|" + r.ch + "|" + r.v;
const unkey = k => { const p = k.split("|"); return {book: p[0], ch: +p[1], v: +p[2]}; };
const verseElem = k => document.getElementById("v-" + k.replace(/\|/g, "-"));

function verseOf(el){                                    // -> the element of the verse a tap landed in
  const p = el && el.closest ? el.closest('[id^="v-"]') : null;
  return p && /^v-.+-\d+-\d+$/.test(p.id) ? p : null;
}
function verseRef(el){
  const m = el.id.match(/^v-(.+)-(\d+)-(\d+)$/);
  return m ? {book: m[1], ch: +m[2], v: +m[3]} : null;
}
function verseContent(r){                                // what is actually on the page for that verse
  const d = DATA[r.book] && DATA[r.book][r.ch];
  if (!d) return null;
  const tr = d.tr && d.tr[tl];
  // Whatever is on the screen is what is copied and read aloud: in the views
  // that show only the originals, the translation is not there to be quoted.
  if (view !== "orig" && view !== "lxx" && view !== "hl" && tr && tr.verses[r.v])
    return {txt: tr.verses[r.v].replace(/\n+/g, " "), lang: tl};
  if (d.src && d.src[r.v])
    return {txt: d.src[r.v], lang: (d.src._lang && d.src._lang[r.v]) || d.lang || "hbo"};
  return tr && tr.verses[r.v] ? {txt: tr.verses[r.v].replace(/\n+/g, " "), lang: tl} : null;
}
/* The held verses that are actually on the page, in the order they are read
   rather than the order they were tapped.
   On the page is meant literally: a map, a theme or a lexicon entry is drawn
   over the chapter and has no verses in it, and a bar offering to copy one
   that cannot be seen belongs to nothing on the screen. The verses are not
   let go of, though - they are still held when the chapter comes back. */
function selContent(){
  const out = [];
  for (const k of vsel) { const r = unkey(k), c = verseElem(k) && verseContent(r); if (c) out.push({r, c}); }
  out.sort((a, b) => (ORDER[a.r.book] || 0) - (ORDER[b.r.book] || 0) || a.r.ch - b.r.ch || a.r.v - b.r.v);
  return out;
}
/* One reference for however many verses are held: neighbours close up into a
   range, a gap starts a new one, and a second chapter says its name again. */
function selRef(sel){
  const runs = [];
  for (const {r} of sel) {
    const last = runs[runs.length - 1];
    if (last && last.book === r.book && last.ch === r.ch && r.v === last.to + 1) { last.to = r.v; continue; }
    runs.push({book: r.book, ch: r.ch, from: r.v, to: r.v});
  }
  let out = "", prev = null;
  for (const g of runs) {
    const span = g.from + (g.to > g.from ? "\u2013" + g.to : "");
    if (prev && prev.book === g.book && prev.ch === g.ch) out += ", " + span;
    else { out += (out ? "; " : "") + disp(g.book) + " " + g.ch + ":" + span; prev = g; }
  }
  return out;
}
/* Quotation marks and the reference, because a passage leaves the app to be
   read by someone who cannot see where it came from. More than one verse is
   numbered as it is quoted, so it can be followed against a printed Bible. */
function selQuote(sel){
  const body = sel.length === 1 ? sel[0].c.txt : sel.map(({r, c}) => r.v + " " + c.txt).join("\n");
  return `\u201c${body}\u201d \u2014 ${selRef(sel)}`;
}

function speechFor(lang){                                // "" = not ready yet, "yes", "no"
  if (PHONE && PHONE.voiceFor) { try { return PHONE.voiceFor(lang); } catch (e) { return "no"; } }
  return ("speechSynthesis" in window) ? "yes" : "no";
}
function speakVerse(txt, lang){
  if (PHONE && PHONE.speak) { PHONE.speak(txt, lang, VOICE.rate, VOICE.pitch, chosenVoice(lang)); return; }
  if (typeof ttsSpeak === "function") ttsSpeak(txt, lang, null);
}
function stopSpeaking(){
  if (PHONE && PHONE.stopSpeaking) { PHONE.stopSpeaking(); return; }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}
function copyText(t){
  // The shell says so, not the page: Android 13 and later shows its own copy
  // confirmation, and a toast of ours on top of it would be one too many.
  if (PHONE && PHONE.copy) { PHONE.copy(t, "Copied, with its reference."); return; }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t).then(() => toast("Copied, with its reference."), selectHeld);
    return;
  }
  selectHeld();
}
/* Nothing would take the text: select it on the page instead, so the reader
   can copy it themselves. A run of verses with a gap in it cannot be selected
   as such - one selection is one stretch of the page - so what is offered is
   the stretch from the first held verse to the last. */
function selectHeld(){
  const on = selContent().map(x => verseElem(vkey(x.r))).filter(Boolean);
  if (on.length) {
    const sel = getSelection(), rg = document.createRange();
    rg.setStartBefore(on[0]); rg.setEndAfter(on[on.length - 1]);
    sel.removeAllRanges(); sel.addRange(rg);
  }
  toast("This browser would not let the page copy. The passage is selected \u2014 press Ctrl+C.");
}
function shareText(t, subject){
  if (PHONE && PHONE.share) { PHONE.share(t, subject); return; }
  if (navigator.share) { navigator.share({title: subject, text: t}).catch(() => {}); return; }
  copyText(t);                                           // nothing to share with; the clipboard is the next best thing
}

/* The held state lives in vsel, not in the page, so it is painted on rather
   than toggled: a chapter redrawn underneath a held verse comes back marked. */
function syncVerseMarks(){
  document.querySelectorAll("main .held").forEach(el => el.classList.remove("held"));
  document.querySelectorAll('sup.v[aria-pressed="true"]').forEach(el => el.setAttribute("aria-pressed", "false"));
  for (const k of vsel) {
    const el = verseElem(k); if (el) el.classList.add("held");
    document.querySelectorAll(`sup.v[data-v="${k}"]`).forEach(n => n.setAttribute("aria-pressed", "true"));
  }
}
/* A hundred and seventy-six verse numbers are not a hundred and seventy-six
   stops on the way through the page. The chapter's numbers are one stop, as a
   toolbar is: the first takes the focus and the arrow keys walk from there.
   That is why CLICKABLE below still leaves verse numbers alone. */
function rovingVerses(){
  const nums = document.querySelectorAll("main sup.v");
  if (!nums.length) return;
  let stop = null;
  for (const n of nums) if (n === document.activeElement) stop = n;
  if (!stop) for (const n of nums) if (n.getAttribute("aria-pressed") === "true") { stop = n; break; }
  if (!stop) stop = nums[0];
  for (const n of nums) n.tabIndex = n === stop ? 0 : -1;
}
function dropVerse(){
  if (!vsel.length) return;
  vsel = []; syncVerseMarks(); rovingVerses();
  drawVbar();                              // with nothing held it puts itself away
  stopSpeaking();
}
/* Taking or letting go of a verse stops the reading: what is being spoken is
   no longer what is held, and a voice carrying on over a new selection is the
   most confusing thing the page could do. */
function setSel(keys){
  vsel = keys;
  stopSpeaking();
  syncVerseMarks();
  drawVbar();
}
function toggleVerse(k){
  const i = vsel.indexOf(k);
  if (i >= 0) setSel(vsel.filter((_, j) => j !== i));
  else if (verseContent(unkey(k))) setSel(vsel.concat([k]));
}
/* What the bar is saying, in as few characters as comparing it needs: the
   verses, the language they are in, and the length of what would be copied. */
const selSig = sel => sel.map(x => `${x.r.book} ${x.r.ch}:${x.r.v} ${x.c.lang} ${x.c.txt.length}`).join("|");
let vbarSig = "";

/* The same verse is different text in another view and another language, and
   on a map it is not on the page at all. After the page is redrawn the bar is
   asked again what it should say; it is only rebuilt if the answer changed,
   because rebuilding it costs the shell a call to the phone about voices. */
function refreshVbar(){
  if (selSig(selContent()) !== vbarSig) drawVbar();
}
function drawVbar(){
  const sel = selContent();
  vbarSig = selSig(sel);
  if (!sel.length) { vbar.hidden = true; vbar.innerHTML = ""; vbar.className = ""; return; }
  const lang = sel[0].c.lang, voice = speechFor(lang), many = sel.length > 1;
  const ref = selRef(sel);
  vbar.setAttribute("aria-label", many ? "What to do with these verses" : "What to do with this verse");
  vbar.innerHTML = `<span class="ref" title="${attr(ref)}">${esc(ref)}</span>`
    + `<button type="button" data-a="copy">Copy</button>`
    + `<button type="button" data-a="share">Share</button>`
    + (voice === "no" ? "" : `<button type="button" data-a="listen">Listen</button>`)
    + (!many && adv() ? `<button type="button" data-a="refs" title="Cross-references, parallels and text notes">Notes</button>` : "")
    + `<button type="button" class="x" data-a="close" aria-label="Let go of ${many ? "these verses" : "this verse"}">&#215;</button>`;
  const quoted = selQuote(sel);
  vbar.querySelector('[data-a="copy"]').onclick = () => { copyText(quoted); };
  vbar.querySelector('[data-a="share"]').onclick = () => { shareText(quoted, ref); };
  const hear = vbar.querySelector('[data-a="listen"]');
  if (hear) hear.onclick = () => {
    if (speechFor(lang) === "no") { toast("This phone has no voice for " + ((LANGS[lang] || {}).name || lang) + " installed."); return; }
    speakVerse(sel.map(x => x.c.txt).join(" "), lang);   // the numbers are not read out; they are not the text
  };
  const refs = vbar.querySelector('[data-a="refs"]');
  if (refs) refs.onclick = e => showRefs(sel[0].r.book, sel[0].r.ch, sel[0].r.v, e);
  vbar.querySelector('[data-a="close"]').onclick = dropVerse;
  // Four things and a reference do not fit across a phone; the reference then
  // takes the line above rather than the close button being left on one of
  // its own underneath.
  vbar.classList.toggle("wide", many || vbar.querySelectorAll("button").length > 4);
  vbar.hidden = false;
  reachable(vbar);
}
/* The study popup used to hang off the verse number, which is now the button
   that holds the verse; the tour reaches it the way a reader does. */
function showFirstRefs(){
  const n = document.querySelector("main sup.v");
  if (!n) return;
  setSel([n.dataset.v]);
  const b = vbar.querySelector('[data-a="refs"]');
  if (b) b.click();
}
/* A tap on a verse number takes that verse and leaves the others where they
   are. A tap on the text of a verse starts again with that one alone, which
   is what a reader who is not collecting verses expects. A word in advanced
   mode belongs to the word popup, so it is left alone. */
document.addEventListener("click", e => {
  if (e.target.closest("#vbar")) return;
  const num = e.target.closest("sup.v");
  if (num) { if (num.dataset.v) toggleVerse(num.dataset.v); return; }
  if (adv() && e.target.closest("main .w")) { dropVerse(); return; }
  if (e.target.closest("#wpop, #vpop, #ctx, dialog, header, #tabbar")) return;
  const el = verseOf(e.target), r = el && verseRef(el);
  if (!r) { dropVerse(); return; }
  const k = vkey(r);
  if (vsel.length === 1 && vsel[0] === k) { dropVerse(); return; }   // tapping it again lets it go
  setSel([k]);
});
/* Enter and space on a focused number are handled with every other drawn-in
   button further down; these are the arrows that move between them. In a
   right-to-left chapter the next verse is to the left, where it is printed. */
document.addEventListener("keydown", e => {
  const num = e.target.closest && e.target.closest("sup.v");
  if (!num || e.altKey || e.ctrlKey || e.metaKey) return;
  const nums = [...document.querySelectorAll("main sup.v")], i = nums.indexOf(num);
  if (i < 0) return;
  const rtl = !!num.closest('[dir="rtl"]');
  const step = {ArrowDown: 1, ArrowUp: -1, ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1}[e.key];
  const j = step ? i + step : e.key === "Home" ? 0 : e.key === "End" ? nums.length - 1 : -1;
  if (j < 0 || j >= nums.length) return;
  e.preventDefault();
  num.tabIndex = -1; nums[j].tabIndex = 0; nums[j].focus();
});
document.addEventListener("keydown", e => { if (e.key === "Escape") dropVerse(); });
window.addEventListener("hashchange", dropVerse);

/* The system back button, when the page is in the Android app. The shell asks
   this first: it undoes what is on top - a held verse, a popup, a tray, a page
   drawn over a chapter - and says so. Chapter after chapter is not a stack to
   climb down on a phone, so from a plain chapter it says no, and the shell
   then offers to leave. */
window.androidBack = function(){
  if (vsel.length) { dropVerse(); return true; }
  if (wpop && !wpop.hidden) { hidePop(); return true; }
  if (vpop && !vpop.hidden) { hideRefs(); return true; }
  const c = document.getElementById("ctx");
  if (c && !c.hidden) { c.hidden = true; return true; }
  if (openName) { closeSheet(); return true; }
  const top = TRAIL[TRAIL.length - 1];
  if (TRAIL.length > 1 && top && !top.key.startsWith("read|")) { goBack(); return true; }
  return false;
};

/* ---------- the shell ----------
   A phone has room for the text and very little else, so everything that is
   not the text lives in a tray: navigation, search, the study views, and the
   display settings. The trays are <dialog> elements opened modally, which is
   where the scrim, the focus trap and Escape come from — none of that is worth
   writing by hand. Each tray's contents are drawn fresh every time it opens,
   so nothing in them can fall out of step with the page behind. */
const SHEETS = {nav: $("#navSheet"), search: $("#searchSheet"), tools: $("#toolsSheet"), set: $("#setSheet")};
const OPENERS = {nav: ["#tbBooks", "#title"], search: ["#tbSearch"], tools: ["#tbTools", "#toolsBtn"], set: ["#tbDisp", "#gear"]};
const mqNarrow = matchMedia("(max-width:760px)");
let openName = null, navBook = null, navPane = "chapters";
function openSheet(name){
  const d = SHEETS[name]; if (!d) return;
  if (openName === name) { closeSheet(); return; }
  if (openName) closeSheet();
  if (name === "nav") { const b = location.hash.slice(1).split("/")[0]; if (DATA[b]) navBook = b; navPane = "chapters"; }
  openName = name;
  drawSheet(name);
  const bd = d.querySelector(".bd"); if (bd) bd.scrollTop = 0;    // a tray opens at its top, wherever it was left
  if (d.showModal) d.showModal(); else d.setAttribute("open", "");
  d.style.transform = "";
  showChrome(); markOpeners();
  if (name === "search") { const q = $("#q"); if (q) { q.focus(); q.select(); } }
}
function closeSheet(){
  if (!openName) return;
  const d = SHEETS[openName]; openName = null;
  /* On a phone the search box in this tray has the keyboard up. Closing the
     tray without letting go of the box leaves the keyboard standing over half
     the screen, which reads as the tray not having closed at all. */
  const f = document.activeElement;
  if (f && f.blur && d.contains(f)) f.blur();
  if (d.close && d.open) d.close(); else d.removeAttribute("open");
  d.style.transform = "";                  // a drag that ended outside the tray must not leave it shifted
  markOpeners();
}
function markOpeners(){
  for (const n in OPENERS) for (const s of OPENERS[n]) {
    const el = $(s); if (el) el.setAttribute("aria-expanded", openName === n ? "true" : "false"); }
}
function drawSheet(n){ ({nav: drawNav, search: drawSearch, tools: drawTools, set: drawSettings})[n](); }
function redrawSheet(){ if (openName) drawSheet(openName); }
/* A tray is dragged down by its handle or its heading only. Starting a drag
   anywhere in the contents would fight the list the reader is scrolling. */
function dragToClose(d){
  let y0 = null, dy = 0;
  const down = e => { if (!mqNarrow.matches || e.target.closest("[data-close]")) return;
    y0 = e.clientY; dy = 0; d.style.transition = "none";
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (x) {} };
  const move = e => { if (y0 === null) return; dy = Math.max(0, e.clientY - y0); d.style.transform = `translateY(${dy}px)`; };
  const up = () => { if (y0 === null) return; y0 = null; d.style.transition = ""; d.style.transform = "";
    if (dy > 80) closeSheet(); };
  for (const el of d.querySelectorAll(".grab, .sh")) {
    el.addEventListener("pointerdown", down); el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  }
}
for (const n in SHEETS) {
  const d = SHEETS[n];
  d.addEventListener("close", () => { if (openName === n) { openName = null; markOpeners(); } });
  /* Outside the sheet is the scrim. It listens for the touch as well as the
     click: with the keyboard up, the first tap outside is spent dismissing it
     and the click never arrives, so the tray would need tapping twice. */
  d.addEventListener("click", e => { if (e.target === d) closeSheet(); });
  d.addEventListener("pointerdown", e => { if (e.target === d && e.pointerType === "touch") closeSheet(); });
  d.querySelector("[data-close]").onclick = closeSheet;
  dragToClose(d);
}
for (const n in OPENERS) for (const s of OPENERS[n]) { const el = $(s); if (el) el.onclick = () => openSheet(n); }
window.addEventListener("hashchange", closeSheet);
/* A modal <dialog> closes itself on Escape; the fallback for a browser without
   showModal() does not, and a tray that traps a keyboard would be worse than
   no tray at all. */
document.addEventListener("keydown", e => { if (e.key === "Escape" && openName) closeSheet(); });

/* The reference box and the search box are one element each, moved between the
   header and a tray as the screen changes, rather than copied into both — a
   second copy would need its own listeners and its own state to keep in step. */
function placeInputs(){
  const narrow = mqNarrow.matches;
  $(narrow ? "#refslot" : "#hdrSlot").appendChild($("#gotoWrap"));
  $(narrow ? "#qslot" : "#hdrSlot").appendChild($("#qWrap"));
}
mqNarrow.addEventListener("change", () => { closeSheet(); placeInputs(); measureBar(); });
placeInputs();
function focusSearch(){ if (mqNarrow.matches) openSheet("search"); else { showChrome(); $("#q").focus(); } }

/* ---------- the navigation tray ---------- */
/* A chosen row is marked three ways over — a tint, bold, and a tick — because
   one of them is colour, and colour on its own says nothing to some readers. */
const row = (attrs, name, note, on) => `<button type="button" ${attrs} class="${on ? "on" : ""}"${on ? ' aria-current="true"' : ""}>`
  + `<span class="nm">${name}</span><span class="ct">${note}</span>${on ? `<span class="tk" aria-hidden="true">&#10003;</span>` : ""}</button>`;
function langRows(){
  let h = "";
  for (const t of haveTargets)
    h += row(`data-lang="${t}"`, esc(TARGETS[t].native), esc(TARGETS[t].name), view !== "orig" && tl === t);
  return h + row(`data-lang="__orig"`, "Original", "Hebrew, Aramaic, Greek", view === "orig");
}
function drawNav(){
  const cur = location.hash.slice(1).split("/"), curBook = cur[0], curCh = cur[1];
  if (!navBook || !DATA[navBook]) navBook = DATA[curBook] ? curBook : srcBooks[0];
  $("#navSheetT").textContent = navPane === "books" ? "Choose a book" : disp(navBook);
  let h = `<div class="seg" role="group" aria-label="Books or chapters">
      <button type="button" data-pane="books" aria-pressed="${navPane === "books"}">Books</button>
      <button type="button" data-pane="chapters" aria-pressed="${navPane === "chapters"}">Chapters</button></div>`;
  if (navPane === "books") {
    h += `<div class="rowlist">`;
    let lastT = "";
    for (const bk of allBooks) {
      const t = ORDER[bk] <= 39 ? "Old Testament" : "New Testament";
      if (t !== lastT) { h += `<div class="shead">${t}</div>`; lastT = t; }
      const nch = DATA[bk] ? Object.keys(DATA[bk]).length : 0;
      if (!nch) { h += `<button type="button" class="missing" disabled><span class="nm">${disp(bk)}</span><span class="ct">not in the source texts</span></button>`; continue; }
      const ntr = Object.values(DATA[bk]).filter(c => c.tr && c.tr[tl]).length;
      const note = !ntr ? `${nch} chapters, original only` : ntr < nch ? `${ntr} of ${nch} translated` : `${nch} chapter${nch === 1 ? "" : "s"}`;
      h += row(`data-book="${bk}"`, disp(bk), note, bk === navBook);
    }
    h += `</div>`;
  } else {
    const chs = DATA[navBook] ? chapterList(navBook) : [];
    h += `<div class="shead">${esc(disp(navBook))} &middot; ${chs.length} chapter${chs.length === 1 ? "" : "s"}</div>`;
    h += `<div class="chgrid">` + chs.map(c =>
      `<a href="#${navBook}/${c}" class="${navBook === curBook && c == curCh ? "on" : ""} ${trOf(navBook, c)[tl] ? "" : "untr"}"${navBook === curBook && c == curCh ? ' aria-current="page"' : ""}>${c}</a>`).join("") + `</div>`;
    h += `<p class="hint">A dashed outline marks a chapter with no ${esc((TARGETS[tl] || {}).name || tl)} yet &mdash; the original is still there to read.</p>`;
    const nb = neighbours(navBook, curBook === navBook ? curCh : chs[0]);
    h += `<div class="shead">Move on</div><div class="rowlist">`;
    if (nb.prev) h += `<a href="#${nb.prev.b}/${nb.prev.c}">&#8592; ${disp(nb.prev.b)} ${nb.prev.c}</a>`;
    if (nb.next) h += `<a href="#${nb.next.b}/${nb.next.c}">${disp(nb.next.b)} ${nb.next.c} &#8594;</a>`;
    h += `</div>`;
  }
  h += `<div class="shead">Reading language</div><div class="rowlist">${langRows()}</div>`;
  const dyn = $("#navDyn");
  dyn.innerHTML = h;
  dyn.querySelectorAll("[data-pane]").forEach(el => el.onclick = () => { navPane = el.dataset.pane; drawNav(); });
  dyn.querySelectorAll("[data-book]").forEach(el => el.onclick = () => { navBook = el.dataset.book; navPane = "chapters"; drawNav(); $("#navBody").scrollTop = 0; });
  dyn.querySelectorAll("[data-lang]").forEach(el => el.onclick = () => {
    const v = el.dataset.lang;
    if (v === "__orig") setView("orig"); else setTl(v);
    drawNav();
  });
  dyn.querySelectorAll("a[href]").forEach(a => a.addEventListener("click", closeSheet));
}

/* ---------- the search tray ---------- */
function drawSearch(){
  $("#searchDyn").innerHTML =
    `<button type="button" class="primary" id="qGo">Show the results</button>
     <p class="hint">Searching the ${esc((TARGETS[tl] || {}).name || tl)} text; two letters is enough. The results are drawn behind this tray as you type.</p>
     <p class="hint">To jump straight to a reference instead, close this and tap the chapter name at the top: &ldquo;Genesis 2:7&rdquo;, &ldquo;1 Sam 3&rdquo;, &ldquo;Ps 23&rdquo;.</p>`;
  /* The tray goes away first. It used to close after the search had been set
     going, which meant that anything the search threw left the tray sitting
     over the page with no way back - the reader saw a search box that would
     not close and no results behind it. */
  $("#qGo").onclick = () => {
    const box = $("#q"), v = box ? box.value.trim() : "";
    closeSheet();
    if (v) search(v);
  };
}

/* ---------- the tools tray: every view this project builds, in one place ---------- */
function drawTools(){
  const cur = location.hash.slice(1).split("/"), book = cur[0], ch = cur[1];
  const d = DATA[book] && DATA[book][ch];
  const src = d && d.src, lxx = src && src._lxx, trs = (d && d.tr) || {};
  const avail = Object.keys(TARGETS).filter(t => trs[t]);
  const L = src ? LANGS[d.lang || "hbo"] : null;
  const B = (act, label, note, on, off) =>
    `<button type="button" data-act="${act}" aria-pressed="${!!on}"${off ? " disabled" : ""}>${label}<small>${note}</small></button>`;
  let h = "";
  if (d) {
    h += `<div class="shead">${esc(disp(book))} ${esc(ch)}</div><div class="tools">`;
    h += B("v:tr", "Reading", "the translation on its own", view === "tr", !avail.length);
    if (src) h += B("v:orig", esc(L.name), "the text it was made from", view === "orig", false);
    if (lxx) h += B("v:lxx", "Septuagint", "the old Greek of this chapter", view === "lxx", false);
    if (lxx) h += B("v:hl", "Hebrew &middot; Septuagint", "the two side by side", view === "hl", false);
    h += B("v:par", "Side by side", "original and translation, verse by verse", view === "par", !src || !avail.length);
    h += B("v:all", "Compare", "every language this chapter has", view === "all", (avail.length + (lxx ? 1 : 0)) < 2);
    h += B("inter", "Interlinear", "gloss and parsing under each word", inter, !src);
    h += B("v:themes", "Themes", "what this chapter is about", view === "themes", false);
    h += B("v:harm", "Parallels", "passages that share its wording", view === "harm", false);
    h += B("v:map", "Places", "where it happens, on a map", view === "map", false);
    h += B("v:chron", "Chronology", "the numbers it states", view === "chron", false);
    h += `</div>`;
  }
  h += `<div class="shead">Across the whole Bible</div><div class="tools">`;
  h += B("gs", "Grammar search", "words by their form", false, false);
  h += B("fields", "Fields of meaning", "this project&rsquo;s grouping of its words", false, false);
  h += B("themes", "All themes", "gathered out of the chapters", false, false);
  h += B("lexicon", "Our lexicon", "entries written from the text", false, false);
  h += B("lexemes", "Lexeme inventory", "dictionary words grown from the forms", false, false);
  h += B("args", "What each book argues", "a book&rsquo;s sections and line of thought", false, false);
  h += B("sources", "Sources and licenses", "where every layer came from", false, false);
  h += `</div><p class="hint">Everything here is a reading built on the text, and each page says what it was built from. Basic mode puts all of it away.</p>`;
  const dyn = $("#toolsDyn");
  dyn.innerHTML = h;
  dyn.querySelectorAll("[data-act]").forEach(el => el.onclick = () => {
    const a = el.dataset.act;
    closeSheet();
    if (a.startsWith("v:")) setView(a.slice(2));
    else if (a === "inter") toggleInter();
    else if (a === "gs") gsOpen();
    else if (a === "fields") browseFields();
    else if (a === "themes") browseThemes();
    else if (a === "lexicon") browseLexicon();
    else if (a === "lexemes") browseLexemes();
    else if (a === "args") browseArguments();
    else if (a === "sources") $("#credits").scrollIntoView({behavior: "smooth", block: "start"});
  });
}

/* ---------- the display tray ---------- */
function drawSettings(){
  let h = READER_ONLY ? "" : `<div class="shead">How much of the reader you want</div>
    <div class="seg" role="group" aria-label="Mode">
      <button type="button" data-mode="basic" aria-pressed="${!adv()}">Just read</button>
      <button type="button" data-mode="advanced" aria-pressed="${adv()}">Everything</button></div>
    <p class="hint">${adv() ? "Every layer this project has built is switched on: the word tags, the lexicon, the themes, the maps and the rest."
                            : "The book and nothing else: a chapter, a language, the size of the type. Tapping a word does nothing."}</p>`;
  if (READER_ONLY) h = "";
  h += `<div class="shead">Skin</div><div class="skins" role="group" aria-label="Skin">`;
  for (const [id, name, paper, ink] of SKINS) {
    const on = skin === id;
    const sw = id === "auto"
      ? `background:linear-gradient(135deg,#faf8f4 0 50%,#181614 50% 100%)`
      : `background:linear-gradient(135deg,${paper} 0 55%,${ink} 55% 100%)`;
    h += `<button type="button" data-skin="${id}" aria-pressed="${on}"><span class="sw" style="${sw}"></span>${name}${on ? `<span class="tick" aria-hidden="true">&#10003;</span>` : ""}</button>`;
  }
  h += `</div>`;
  h += `<div class="shead">Text size</div><div class="seg" role="group" aria-label="Text size">
      <button type="button" data-fs="-1"${fs <= FS_MIN ? " disabled" : ""} aria-label="Smaller text">A&minus;</button>
      <span class="val" role="status">${fs} px</span>
      <button type="button" data-fs="1"${fs >= FS_MAX ? " disabled" : ""} aria-label="Larger text">A+</button></div>
    <p class="hint">Pinching the page magnifies it as well, for as long as you need it; the reader offers a way back to normal size while it is magnified.</p>`;
  h += `<div class="shead">Line spacing</div><div class="seg" role="group" aria-label="Line spacing">`
    + SPACING.map(([v, n]) => `<button type="button" data-lh="${v}" aria-pressed="${Math.abs(lh - v) < .001}">${n}</button>`).join("") + `</div>`;
  h += `<div class="shead">Reading language</div><div class="rowlist">${langRows()}</div>`;
  h += `<div class="shead">Read aloud</div><p class="hint">${PHONE
      ? "Tap a verse and choose Listen. The voices are the phone\u2019s own, so whichever languages it has installed are the ones it can read; Hebrew and Greek are read with modern voices."
      : ("speechSynthesis" in window)
      ? "Tap a verse and choose Listen, or press and hold it (right-click) for the same in its own language."
      : "This browser has no speech voices, so nothing can be read aloud here."}</p>`;
  if (speechFor(tl) !== "no") {
    h += `<div class="shead">Voice speed</div><div class="seg" role="group" aria-label="Voice speed">`
      + SPEEDS.map(([v, n]) => `<button type="button" data-rate="${v}" aria-pressed="${Math.abs(VOICE.rate - v) < .001}">${n}</button>`).join("")
      + `</div>`;
    h += `<div class="shead">Voice pitch</div><div class="seg" role="group" aria-label="Voice pitch">`
      + PITCHES.map(([v, n]) => `<button type="button" data-pitch="${v}" aria-pressed="${Math.abs(VOICE.pitch - v) < .001}">${n}</button>`).join("")
      + `</div><p class="hint"><button type="button" id="voiceTry" class="try">Hear it</button> a verse at this setting.</p>`;
    const vs = voicesFor(tl), pickName = chosenVoice(tl);
    if (vs.length > 1) {
      h += `<div class="shead">Which voice</div><div class="rowlist">`
        + row('data-voice=""', "Best this phone has", "chosen for quality", !pickName)
        + vs.map((v, i) => row(`data-voice="${attr(v.name)}"`, `Voice ${i + 1}`,
            `${v.quality >= 400 ? "very natural" : v.quality >= 300 ? "natural" : "plain"} \u00b7 ${esc(v.locale)}`,
            pickName === v.name)).join("")
        + `</div>`;
    }
    h += `<p class="hint">The voices belong to the phone, not to this app. A flat, clipped voice is the small
      one Android ships with: more natural voices are a free download in the phone's own settings \u2014
      Settings \u203a Accessibility \u203a Text-to-speech output \u203a your engine \u203a Install voice data,
      where the larger voices for a language can be added. They then appear here.</p>`;
  }
  if (PHONE) h += `<div class="shead">Pass it on</div><div class="rowlist">`
    + row('id="setShareApp"', "Share this app", "send a copy to another phone", false)
    + `</div><p class="hint">The whole Bible goes with it: no shop, no account, and nothing to download at the other end.</p>`;
  h += `<div class="shead">About the text</div><div class="rowlist"><button type="button" id="setSrc"><span class="nm">Sources and licenses</span><span class="ct">what each layer came from</span></button></div>`;
  const dyn = $("#setDyn");
  dyn.innerHTML = h;
  dyn.querySelectorAll("[data-mode]").forEach(el => el.onclick = () => setMode(el.dataset.mode));
  dyn.querySelectorAll("[data-skin]").forEach(el => el.onclick = () => setSkin(el.dataset.skin));
  dyn.querySelectorAll("[data-fs]").forEach(el => el.onclick = () => fsStep(+el.dataset.fs));
  dyn.querySelectorAll("[data-lh]").forEach(el => el.onclick = () => setLh(+el.dataset.lh));
  dyn.querySelectorAll("[data-rate]").forEach(el => el.onclick = () => { setVoice("rate", +el.dataset.rate); tryVoice(); });
  dyn.querySelectorAll("[data-pitch]").forEach(el => el.onclick = () => { setVoice("pitch", +el.dataset.pitch); tryVoice(); });
  dyn.querySelectorAll("[data-voice]").forEach(el => el.onclick = () => { setChosenVoice(tl, el.dataset.voice); tryVoice(); });
  const tryBtn = $("#voiceTry");
  if (tryBtn) tryBtn.onclick = tryVoice;
  dyn.querySelectorAll("[data-lang]").forEach(el => el.onclick = () => {
    const v = el.dataset.lang;
    if (v === "__orig") setView("orig"); else setTl(v);
    drawSettings();
  });
  $("#setSrc").onclick = () => { closeSheet(); $("#credits").scrollIntoView({behavior: "smooth", block: "start"}); };
  const shareApp = $("#setShareApp");
  if (shareApp) shareApp.onclick = () => { closeSheet(); if (PHONE && PHONE.shareApp) PHONE.shareApp(); };
}

/* A setting is worth hearing rather than reading: the sample is a verse of the
   text itself, in the language on screen, so the speed is judged on the thing
   it will be used for. */
function tryVoice(){
  const h = location.hash.slice(1).split("/"), book = DATA[h[0]] ? h[0] : srcBooks[0];
  if (!DATA[book]) return;                 // nothing built into this copy to read from
  const ch = DATA[book][h[1]] ? h[1] : Object.keys(DATA[book])[0];
  const r = {book, ch: +ch, v: 1}, c = verseContent(r);
  if (c) speakVerse(c.txt, c.lang);
}

/* ---------- the title in the bar, and the bars getting out of the way ---------- */
function setTitle(main, sub){
  $("#titleMain").textContent = main;
  $("#titleSub").textContent = sub || "";
  document.title = main ? main + " — eBible" : "eBible Translation";
}
function measureBar(){
  document.documentElement.style.setProperty("--barH", ($("header").offsetHeight || 56) + "px");
}
addEventListener("resize", measureBar); measureBar();
/* Reading is what the page is for. Once the reader is moving down a chapter
   the bars slide away, and the first flick back up brings them back; they are
   sticky, so nothing under them moves when they go. */
let lastY = 0, chromeOff = false;
function showChrome(){ if (chromeOff) { chromeOff = false; document.documentElement.classList.remove("chrome-off"); } }
addEventListener("scroll", () => {
  const y = Math.max(0, window.pageYOffset), d = y - lastY;
  if (Math.abs(d) < 8) return;
  lastY = y;
  if (openName) return;
  if (d > 0 && y > 120) { if (!chromeOff) { chromeOff = true; document.documentElement.classList.add("chrome-off"); } }
  else showChrome();
}, {passive: true});
addEventListener("focusin", e => { if (e.target.closest && e.target.closest("header, #tabbar")) showChrome(); });

/* ---------- the magnifier ----------
   Pinching is the zoom of a reader who cannot see the text at its set size, so
   the page never forbids it. Nothing in the platform releases a pinch again,
   which leaves a magnified reader stranded; clamping the viewport for a single
   frame makes the browser snap back, and the clamp is lifted immediately after,
   so the page is never left unzoomable. */
const vvp = window.visualViewport;
function zoomWatch(){
  const chip = $("#zoomchip"), s = (vvp && vvp.scale) || 1;
  if (s > 1.05) {
    $("#zoomlvl").textContent = "Magnified " + s.toFixed(1) + "×";
    chip.hidden = false;
    chip.style.left = (vvp.offsetLeft + vvp.width / 2) + "px";
    chip.style.top = (vvp.offsetTop + vvp.height - chip.offsetHeight / s - 12) + "px";
    chip.style.bottom = "auto";
    chip.style.transform = `translateX(-50%) scale(${1 / s})`;
    chip.style.transformOrigin = "bottom center";
  } else { chip.hidden = true; chip.style.top = ""; chip.style.bottom = ""; chip.style.left = ""; chip.style.transform = ""; }
}
if (vvp) { vvp.addEventListener("resize", zoomWatch); vvp.addEventListener("scroll", zoomWatch); }
$("#zoomreset").onclick = () => {
  const m = document.querySelector('meta[name="viewport"]'), had = m.getAttribute("content");
  m.setAttribute("content", had + ", maximum-scale=1");
  setTimeout(() => { m.setAttribute("content", had); zoomWatch(); }, 80);
  setTimeout(() => { if (vvp && vvp.scale > 1.05) $("#zoomlvl").textContent = "Still magnified — pinch inwards to go back"; }, 500);
};

/* In the app there is no console to open: a script error would simply be a
   button that does nothing, and the reader would have no way to say what went
   wrong beyond "it does not work". So every error the page throws is shown,
   once, where it can be read and repeated back. */
addEventListener("error", e => {
  const where = e.filename ? ` (line ${e.lineno})` : "";
  toast(`Something went wrong: ${e.message || e.type}${where}. The rest of the reader is unaffected.`);
});
addEventListener("unhandledrejection", e => {
  const r = e.reason;
  toast(`Something went wrong: ${(r && (r.message || r)) || "a failed operation"}. The rest of the reader is unaffected.`);
});

/* A file that fails to load should say so rather than leave an empty view. */
let toastT;
function toast(msg){
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  // Never on top of the magnifier's way back, and never on top of the verse
  // bar - which is where most of these messages are asked for in the first
  // place, so a reader would watch the bar disappear behind the answer.
  const lift = ($("#zoomchip").hidden ? 0 : 54) + (vbar.hidden ? 0 : vbar.offsetHeight + 10);
  t.style.marginBottom = lift ? lift + "px" : "";
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 7000);
}

/* Two things every view needs and none of them should have to remember: its
   links reachable from a keyboard — most of the reader's links are <a> with no
   href, drawn into the page, which a keyboard cannot touch — and its heading
   repeated in the bar, where it is the way back into the navigation tray. */
const CLICKABLE = "a:not([href]):not([tabindex]):not(.off), .hit:not([tabindex]), .r[onclick]:not([tabindex]),"
  + " .thm .t b:not([tabindex]), .chron .row b:not([tabindex]), .arg .sec b:not([tabindex]), .harm .lab[onclick]:not([tabindex])";
function reachable(root){
  for (const el of root.querySelectorAll(CLICKABLE)) { el.tabIndex = 0; el.setAttribute("role", "button"); }
}
new MutationObserver(() => {
  const m = $("#main");
  reachable(m);
  syncVerseMarks();                      // a redrawn chapter comes back with its held verses still held
  rovingVerses();
  refreshVbar();
  const h = m.querySelector("h2");
  if (h) {
    const c = h.cloneNode(true), sub = h.querySelector(".lang");
    c.querySelectorAll(".lang").forEach(x => x.remove());
    setTitle(c.textContent.trim(), sub ? sub.textContent.trim() : "");
  }
}).observe($("#main"), {childList: true, subtree: true});
document.addEventListener("keydown", e => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches('[role="button"][tabindex="0"]')) {
    e.preventDefault(); e.target.click();
  }
});

/* ---------- routing ---------- */
function route() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h) { const b = booksWith(tl)[0] || srcBooks[0]; if (b) location.hash = `#${b}/1`; return; }
  const [book, ch, v] = h.split("/");
  $("#q").value = "";
  const p = readPlace();
  trailPush(p.key, p.run);
  renderChapter(book, ch, v ? +v : null);
}

/* ---------- back: the trail of what has been looked at ---------- */
/* A chapter has an address in the hash, but a theme, a lexicon entry, a field
   of meaning or a list of occurrences does not: they are drawn straight into
   the page. Without a trail of its own the reader has no way back out of
   them, and a mistaken click is a dead end. Every page is remembered here,
   however it was reached, and the arrow in the header walks back through
   them. */
const TRAIL = [];
function trailPush(key, run){
  const top = TRAIL[TRAIL.length - 1];
  if (top && top.key === key) { top.run = run; return; }          // the same page again is not a step
  if (top && key.startsWith("search|") && top.key.startsWith("search|")) TRAIL[TRAIL.length - 1] = {key, run};
  else TRAIL.push({key, run});                                    // a search being typed stays one place
  if (TRAIL.length > 300) TRAIL.shift();
  backSync();
}
function backSync(){ const b = $("#back"); if (b) b.disabled = TRAIL.length < 2; }
/* An open tray is the first thing back should undo — it is what the reader is
   looking at. The Android shell asks canGoBack() before it will leave the app,
   so the two have to agree about what counts as somewhere to go back to. */
function canGoBack(){ return !!openName || TRAIL.length > 1; }
function goBack(){
  if (openName) { closeSheet(); return; }
  if (TRAIL.length < 2) return;
  TRAIL.pop();                                                    // where we are now
  const p = TRAIL[TRAIL.length - 1];
  backSync();
  hidePop(); hideRefs();
  p.run();
}
function readPlace(){                    // a chapter, as it was being read: the reference, the view, the language
  const h = location.hash, v = view, t = tl;
  return {key: `read|${h}|${v}|${t}`, run: () => {
    view = v; localStorage.setItem("view", v);
    if (t !== tl) { tl = t; localStorage.setItem("tl", t); const s = $("#tlSel"); if (s) s.value = t; }
    if (location.hash === h) route(); else location.hash = h;     // an unchanged hash fires no event
  }};
}
for (const name of ["browseThemes", "showTheme", "browseArguments", "showArgument", "browseLexicon", "showLexEntry",
                    "browseLexemes", "showLexeme", "searchSource", "browseFields", "showDomain", "showConc",
                    "gsOpen", "search"]) {
  const fn = window[name];
  if (typeof fn !== "function") continue;
  window[name] = function(...a){ trailPush(name + "|" + a.join("|"), () => fn(...a)); return fn(...a); };
}
$("#back").onclick = goBack;
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
/* Enter is done searching: on a phone that means putting the tray away and
   letting the reader see the hits it has been drawing behind it. */
$("#q").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  clearTimeout(deb);
  const val = e.target.value.trim();
  if (openName === "search") closeSheet();          // away first, for the reason in drawSearch
  if (val) search(val);
});
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.defaultPrevented) return;              // the arrows walking the verse numbers are not asking for a chapter
  if (e.key === "Backspace" || (e.altKey && e.key === "ArrowLeft")) { e.preventDefault(); goBack(); return; }
  if (openName) return;                        // the arrows belong to the tray while one is open
  const h = location.hash.slice(1).split("/");
  if (h.length < 2 || !DATA[h[0]]) return;
  const {prev, next} = neighbours(h[0], h[1]);
  if (e.key === "ArrowLeft" && prev) goto(`#${prev.b}/${prev.c}`);
  if (e.key === "ArrowRight" && next) goto(`#${next.b}/${next.c}`);
});
window.addEventListener("hashchange", route);
$("#sources").onclick = () => $("#credits").scrollIntoView({behavior:"smooth", block:"start"});
/* The gear is for a phone, and only while there is something to read under it. */
const quick = $("#quick");
quick.onclick = () => openSheet("set");
function quickShow(){ quick.hidden = !mqNarrow.matches; }
mqNarrow.addEventListener("change", quickShow); quickShow();
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
    import argparse
    ap = argparse.ArgumentParser(description="Build the offline reader page.")
    ap.add_argument("--reader-only", action="store_true",
                    help="the text alone, always in basic mode: the page for the Android reader APK, "
                         "which ships without the study layers in morph/")
    ap.add_argument("--out", default=str(SITE), help="folder to write index.html into (default: site/)")
    ap.add_argument("--complete-only", action="store_true",
                    help="carry only the languages the whole Bible has been translated into; "
                         "what is shipped (the APKs) should not offer a language with books missing")
    a = ap.parse_args()
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
    counts, short = {}, {}
    for code in TARGETS:
        for f in sorted((OUT_ROOT / code / "json").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            key, ch = slug(d["book"]), str(d["chapter"])
            entry = data.setdefault(key, {}).setdefault(ch, {"src": None, "lang": None, "tr": {}})
            entry["tr"][code] = {"verses": d["verses"], "notes": d.get("notes", "")}
            # A chapter counts as translated when the verses are actually in it.
            # A run that failed - the model answered in the wrong language, or
            # echoed the prompt back - still leaves a file behind, and counting
            # files once let a Chinese Bible with no Psalm 119 in it call
            # itself complete. The source is the authority on what is missing.
            want = {v for v in (entry["src"] or {}) if not v.startswith("_")}
            if want and want - set(d["verses"]):
                short.setdefault(code, []).append(f"{d['book']} {ch}")
            else:
                counts[code] = counts.get(code, 0) + 1
    # A language still being translated is fine to watch here, on the machine
    # doing the translating, where the chapter list shows what is done. It is
    # not fine to hand someone a Bible whose Psalms stop at 39, so a build for
    # shipping keeps only the languages that have every chapter.
    targets = TARGETS
    if a.complete_only:
        whole = sum(len(v) for v in data.values())
        targets = {c: t for c, t in TARGETS.items() if counts.get(c, 0) >= whole}
        for chapters in data.values():
            for entry in chapters.values():
                entry["tr"] = {c: v for c, v in entry["tr"].items() if c in targets}
        dropped = {c: n for c, n in counts.items() if c not in targets}
        counts = {c: n for c, n in counts.items() if c in targets}
        if dropped:
            print("left out, still being translated: "
                  + ", ".join(f"{c} ({n}/{whole})" for c, n in sorted(dropped.items())))
        for code in sorted(dropped):
            gaps = short.get(code)
            if gaps:                       # a language held back by a handful of failures, not by its progress
                print(f"  {code}: {len(gaps)} chapter(s) have verses missing and do not count - "
                      + ", ".join(gaps[:6]) + (" ..." if len(gaps) > 6 else "")
                      + f"; re-run them (scripts/verify.py --lang {code} shows what is gone)")
        if not counts:
            print("WARNING: no language is complete, so this page carries the original text alone")
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    page = (PAGE
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__ORDER__", json.dumps(ORDER))
            .replace("__LANGS__", json.dumps({**LANGS, "mixed": MIXED}))
            .replace("__TARGETS__", json.dumps({c: {"name": t["name"], "native": t["native"], "dir": t.get("dir", "ltr")} for c, t in targets.items()}, ensure_ascii=False))
            .replace("__ABBREV__", json.dumps(
                {k: v.replace(" ", "_") for k, v in ABBREV.items()}))
            .replace("__READER_ONLY__", "true" if a.reader_only else "false")
            .replace("__BUILT__", __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__READALOUD_CSS__", RA.CSS)
            .replace("__READALOUD_JS__", RA.js('main', '.par .o, .par .e, .cmp .row .txt, p.ov, .poetry, .vv span, .hit, .notes')))
    out = out_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    nch = sum(len(v) for v in data.values())
    tr = ", ".join(f"{c}={n}" for c, n in counts.items()) or "none"
    print(f"site built{' (reader only)' if a.reader_only else ''}: {out} ({len(data)} books, {nch} chapters of original text; "
          f"translated chapters: {tr}; {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
