# Calibration: several speakers, one passage

Matthew 6:9-13, 146 syllables, aligned in each recording by MMS_FA. Our voice: `models/mms/karen-runs/emma-v1/G_e0200.pth`.

| speaker | where (s) | rate syl/s | depth dB | rise ms | pitch st | bright dB | fit | in mean |
|---|---|---|---|---|---|---|---|---|
| Htoo Aye (Stuff of Life, with English) | 103.7-169.5 | 5.35 | 14.4 | 40 | 3.78 | -19.6 | 0.69 | yes |
| Stuff of Life reader (with English, music under) | 5.5-58.3 | 6.52 | 12.7 | 30 | 7.69 | -19.0 | 0.55 | yes |
| Thaw Eh Paw, narrator | 2.5-78.1 | 5.21 | 14.3 | 60 | 2.51 | -27.1 | 0.60 | yes |
| Karen Young Dreamers, Matthew 6 read whole | 159.6-207.0 | 5.21 | 20.7 | 50 | 5.30 | -16.7 | 0.72 | yes |
| Karen Spiritual Growth Channel | 97.9-134.9 | 6.06 | 12.7 | 40 | 3.82 | -16.2 | 0.65 | yes |
| congregation, Messiah St. Paul | 5.4-71.0 | 6.62 | 9.8 | 40 | 3.02 | -15.0 | 0.48 | no |
| congregation, Messiah St. Paul | 13.6-81.5 | 6.50 | 10.3 | 40 | 2.80 | -14.9 | 0.45 | no |
| **mean of 5 readers** | | **5.67** | **15.0** | **44** | **4.62** | | | |
| our voice, clarity 0 | | 7.39 | 11.7 | 20 | 2.87 | -20.7 | 0.11 | |
| our voice, clarity 0.5 | | 7.57 | 13.1 | 20 | 2.86 | -19.2 | 0.11 | |
| our voice, clarity 1 | | 7.34 | 14.1 | 20 | 2.97 | -17.4 | 0.11 | |
| our voice, clarity 1.5 | | 7.10 | 15.5 | 20 | 2.92 | -15.3 | 0.11 | |
| our voice, clarity 2 | | 7.17 | 15.3 | 20 | 3.01 | -13.2 | 0.11 | |
| our voice, clarity 3 | | 6.90 | 13.9 | 10 | 2.95 | -8.9 | 0.11 | |

Nearest the readers' mean on depth and rise: clarity 2. To speak at their rate the voice's pace would be 1.26 (above 1 is slower).

Fit is the aligner's mean confidence per syllable; a low one means the passage may not have been found, and that reader's numbers should not be trusted.
