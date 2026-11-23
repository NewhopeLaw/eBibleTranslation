# Shan trial

Written 2026-11-22 16:22 by scripts/trial_lang.py. Each model translated the same chapters; there is no published Bible to measure them against, so nothing here grades them (see the script's docstring).

"chrF back to English" is the chapter put into English again by NLLB-200 and measured against our English: a rough reading of whether the meaning survived, kinder to NLLB's own chapters than to the others'.

| model | chapter | verses | chrF back to English | in script % | verses with Shan letters | verses with Burmese letters |
|---|---|---|---|---|---|---|
| claude-opus | Genesis 1 | 31/31 | 57.6 | 100 | 31 | 0 |
| claude-opus | Ruth 1 | 22/22 | 44.5 | 100 | 22 | 0 |
| claude-opus | Psalms 23 | 6/6 | 39.1 | 100 | 6 | 0 |
| claude-opus | John 1 | 51/51 | 59.6 | 100 | 51 | 0 |
| madlad-400 | Genesis 1 | 31/31 | 47.5 | 100 | 31 | 3 |
| madlad-400 | Ruth 1 | 22/22 | 37.3 | 99 | 22 | 0 |
| madlad-400 | Psalms 23 | 6/6 | 25.9 | 99 | 6 | 0 |
| madlad-400 | John 1 | 51/51 | 57.4 | 96 | 51 | 0 |
| nllb-200 | Genesis 1 | 31/31 | 55.5 | 100 | 31 | 0 |
| nllb-200 | Ruth 1 | 22/22 | 52.7 | 100 | 22 | 0 |
| nllb-200 | Psalms 23 | 6/6 | 53.8 | 100 | 6 | 0 |
| nllb-200 | John 1 | 51/51 | 64.4 | 100 | 51 | 0 |
| qwen3-32b | Genesis 1 | 31/31 | 9.3 | 100 | 0 | 29 |
| qwen3-32b | Ruth 1 | 3/22 | 18.2 | 99 | 1 | 1 |
| qwen3-32b | Psalms 23 | 6/6 | 12.0 | 86 | 6 | 6 |
| qwen3-32b | John 1 | 51/51 | 11.1 | 100 | 51 | 0 |
| qwen3.5-35b-a3b | Genesis 1 | 31/31 | 13.4 | 100 | 31 | 0 |
| qwen3.5-35b-a3b | Ruth 1 | 22/22 | 14.1 | 100 | 22 | 0 |
| qwen3.5-35b-a3b | Psalms 23 | 6/6 | 13.0 | 100 | 0 | 6 |
| qwen3.5-35b-a3b | John 1 | 51/51 | 13.5 | 100 | 51 | 0 |

Mean chrF back to English: nllb-200 56.6, claude-opus 50.2, madlad-400 42.0, qwen3.5-35b-a3b 13.5, qwen3-32b 12.7
