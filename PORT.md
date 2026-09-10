# PORT.md — running the translation on the 5090 PC

The 5090 (Windows, 32 GB VRAM) runs qwen3:32b at ~35–45 tok/s vs the Spark's
6.8 — whole-Bible time drops from ~2 days to ~8–10 hours. Everything resumes,
so the two machines can trade off freely.

Do NOT move llama3.3:70b there: 43 GB doesn't fit in 32 GB VRAM and it will
crawl. 70B spot passes stay on the Spark.

## 1. One-time setup on the 5090

- [ ] Install [Ollama for Windows](https://ollama.com/download/windows)
- [ ] `ollama pull qwen3:32b` (~20 GB)
- [ ] Install Python 3.10+ (`winget install Python.Python.3.12`) —
      the scripts are pure standard library, nothing to pip-install
- [ ] Confirm Tailscale is signed in (the PC is already on the tailnet)

## 2. Shared folder over Tailscale (pick ONE)

### Option A — Taildrive (recommended: no new software)

On the Spark (share the canonical folder):
```sh
sudo tailscale drive share ebible /home/clemcheng/eBibleTranslation
```

In the Tailscale admin console → Access controls, grant access (once):
```jsonc
"grants": [{
  "src": ["autogroup:member"],
  "dst": ["*"],
  "app": {"tailscale.com/cap/drive": [{"shares": ["ebible"], "access": "rw"}]}
}]
```

On the 5090 (map it as a network drive):
```
net use B: \\100.100.100.100@8080\<tailnet-name>\spark-1526\ebible /persistent:yes
```
(Find `<tailnet-name>` in the admin console header, e.g. `law.github`.)

Then run from the mapped drive:
```
cd /d B:\
python scripts\translate.py --all
```

### Option B — Syncthing (better if the 5090 goes offline mid-run)

Install Syncthing on both, share `eBibleTranslation` both ways over the
tailnet IPs. Two-way sync means don't run translate.py on both machines
against the SAME book at the same time (see §4).

### Option C — one-shot copy (no live share)

```
scp -r clemcheng@100.118.191.115:eBibleTranslation C:\ebible
```
…and rsync/scp `output/` and `logs/` back when done. Simplest, but manual.

## 3. Run

```
python scripts\translate.py --all        # resumes wherever the Spark stopped
python scripts\verify.py                 # flags problems, fixes nothing
python scripts\build_site.py             # refresh site/index.html reader
```

`config.json` needs no changes — `api_url` points at localhost, which is the
5090's own Ollama once you're running there.

## 4. Both machines at once (optional)

Safe as long as they work on DIFFERENT books — chapter files are the resume
unit and books never overlap:
```
# 5090 (fast): the long OT narrative + poetry
python scripts\translate.py Exod   ... etc.
# Spark (slow, idle time): short NT epistles
python3 scripts/translate.py Titus
```
Never point two runs at the same book: both would translate the same missing
chapters and race on the same output files. logs/translate.jsonl records which
machine's model did each chapter (append-safe from both only on a real shared
folder, Option A).

## 5. Gotchas

- [ ] Windows Defender may scan every chapter write on a mapped drive; if
      chapters feel slow to save, exclude the drive letter.
- [ ] Taildrive access is per-share and read-write here; the Spark stays the
      canonical copy — back it up (`sources/` is re-cloneable; `output/`,
      `logs/`, `glossary.json` are not).
- [ ] The avatar's vLLM lives on the Spark and is untouched by any of this;
      the 5090 run creates zero contention with it.
- [ ] Keep `num_ctx` at 16384 in config.json: qwen3:32b + that KV cache is
      ~25 GB, comfortably inside 32 GB VRAM. Don't raise it past ~32k on the
      5090 or Ollama will start offloading layers to system RAM.
