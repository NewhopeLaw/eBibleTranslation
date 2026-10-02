# Burmese trial

Written 2026-09-30 11:02 by scripts/trial_lang.py. Each model translated the same chapters; chrF is measured against Judson 1835 and Common Language 2005 and ranks the models rather than grading them (see the script's docstring).

| model | chapter | verses | chrF Judson 1835 | chrF Common Language 2005 | in script % | Zawgyi verses | spoken-register words |
|---|---|---|---|---|---|---|---|
| nllb-200 | Genesis 1 | 31/31 | 47.8 | 40.0 | 100 | 0 | 0 |
| nllb-200 | Ruth 1 | 22/22 | 44.8 | 36.3 | 100 | 0 | 0 |
| nllb-200 | Psalms 23 | 6/6 | 48.3 | 30.4 | 100 | 0 | 0 |
| nllb-200 | John 1 | 51/51 | 52.3 | 53.9 | 100 | 2 | 0 |
| qwen3-32b | Genesis 1 | 31/31 | 31.8 | 31.9 | 100 | 0 | 0 |
| qwen3-32b | Ruth 1 | 22/22 | 32.8 | 32.9 | 100 | 0 | 1 |
| qwen3-32b | Psalms 23 | 6/6 | 26.7 | 24.4 | 100 | 0 | 0 |
| qwen3-32b | John 1 | 50/51 | 33.4 | 30.7 | 100 | 0 | 0 |
| qwen3.5-35b-a3b | Genesis 1 | 31/31 | 38.0 | 38.0 | 100 | 0 | 0 |
| qwen3.5-35b-a3b | Ruth 1 | 22/22 | 36.2 | 37.3 | 100 | 0 | 0 |
| qwen3.5-35b-a3b | Psalms 23 | 6/6 | 36.0 | 32.4 | 100 | 0 | 0 |
| qwen3.5-35b-a3b | John 1 | 51/51 | 34.7 | 33.7 | 100 | 0 | 0 |
| (Judson 1835, a human translation) | Genesis 1 | 31/31 | - | 43.0 | 100 | 0 | 0 |
| (Judson 1835, a human translation) | Ruth 1 | 22/22 | - | 41.7 | 100 | 0 | 0 |
| (Judson 1835, a human translation) | Psalms 23 | 6/6 | - | 38.0 | 100 | 0 | 0 |
| (Judson 1835, a human translation) | John 1 | 51/51 | - | 52.1 | 100 | 0 | 0 |
| (Common Language 2005, a human translation) | Genesis 1 | 30/31 | 37.7 | - | 100 | 0 | 0 |
| (Common Language 2005, a human translation) | Ruth 1 | 21/22 | 45.1 | - | 100 | 0 | 0 |
| (Common Language 2005, a human translation) | Psalms 23 | 6/6 | 44.7 | - | 100 | 0 | 0 |
| (Common Language 2005, a human translation) | John 1 | 51/51 | 54.9 | - | 100 | 0 | 0 |

Mean chrF against Judson 1835: nllb-200 48.3, (Common Language 2005, a human translation) 45.6, qwen3.5-35b-a3b 36.2, qwen3-32b 31.2

Mean chrF against Common Language 2005: (Judson 1835, a human translation) 43.7, nllb-200 40.1, qwen3.5-35b-a3b 35.4, qwen3-32b 30.0
