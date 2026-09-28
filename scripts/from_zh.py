#!/usr/bin/env python3
"""A Chinese language made from our Mandarin: word replacement first, the model second.

The engine behind scripts/hakka_from_zh.py (Hakka, hak) and
scripts/taiwanese_from_zh.py (Taiwanese Hokkien, nan); each of those names
its language and hands over to main() here.

    python scripts/hakka_from_zh.py John 1                 # draft by table, then the model mends it
    python scripts/hakka_from_zh.py John 1 --table-only    # the replacement alone, no model
    python scripts/hakka_from_zh.py John 1 --show          # print Mandarin, draft and result side by side
    python scripts/hakka_from_zh.py John --force           # every chapter of John, over what is there
    python scripts/hakka_from_zh.py --all                  # the whole Bible, New Testament first (resumes)
    (the same for taiwanese_from_zh.py)

Asked to translate into Hakka from the Greek, qwen3:32b wrote Cantonese and
Mandarin with hardly a Hakka word in it, and qwen3.5 wrote Hakka still
threaded with Mandarin. Yet written Hakka and Taiwanese share most of their
words with Mandarin - 道, 光, 生命, 恩典 and every name are the same - and
part mostly in a few hundred common ones: the pronouns, the copula, negation,
the question words, the particles, a stock of everyday verbs and nouns. So
the language is made from the Mandarin translation, which is finished and
checked, rather than from the source again:

  1. The Mandarin is cut into words (jieba) and put into traditional
     characters (OpenCC, s2tw).
  2. Each word found in targets/<lang>/replace.json - the common words,
     chosen by hand - becomes its word in the language. A word not there but
     in the table drawn from the Ministry of Education's dictionary of the
     language becomes the dictionary's word for it: the dictionary glosses
     each of its words in Mandarin, a Mandarin word that is not itself a word
     of the language is replaced, and where several words share a gloss the
     one its example sentences pair with that Mandarin word most often is
     taken.
  3. Patterns the words cannot do alone (replace.json "rules"): the
     characters that are Mandarin wherever they stand, inside words the
     segmenter kept whole; 告訴你; a count of days; a question's 嗎; the
     quotation marks.
  4. The model mends what is left - aspect (了, 著), 把 and 跟, the odd
     Mandarin word or word order - in a draft that is mostly the language
     already. It sees the draft alone: shown the Mandarin too, it copied the
     Mandarin back in. And each verse it returns is checked against its
     draft, and the draft kept if the model's has more Mandarin in it or is
     much shorter or longer, so the model can only move a verse forward.

What the table leaves is counted before and after the model (Mandarin-only
words per hundred characters), so a chapter says how much it moved.

The MOE dictionaries are CC BY-ND 3.0 TW. They are fetched into sources/
(not in git) and the tables built from them are kept there too; only the
hand-made tables are committed.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                  # noqa: E402
from books import BOOKS, slug          # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)   # a job log shows each chapter as it lands

ROOT = T.ROOT
CJK = re.compile(r"^[一-鿿\U00020000-\U0003ffff]{2,4}$")
GPU_LAYERS = None      # --gpu-layers: hold only this many of the model's layers on the GPU, to share it
SHARE_LAYERS = 24      # what a Karen voice training leaves room for: qwen3.5 has 40 layers of ~0.55 GB
_train = {"at": 0.0, "on": False}


def training_voice():
    """Whether a voice is training on the GPU (NGAW KAREN TTS/train_mms.py
    --train). It holds ~8 GB; qwen3.5 whole wants ~25, and the two together
    on the 5090 would leave the training nothing to grow into - so while one
    runs the model keeps only part of itself on the GPU. Asked once a minute."""
    if time.time() - _train["at"] > 60:
        on = False
        try:
            import psutil
            for p in psutil.process_iter(["name", "cmdline"]):
                cmd = " ".join(p.info["cmdline"] or ())
                if "train_mms.py" in cmd and "--train" in cmd:
                    on = True
                    break
        except Exception:                      # noqa: BLE001 - no psutil, or a process gone mid-look
            pass
        _train.update(at=time.time(), on=on)
    return _train["on"]


def gpu_layers():
    if GPU_LAYERS is not None:
        return GPU_LAYERS
    return SHARE_LAYERS if training_voice() else None


# ------------------------------------------------------------------ the dictionaries
def scored_table(candidates, pairs):
    """{Mandarin word: its word in the language} from the gloss candidates,
    choosing among several by how often the example pairs (language,
    Mandarin) carry both. A lone candidate is safe; among several, only one
    the examples bear out is taken."""
    by_char = [defaultdict(set), defaultdict(set)]
    for i, pair in enumerate(pairs):
        for side, text in enumerate(pair):
            for c in set(text):
                by_char[side][c].add(i)

    def holding(word, side):
        ids = set.intersection(*(by_char[side].get(c, set()) for c in word))
        return {i for i in ids if word in pairs[i][side]}

    table = {}
    for man, heads in candidates.items():
        with_man = holding(man, 1)
        seen = [(h, len(with_man & holding(h, 0))) for h in heads]
        best, score = max(seen, key=lambda s: (s[1], -len(s[0])))
        if score or len(heads) == 1:
            table[man] = best
    return table


def hakka_pairs(examples):
    """(Hakka, Mandarin) sentence pairs from the Hakka dictionary's example
    column: '例：<Hakka>(<Mandarin>)' or '<Hakka>\\n<Mandarin>'."""
    out = []
    for e in examples:
        for line in re.split(r"\n(?=例)", str(e)):
            line = re.sub(r"^例[：:]", "", line.strip())
            m = re.match(r"(.+?)[(（](.+)[)）]\s*$", line, re.S)
            if m:
                out.append((m.group(1), m.group(2)))
            elif "\n" in line:
                hak, man = line.split("\n", 1)
                out.append((hak, man))
    return out


def build_hakka_table(cfg):
    """From the MOE Taiwan Hakka dictionary, Sixian (an ODS spreadsheet:
    headword, gloss, examples with their Mandarin in brackets)."""
    import pandas as pd
    ods = cfg["dict_file"]
    if not ods.exists():
        ods.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetching the MOE Sixian dictionary -> {ods.relative_to(ROOT)}")
        urllib.request.urlretrieve(cfg["dict_url"], ods)
    df = pd.read_excel(ods, engine="odf").fillna("")
    words = set()
    for _, r in df.iterrows():
        for w in re.split(r"[　\s、]+", f"{r['詞目']}　{r['相似詞']}"):
            if w.strip():
                words.add(w.strip())
    candidates = defaultdict(set)
    for _, r in df.iterrows():
        head = str(r["詞目"]).strip()
        gloss = re.split(r"[。；;]", str(r["釋義"]).strip())[0]
        for man in re.split(r"[、，,]", gloss):
            man = man.strip()
            if CJK.match(man) and CJK.match(head) and man != head and man not in words:
                candidates[man].add(head)
    return scored_table(candidates, hakka_pairs(df["例句"])), len(df)


def taigi_entries(cfg):
    """The MOE dictionary of Taiwan Southern Min (臺灣閩南語常用詞辭典) as g0v
    keeps it: a list of {title, heteronyms: [{trs, synonyms, definitions:
    [{def, example: ['￹漢字￺Tâi-lô￻華語']}]}]}."""
    f = cfg["dict_file"]
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetching the MOE Taiwanese dictionary -> {f.relative_to(ROOT)}")
        urllib.request.urlretrieve(cfg["dict_url"], f)
    return json.loads(f.read_text(encoding="utf-8"))


def taigi_examples(entries):
    """(漢字, Tâi-lô, 華語) for every example sentence in the dictionary."""
    out = []
    for e in entries:
        for h in e.get("heteronyms", []):
            for d in h.get("definitions", []):
                for ex in d.get("example", []):
                    m = re.match(r"￹(.*?)￺(.*?)￻(.*)", ex, re.S)
                    if m:
                        out.append(tuple(s.strip() for s in m.groups()))
    return out


def build_taigi_table(cfg):
    entries = taigi_entries(cfg)
    words = set()
    for e in entries:
        words.add(e["title"])
        for h in e.get("heteronyms", []):
            for s in re.split(r"[,、，]", h.get("synonyms", "") or ""):
                if s.strip():
                    words.add(s.strip())
    candidates = defaultdict(set)
    for e in entries:
        head = e["title"]
        for h in e.get("heteronyms", []):
            for d in h.get("definitions", [])[:1]:              # the first sense: the common one
                gloss = re.split(r"[。；;]", (d.get("def") or "").strip())[0]
                for man in re.split(r"[、，,]", gloss):
                    man = man.strip()
                    if CJK.match(man) and CJK.match(head) and man != head and man not in words:
                        candidates[man].add(head)
    pairs = [(han, man) for han, _, man in taigi_examples(entries)]
    return scored_table(candidates, pairs), len(entries)


LANGS = {
    "hak": {
        "name": "Hakka", "native": "客語", "variety": "Taiwanese Hakka, Sixian (四縣腔)",
        "script": "hakka_from_zh.py",
        "dict_file": ROOT / "sources" / "hakka-dict" / "sixian.ods",
        "dict_url": ("https://hakkadict.moe.edu.tw/static/resource/%E5%AE%A2%E8%AA%9E%E8%B3%87%E6%BA%90%E4%B8%8B%E8%BC%89/"
                     "%E6%9C%AC%E8%BE%AD%E5%85%B8%E7%9A%84%E6%96%87%E5%AD%97/"
                     "%E5%9B%9B%E7%B8%A3%E8%85%94%E8%A9%9E%E6%A2%9D%E8%A9%9E%E7%9B%AE%E6%96%87%E5%AD%97.ods"),
        "table_file": ROOT / "sources" / "hakka-dict" / "moe_table.json",
        "table_source": "MOE 臺灣客語辭典, 四縣腔 (CC BY-ND 3.0 TW)",
        "build": build_hakka_table,
        # Words that are Mandarin and not Hakka, to measure what is left.
        "mandarin": ["我們", "他們", "你們", "的", "是", "不", "沒有", "沒", "什麼", "甚麼", "誰", "嗎", "說", "這裡",
                     "那裡", "哪裡", "很", "給", "和", "知道", "看見", "孩子", "兒子", "吃", "喝", "這樣", "那樣", "怎麼",
                     "現在", "我", "他", "她", "們", "要", "可以", "時候", "一起", "告訴", "個", "吧", "把", "首先", "大約",
                     "看哪", "這麼", "那麼", "怎麼", "還要"],
        "mend": (
            "The draft was made from a Mandarin translation by replacing words, so most of it is already Hakka: "
            "𠊎, 佢, 𠊎兜, 你兜, 佢兜, 个, 係, 毋, 無, 麼个, 麼人, 摎, 分, 講, 看著, 該位 are all right and must stay. "
            "What is left is Mandarin the replacement could not see. Mend that, and only that:\n"
            "- aspect and particles: a completed action's 了 -> 忒 or 矣 (or nothing); 著/着 of a lasting state -> 等 "
            "or 緊; the adverb's 地 goes; 吧 -> 啦 or 哪; 呢 may stay\n"
            "- 把 X + verb -> 摎 X + verb; 跟 meaning 'with' -> 摎 or 同 (跟從/跟隨 'follow' stay)\n"
            "- Mandarin words with a Hakka one: 還能 -> 還做得, 首先 -> 先, 大約 -> 差毋多, 看哪 -> 你看, "
            "這麼 -> 恁, 都 stays\n"
            "- Mandarin word order where Hakka differs (給他X -> 分佢X; 對他說 -> 同佢講 is better but 對佢講 may stay)\n"
            "- a 神 still in the draft was left because the verse also speaks of other gods: the God of Israel "
            "-> 上帝; a god or the gods of the nations -> 神 (神明 where it reads better)\n"
            "Do not turn anything back into Mandarin: never write 我, 他, 們, 的, 是, 不 (where 毋 goes), 沒有, 說, "
            "誰, 什麼, 看見."),
        "example": "[1] 太初有道，道摎上帝共下，道就係上帝。",
    },
    "nan": {
        "name": "Taiwanese", "native": "台語", "variety": "Taiwanese Hokkien (臺灣閩南語, 台語)",
        "script": "taiwanese_from_zh.py",
        "dict_file": ROOT / "sources" / "taigi-dict" / "dict-twblg.json",
        "dict_url": "https://raw.githubusercontent.com/g0v/moedict-data-twblg/master/dict-twblg.json",
        "table_file": ROOT / "sources" / "taigi-dict" / "moe_table.json",
        "table_source": "MOE 臺灣閩南語常用詞辭典 (CC BY-ND 3.0 TW), via g0v/moedict-data-twblg",
        "build": build_taigi_table,
        # Mandarin and not Taiwanese. 的, 是, 我, 你 and 不 in fixed words are
        # Taiwanese too, so they are not counted.
        "mandarin": ["我們", "他們", "你們", "他", "她", "們", "沒有", "沒", "什麼", "甚麼", "誰", "嗎", "說", "這裡",
                     "那裡", "哪裡", "很", "給", "和", "知道", "看見", "孩子", "兒子", "吃", "喝", "這樣", "那樣", "怎麼",
                     "現在", "要", "可以", "時候", "一起", "告訴", "個", "吧", "把", "首先", "看哪", "這麼", "那麼", "都",
                     "還要", "東西", "事情", "地方"],
        "mend": (
            "The draft was made from a Mandarin translation by replacing words, so most of it is already Taiwanese: "
            "伊, 𪜶, 阮, 咱, 恁, 的, 是, 毋, 無, 袂, 啥物, 啥人, 佮, 予, 講, 看著, 遮, 遐, 佇, 攏, 欲, 真, 知影 are "
            "all right and must stay. What is left is Mandarin the replacement could not see. Mend that, and only "
            "that:\n"
            "- aspect and particles: a completed action's 了 -> 矣 at the end of a clause, or 了 (liáu) for 'finish'; "
            "著/着 of a lasting or ongoing state -> 咧; the adverb's 地 goes; 吧 -> 啦; 呢 -> 咧 or 呢\n"
            "- 把 X + verb -> 共 X + verb; 跟 meaning 'with' -> 佮, 跟 meaning 'follow' -> 綴 (跟從/跟隨 -> 綴)\n"
            "- 我們 was made 阮 (we, not you): where the listener is included it is 咱\n"
            "- Mandarin words with a Taiwanese one: 還能 -> 猶閣會當, 首先 -> 先, 看哪 -> 恁看, 這麼 -> 遮爾, "
            "東西 -> 物件, 事情 -> 代誌, 地方 -> 所在, 都 -> 攏\n"
            "- Mandarin word order where Taiwanese differs\n"
            "- a 神 still in the draft was left because the verse also speaks of other gods: the God of Israel "
            "-> 上帝; a god or the gods of the nations -> 神 (神明 where it reads better)\n"
            "Do not turn anything back into Mandarin: never write 他, 們, 沒有, 說, 誰, 什麼, 看見, 很, 給, 都."),
        "example": "[1] 太初有道，道佮上帝同在，道就是上帝。",
    },
}
LANG = None            # the language this run makes: set by main()
L = None               # and its entry in LANGS


def moe_table():
    f = L["table_file"]
    if f.exists() and (not L["dict_file"].exists() or f.stat().st_mtime >= L["dict_file"].stat().st_mtime):
        return json.loads(f.read_text(encoding="utf-8"))["words"]
    return build_moe_table()


def build_moe_table():
    table, n = L["build"](L)
    L["table_file"].parent.mkdir(parents=True, exist_ok=True)
    L["table_file"].write_text(json.dumps({"_source": f"{L['table_source']}; built by scripts/{L['script']}",
                                           "words": table}, ensure_ascii=False, indent=0, sort_keys=True),
                               encoding="utf-8")
    print(f"MOE table: {n} entries -> {len(table)} Mandarin words with a {L['name']} word")
    return table


# ------------------------------------------------------------------ the replacement
class Converter:
    def __init__(self):
        import jieba
        import opencc
        jieba.setLogLevel(60)
        core = json.loads((ROOT / "targets" / LANG / "replace.json").read_text(encoding="utf-8"))
        self.words = core["words"]
        self.god_not = set(core["god_not"])
        self.skip = set(core["moe_skip"])
        self.rules = [(re.compile(p), r) for p, r in core["rules"]]
        self.moe = moe_table()
        for w in self.words:
            if len(w) > 1:
                jieba.add_word(w)
        self.cut = jieba.lcut
        self.cc = opencc.OpenCC("s2tw")
        self.simp = opencc.OpenCC("t2s").convert

    def trad(self, s):
        return self.cc.convert(s)

    def line(self, text, hits, god=True):
        tokens = self.cut(text, HMM=False)
        whole = self.trad(text)
        if len(whole) == len(text):           # s2tw keeps length: cut the converted text at the same places
            at, trads = 0, []
            for t in tokens:
                trads.append(whole[at:at + len(t)])
                at += len(t)
        else:
            trads = [self.trad(t) for t in tokens]
        out = []
        for i, (s, t) in enumerate(zip(tokens, trads)):
            quoted = 0 < i < len(tokens) - 1 and tokens[i - 1] in "‘“「『" and tokens[i + 1] in "’”」』"
            if s == "神" and (not god or quoted or (i and tokens[i - 1] in self.god_not)):
                out.append(t)                  # 别神, ‘神’ (the word quoted: John 10:35), or a verse of gods
            elif s in self.words:
                out.append(self.words[s])
                hits[f"{t}→{self.words[s]}"] += 1
            elif t in self.moe and t not in self.skip:
                out.append(self.moe[t])
                hits[f"{t}→{self.moe[t]} (MOE)"] += 1
            else:
                out.append(t)
        text = "".join(out)
        for pat, rep in self.rules:
            text = pat.sub(rep, text)
        return text

    def tidy(self, text, keep=""):
        """The model's text put back into traditional characters with the
        rules run over it again: it slips in simplified ones (话 in Hakka John
        6:40, which the voice cannot read) and the odd Mandarin word. Only a
        character that is simplified and nothing else is converted - one that
        is itself traditional stays, or s2tw would turn the MOE's 脣 (脣項,
        beside) into Taiwan's 唇. Nor is a character the chapter's own draft
        uses: 干 and 里 are simplified and traditional both, and taken alone
        s2tw makes 相干 相幹 and 十五里 十五裡 (John 2:4, 11:18); the draft,
        converted a phrase at a time, has them right. s2tw turns 个 into 個;
        the last rule turns it back."""
        text = "".join(self.trad(c) if c not in keep and self.simp(c) == c and self.trad(c) != c else c
                       for c in text)
        for pat, rep in self.rules:
            text = pat.sub(rep, text)
        return text

    def verse(self, text, hits, god=True):
        return "\n".join(self.line(ln, hits, god) if ln.strip() else ln for ln in text.split("\n"))


def god_is_meant(english):
    """Whether the Mandarin's 神 in this verse can all be 上帝. Our Mandarin
    writes both God and a god as 神 (你们的神 is 'the LORD your God', 他们的神
    as often 'their gods'), so the English of the same verse decides: 'God'
    and no 'god' or 'gods' means every 神 is God. A verse with both, or with
    gods alone, keeps its 神 and the model is asked to sort them."""
    if english is None:
        return True
    return not re.search(r"\bgods?\b", english)


def mandarin_left(text):
    """Mandarin-only words per hundred characters."""
    n = sum(text.count(w) for w in L["mandarin"])
    return round(100 * n / max(1, len(re.sub(r"\s", "", text))), 1)


# ------------------------------------------------------------------ the model's edit
def system_prompt():
    rules = (ROOT / "prompts" / "targets" / f"{LANG}.txt").read_text(encoding="utf-8").strip()
    return (
        f"You edit a Bible chapter into {L['variety']}, written in the Ministry of Education's recommended "
        "characters.\n\n"
        + L["mend"] + " Do not retranslate, reorder or polish what is already right. Keep the meaning exactly - "
        "add nothing, drop nothing - keep names as the draft spells them, and keep 上帝, 耶和華, 主, 基督, 彌賽亞.\n\n"
        + rules + "\n\n"
        "OUTPUT: one line per verse, the verse number in square brackets and the text, e.g.\n"
        + L["example"] + "\n"
        "Every verse asked for, in order, and nothing else - no Mandarin, no draft, no notes.")


def edit_prompt(meta, ch, draft):
    """The draft alone. Shown the Mandarin beside it, the model copied the
    Mandarin back in (Hakka John 1:50 came back word for word in Mandarin), so
    it sees only the text it is to mend."""
    lines = [f"{meta['name']} {ch}. Mend the Mandarin left in this {L['name']} draft.", ""]
    lines += [f"[{n}] {one_line(draft[n])}" for n in sorted(draft)]
    lines += ["", f"Now the mended {L['name']}, verses {min(draft)} to {max(draft)}, one [n] line each."]
    return "\n".join(lines)


def keep_better(draft, edited):
    """The model's verse, unless it went backwards: more Mandarin than the
    draft, or so much shorter or longer that it cannot be the same verse."""
    d, e = re.sub(r"\s", "", draft), re.sub(r"\s", "", edited)
    if not e or not 0.75 <= len(e) / max(1, len(d)) <= 1.35:
        return draft, "length"
    if mandarin_left(edited) > mandarin_left(draft):
        return draft, "more Mandarin"
    return edited, None


def one_line(s):
    return s.replace("\n", " / ").strip(" /")


def model_edit(meta, ch, draft):
    model = T.model_for(LANG)
    system, user = system_prompt(), edit_prompt(meta, ch, draft)
    expected = sorted(draft)
    best, fix = None, ""
    for attempt in range(1, T.CONFIG.get("max_attempts", 3) + 1):
        try:
            raw, resp = T.call_model(system, user + fix, {"temperature": 0.3, **(
                {"num_gpu": gpu_layers()} if gpu_layers() is not None else {})}, model)
        except T.LoopError as e:
            raw, resp = e.text, {}
        verses, _, missing, _ = T.parse_output(raw, expected)
        if best is None or len(missing) < len(best[2]):
            best = (verses, raw, missing, resp, attempt)
        if not missing:
            break
        fix = (f"\n\nYour last answer left out verses {missing}. Give every verse from {expected[0]} to "
               f"{expected[-1]}, one [n] line each.")
        print(f"    {meta['name']} {ch}: attempt {attempt} missing {missing}, retrying", file=sys.stderr)
    verses, raw, missing, resp, attempts = best
    for n in missing:                          # a verse the model would not give keeps its draft
        verses[n] = draft[n]
    kept = {}
    for n in expected:
        verses[n], why = keep_better(draft[n], verses[n].replace(" / ", "\n"))
        if why:
            kept[n] = why
    return verses, raw, missing, resp, attempts, model, kept


# ------------------------------------------------------------------ chapters
def zh_chapters(code):
    name = slug(BOOKS[code]["name"])
    return sorted(int(p.stem.rsplit("_", 1)[1]) for p in T.json_dir("zh").glob(f"{name}_*.json")
                  if p.stem.rsplit("_", 1)[0] == name)


def draft_chapter(conv, code, ch, hits):
    """The Mandarin of a chapter and the draft made from it, or (None, None)."""
    name = slug(BOOKS[code]["name"])
    src = T.json_dir("zh") / f"{name}_{ch:02d}.json"
    if not src.exists():
        return None, None
    zh = {int(n): v for n, v in json.loads(src.read_text(encoding="utf-8"))["verses"].items()}
    en_path = T.json_dir("en") / f"{name}_{ch:02d}.json"
    en = {int(n): v for n, v in json.loads(en_path.read_text(encoding="utf-8"))["verses"].items()} \
        if en_path.exists() else {}
    return zh, {n: conv.verse(v, hits, god_is_meant(en.get(n))) for n, v in zh.items()}


def do_chapter(conv, code, ch, table_only, force, show):
    meta = BOOKS[code]
    name = slug(meta["name"])
    md_path = T.out_dir(LANG) / name / f"{name}_{ch:02d}.md"
    json_path = T.json_dir(LANG) / f"{name}_{ch:02d}.json"
    if md_path.exists() and not force:
        print(f"  {meta['name']} {ch} [{LANG}]: exists, skipping")
        return
    t0 = time.time()
    hits = Counter()
    zh, draft = draft_chapter(conv, code, ch, hits)
    if zh is None:
        print(f"  {meta['name']} {ch}: no Mandarin chapter to start from")
        return
    before = mandarin_left("".join(draft.values()))
    kept = {}
    if table_only:
        verses, raw, missing, resp, attempts, engine = dict(draft), "", [], {}, 0, "zh+table"
    else:
        verses, raw, missing, resp, attempts, model, kept = model_edit(meta, ch, draft)
        keep = set("".join(draft.values()))
        verses = {n: conv.tidy(v, keep) for n, v in verses.items()}
        engine = f"zh+table+{model}"
    after = mandarin_left("".join(verses.values()))
    dt = time.time() - t0
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(T.render_md(meta, ch, verses, ""), encoding="utf-8")
    json_path.write_text(json.dumps(
        {"book": meta["name"], "chapter": ch, "lang": LANG,
         "verses": {str(k): v for k, v in sorted(verses.items())}, "notes": "", "raw": raw, "engine": engine,
         "draft": {str(k): v for k, v in sorted(draft.items())}, "mandarin_left": {"draft": before, "final": after}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    with T.LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": ch,
                            "lang": LANG, "model": engine, "seconds": round(dt, 1), "attempts": attempts,
                            "prompt_tokens": resp.get("prompt_eval_count"), "output_tokens": resp.get("eval_count"),
                            "missing": missing, "extra": [], "loop": None,
                            "mandarin_left": [before, after]}) + "\n")
    changed = sum(1 for n in verses if verses[n] != draft[n])
    print(f"  {meta['name']} {ch} [{LANG}]: {len(verses)}/{len(zh)} vv, {dt:.0f}s, {sum(hits.values())} words "
          f"replaced, Mandarin left {before} -> {after} per 100 chars"
          + ("" if table_only else f", model changed {changed} verses")
          + (f", kept the draft for {len(kept)} ({', '.join(f'{n}: {w}' for n, w in sorted(kept.items()))})"
             if kept else ""))
    if show:
        for n in sorted(zh):
            same = verses[n] == draft[n]
            print(f"\n[{n}] 華語 {conv.trad(zh[n])}\n    草稿 {draft[n]}"
                  + ("" if table_only else f"\n    {L['native']} " + ("(= 草稿)" if same else verses[n])))
        print("\n  most replaced: " + ", ".join(f"{k} ×{v}" for k, v in hits.most_common(25)))


def setup(lang):
    """Make this module work for one language (for scripts that import it)."""
    global LANG, L
    LANG, L = lang, LANGS[lang]


def main(lang):
    global GPU_LAYERS
    setup(lang)
    ap = argparse.ArgumentParser(prog=L["script"], description=f"{L['name']} from our Mandarin")
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. John")
    ap.add_argument("chapters", nargs="?", help="chapter or range, e.g. 1-3 (default: the whole book)")
    ap.add_argument("--all", action="store_true", help="every book, the New Testament first")
    ap.add_argument("--table-only", action="store_true", help="the word replacement alone, no model")
    ap.add_argument("--force", action="store_true", help="redo chapters that exist")
    ap.add_argument("--show", action="store_true", help="print each verse's Mandarin, draft and result")
    ap.add_argument("--rebuild-table", action="store_true", help="rebuild the MOE table from the dictionary")
    ap.add_argument("--gpu-layers", type=int, help="keep only this many model layers on the GPU and the rest in "
                                                   "memory, so a training run can keep its share (qwen3.5 has 40)")
    a = ap.parse_args()
    GPU_LAYERS = a.gpu_layers
    if a.rebuild_table:
        build_moe_table()
        if not (a.book or a.all):
            return
    if not (a.book or a.all):
        ap.error("give a book, or --all")
    if a.book and a.book not in BOOKS:
        ap.error(f"no book {a.book!r}; use the OSIS code, e.g. Gen, John, 1Cor")
    conv = Converter()
    if not a.table_only:
        print(f"[{LANG}] zh + table + {T.model_for(LANG)}")
    # The whole Bible goes New Testament first: a reader wants the Gospels
    # long before Chronicles.
    books = sorted(BOOKS, key=lambda c: (BOOKS[c]["testament"] != "NT", BOOKS[c]["num"])) if a.all else [a.book]
    for code in books:
        have = zh_chapters(code)
        if a.chapters and not a.all:
            lo, _, hi = a.chapters.partition("-")
            have = [c for c in have if int(lo) <= c <= int(hi or lo)]
        for ch in have:
            do_chapter(conv, code, ch, a.table_only, a.force, a.show)
