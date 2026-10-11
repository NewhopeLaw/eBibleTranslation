# Our lexeme inventory against the reference tagging

Written 2026-10-03 10:44 by `build_lexemes.py --score`. The reference tagging is
STEPBible's (CC BY 4.0) and is used here only to read our inventory against; none of it is
copied into it. Agreement is partly memory (docs/from-the-text.md, point 3); the lists below
are the half worth reading.

## The figures

- words compared: 442,251 (0 more have a reference tag but no answer of ours)
- our lexemes: 27,037; reference words they meet: 16,967
- words whose lexeme lands on its usual reference word: 393,575 (89.0%)
- the same, ignoring the letter STEPBible adds to split one Strong's number: 417,776 (94.5%)
- the best an inventory with one answer per spelling could reach: 420,405 (95.1%). 5,114 spellings stand for more than one word in the reference, and 21,846 words (4.9%) are lost to that before the model answers anything.

Where the rest of the disagreement lies, in words of the text:

- merged, different words: 24,602 (5.6%)
- merged, the reference's finer sense letter: 24,074 (5.4%)
- split, a spelling from the text given as the headword: 54,960 (12.4%)
- split, pointing or accents only: 20,815 (4.7%)
- split, different headwords: 20,203 (4.6%)
- split, prefix left on: 17,910 (4.0%)
- split, ending left on: 10,648 (2.4%)
- split, : 0 (0.0%)

Merges and homographs overlap: a spelling that is two words in the reference, answered once,
puts both into one of our lexemes, so it is counted in both lists.

## Splits: one reference word, several of ours

Commonest first; the first of our lexemes is the one most of the word went to, and each
other says why it stands apart. A prefix, an ending or a spelling from the text given as the
headword is a fault the prompt already warns against, and a repair could ask those forms again.

| words off | reference word | our lexemes (words, why apart) | e.g. |
|---|---|---|---|
| 11910 | ὁ (G3588, “the/this/who”) | ὁ (7792); τό (6522, a spelling from the text given as the headword); ἡ (5128, a spelling from the text given as the headword); τάς (203, different headwords); ὅς (36, ending left on) | τὸν Matthew 1:2 |
| 2734 | כֹּל (H3605, “all”) | כָּל (2678); כֹּל (1082, pointing or accents only); וְכָל (587, prefix left on); בְּכָל (350, prefix left on); לְכָל (217, prefix left on) | וּבְכָל Genesis 1:26 |
| 2628 | הָיָה (H1961, “to be”) | הָיָה (932); יִהְיֶה (665, a spelling from the text given as the headword); וַיְהִי (633, a spelling from the text given as the headword); וְהָיָה (380, prefix left on); הָיוּ (167, a spelling from the text given as the headword) | תִּֽהְיֶה Genesis 4:12 |
| 1983 | בֵּן (H1121A, “son: child”) | בֶּן (1064); בֵּן (706, pointing or accents only); בְּנֵי (271, a spelling from the text given as the headword); בֶן (253, pointing or accents only); בָּנָיו (152, a spelling from the text given as the headword) | בֵּן Genesis 4:25 |
| 1920 | אָמַר (H0559, “to say”) | אָמַר (3386); לֵאמֹר (938, prefix left on); יָּמַר (282, different headwords); וַתֹּאמֶר (206, a spelling from the text given as the headword); יָֽאמַר (96, different headwords) | לֵאמֹר Genesis 1:22 |
| 1788 | אֶל (H0413, “to(wards)”) | אֶל (3726); אֵלָיו (452, ending left on); אֵלַי (390, ending left on); וְאֶל (301, prefix left on); אֵלֶיךָ (229, ending left on) | אֵלָיו Genesis 8:9 |
| 1647 | אֵת (H0853, “[Obj.]”) | אֵת (9281); אֶת (498, pointing or accents only); אֹתוֹ (395, ending left on); הֵם (252, a spelling from the text given as the headword); אֹתָהּ (162, ending left on) | אֶֽת Genesis 2:6 |
| 1400 | מֶ֫לֶךְ (H4428G, “king”) | מֶלֶךְ (1112); הַמֶּלֶךְ (955, prefix left on); מַלְכֵי (146, a spelling from the text given as the headword); הַמֶּֽלֶךְ (117, prefix left on); לְמֶלֶךְ (58, prefix left on) | הַמֶּלֶךְ Genesis 39:20 |
| 1386 | יוֹם (H3117G, “day”) | יוֹם (548); הַיּוֹם (257, prefix left on); יָמִים (237, a spelling from the text given as the headword); יָֽמִים (217, a spelling from the text given as the headword); בְּיוֹם (194, prefix left on) | הַיּוֹם Genesis 1:14 |
| 1316 | אֶ֫רֶץ (H0776G, “land: country/planet”) | אֶרֶץ (1002); הָאָרֶץ (720, prefix left on); בְּאֶרֶץ (211, prefix left on); בָּאָרֶץ (139, prefix left on); אָֽרֶץ (43, pointing or accents only) | הָאָרֶץ Genesis 1:11 |
| 1297 | בּוֹא (H0935G, “to come (in): come”) | בָּא (637); יָבָא (425, different headwords); יָבֹא (361, a spelling from the text given as the headword); בֹּא (143, pointing or accents only); בָּאָה (107, ending left on) | וַיָּבֹא Genesis 7:7 |
| 1260 | עַל (H5921A, “upon”) | עַל (4501); עָלָיו (361, ending left on); עָלָה (245, ending left on); מֵעַל (195, prefix left on); עֲלֵיהֶם (190, ending left on) | עָלָיו Genesis 12:20 |
| 1138 | σύ (G4771, “you”) | ὑμεῖς (1823); σύ (1024, a spelling from the text given as the headword); σὺ (44, a spelling from the text given as the headword); ἑαυτός (38, different headwords); σύς (6, different headwords) | σου Matthew 1:20 |
| 1039 | יְהֹוָה (H3068G, “LORD”) | יְהוָה (5480); יְהוָֽה (599, pointing or accents only); לַֽיהוָה (201, prefix left on); לַיהוָה (73, prefix left on); בַּֽיהוָה (46, prefix left on) | יְהוָֽה Genesis 4:1 |
| 1021 | οὗτος (G3778, “this/he/she/it”) | τοῦτο (360); τοῦτος (310, ending left on); οὗτος (260, a spelling from the text given as the headword); ταῦτα (248, a spelling from the text given as the headword); ταύτη (129, a spelling from the text given as the headword) | τούτων Matthew 3:9 |
| 962 | עַם (H5971A, “people”) | עַם (794); הָעָם (634, prefix left on); עָם (235, pointing or accents only); הָֽעַמִּים (29, a spelling from the text given as the headword); לְעַמּוֹ (10, a spelling from the text given as the headword) | הָעָם Genesis 19:4 |
| 908 | עָשָׂה (H6213A, “to make: do”) | עָשָׂה (843); עֲשׂוֹת (196, a spelling from the text given as the headword); עֹשֶׂה (117, pointing or accents only); יָּסַד (113, different headwords); יַעֲשֶׂה (107, a spelling from the text given as the headword) | לַעֲשׂוֹת Genesis 11:6 |
| 852 | μέ (G3165, “me”) | ἐγώ (1072); ἡμεῖς (852, a spelling from the text given as the headword) | ἡμῶν Matthew 1:23 |
| 777 | בֵּן (H1121G, “son: descendant/people”) | בְּנֵי (783); בֵּן (468, a spelling from the text given as the headword); בְנֵי (77, pointing or accents only); מִבְּנֵי (77, prefix left on); וּבְנֵי (74, prefix left on) | בְנֵֽי Genesis 19:38 |
| 773 | הָלַךְ (H1980G, “to go: went”) | וַיֵּלֶךְ (169); יָלַךְ (141, a spelling from the text given as the headword); הָלַךְ (130, a spelling from the text given as the headword); לֶכֶת (129, different headwords); יֵלֵךְ (55, a spelling from the text given as the headword) | וַיֵּלְכוּ Genesis 18:22 |
| 755 | דָבַר (H1696G, “to speak: speak”) | דָּבַר (303); וַיְדַבֵּר (188, a spelling from the text given as the headword); דִּבֶּר (162, pointing or accents only); דַּבֵּר (127, pointing or accents only); יְדַבֵּר (93, a spelling from the text given as the headword) | וַיְדַבֵּר Genesis 8:15 |
| 744 | οὐ (G3756, “no”) | οὐκ (918); οὐ (680, a spelling from the text given as the headword); οὐκέτι (47, ending left on); οὔ (17, a spelling from the text given as the headword) | οὐ Matthew 5:14 |
| 707 | פָּנֶה (H6440G, “face: before”) | לִפְנֵי (681); פָּנִים (380, a spelling from the text given as the headword); לְפָנֶיךָ (89, ending left on); לְפָנַי (49, pointing or accents only); מִפְּנֵי (38, different headwords) | מִפְּנֵי Genesis 7:7 |
| 696 | הוּא (H1931, “he/she/it”) | הוּא (1182); הִיא (216, a spelling from the text given as the headword); הִוא (193, pointing or accents only); וְהוּא (188, prefix left on); הַיָּה (62, different headwords) | הִיא Genesis 14:2 |
| 674 | נָתַן (H5414G, “to give: give”) | נָתַן (641); יִתֵּן (118, a spelling from the text given as the headword); יָתַן (113, a spelling from the text given as the headword); נָתַתִּי (81, a spelling from the text given as the headword); לָתֵת (67, a spelling from the text given as the headword) | תֵּת Genesis 4:12 |
| 665 | לֹא (H3808, “not”) | לֹא (4504); וְלֹא (353, prefix left on); הֲלֹא (267, prefix left on); בְּלֹא (20, prefix left on); לֹּא (6, pointing or accents only) | וְלֹֽא Genesis 8:9 |
| 648 | זֶה (H2088, “this”) | הַזֶּה (528); זֶה (390, a spelling from the text given as the headword); זֶֽה (175, different headwords); מִזֶּה (63, a spelling from the text given as the headword); כָּזֶה (10, a spelling from the text given as the headword) | זֶה Genesis 5:1 |
| 632 | יָשַׁב (H3427, “to dwell”) | יָשַׁב (447); יֹשֵׁב (212, pointing or accents only); יֹשְׁבֵי (136, ending left on); יֵשֵׁב (43, pointing or accents only); לָשֶׁבֶת (35, a spelling from the text given as the headword) | יֹשֵׁב Genesis 4:20 |
| 626 | אֵת (H0854, “with”) | אֵת (303); אִתּוֹ (165, ending left on); מֵאֵת (122, prefix left on); אִתָּם (66, ending left on); אִתִּי (59, ending left on) | אִתּוֹ Genesis 7:7 |
| 557 | לָקַח (H3947G, “to take: take”) | לָקַח (214); וַיִּקַּח (173, a spelling from the text given as the headword); קָח (100, different headwords); קַח (66, a spelling from the text given as the headword); יִקְחַ (44, different headwords) | וַיִּקַּח Genesis 2:15 |
| 538 | מוּת (H4191, “to die”) | מֵת (302); מָוַת (76, different headwords); יָמוּת (72, a spelling from the text given as the headword); מוֹת (71, a spelling from the text given as the headword); יָמַת (49, a spelling from the text given as the headword) | תְּמֻתֽוּן Genesis 3:3 |
| 509 | אֱלֹהִים (H0430G, “God”) | אֱלֹהִים (1874); אֱלֹהֵי (331, a spelling from the text given as the headword); הָאֱלֹהִֽים (38, prefix left on); אֱלֹהֵיהֶם (29, a spelling from the text given as the headword); אֱלֹהֶֽיךָ (29, a spelling from the text given as the headword) | אֱלֹהֵי Genesis 9:26 |
| 499 | מָה (H4100, “what?”) | מַה (248); מָה (175, pointing or accents only); לָמָּה (147, prefix left on); מֶה (53, pointing or accents only); וּמַה (40, prefix left on) | מֶֽה Genesis 20:9 |
| 480 | בּוֹא (H0935P, “to come (in): bring”) | הֵבִיא (75); יָבֹא (68, a spelling from the text given as the headword); יָבִיא (68, a spelling from the text given as the headword); בָּא (60, a spelling from the text given as the headword); הָבִיא (39, pointing or accents only) | וַיָּבֵא Genesis 2:19 |
| 473 | הֶם (H9038, “them”) | לָהֶם (652); בָּהֶם (121, a spelling from the text given as the headword); מֵהֶם (97, a spelling from the text given as the headword); בָּם (88, a spelling from the text given as the headword); לָמוֹ (55, a spelling from the text given as the headword) | בָּהֶם Genesis 41:56 |
| 443 | רָאָה (H7200G, “to see: see”) | רָאָה (754); יָרָא (55, a spelling from the text given as the headword); לִרְאוֹת (44, a spelling from the text given as the headword); יִֽרְאוּ (38, different headwords); רֹאֶה (30, pointing or accents only) | וַיֵּרָא Genesis 12:7 |
| 441 | שָׁמַע (H8085G, “to hear: hear”) | שָׁמַע (524); שִׁמְעוּ (89, ending left on); יִשְׁמָע (38, a spelling from the text given as the headword); שֹׁמֵעַ (38, pointing or accents only); שָׁמְעוּ (36, ending left on) | שִׁמְעוּ Genesis 37:6 |
| 441 | שׁוּב (H7725G, “to return: return”) | שׁוּב (187); יָשַׁב (92, a spelling from the text given as the headword); שָׁבַב (82, different headwords); יָשׁוּב (52, a spelling from the text given as the headword); שָׁב (45, a spelling from the text given as the headword) | וַתָּשָׁב Genesis 8:9 |
| 431 | וֹ (H9033, “him”) | לוֹ (1120); בּוֹ (275, a spelling from the text given as the headword); בוֹ (95, a spelling from the text given as the headword); לו (19, pointing or accents only); לָהּ (14, a spelling from the text given as the headword) | בּוֹ Genesis 1:29 |
| 405 | אָכַל (H0398, “to eat”) | אָכַל (405); יֹאכַל (142, a spelling from the text given as the headword); יֵאָכֵל (38, a spelling from the text given as the headword); לֶאֱכֹל (36, prefix left on); תֹּאכַל (35, a spelling from the text given as the headword) | וַתֹּאכַל Genesis 3:6 |
| 400 | אֵ֫לֶּה (H0428, “these”) | אֵלֶּה (346); הָאֵלֶּה (274, prefix left on); וְאֵלֶּה (106, prefix left on); כָּאֵלֶּה (8, prefix left on); לָאֵלֶּה (5, prefix left on) | הָאֵלֶּה Genesis 15:1 |
| 386 | שְׁנַ֫יִם (H8147, “two”) | שְׁנַיִם (382); שְׁתֵּי (124, a spelling from the text given as the headword); שְׁתַּיִם (83, a spelling from the text given as the headword); שְׁנֵיהֶם (49, a spelling from the text given as the headword); שְׁנֵי (33, different headwords) | שְׁתֵּי Genesis 4:19 |
| 381 | שָׁלַח (H7971G, “to send: depart”) | שָׁלַח (288); וַיִּשְׁלַח (171, a spelling from the text given as the headword); יְשַׁלַּח (31, a spelling from the text given as the headword); שְׁלַחְתִּי (24, ending left on); שֹׁלֵחַ (22, pointing or accents only) | וַיִּשְׁלַח Genesis 20:2 |
| 371 | דָּוִד (H1732, “David”) | דָּוִד (704); דָּוִיד (205, a spelling from the text given as the headword); לְדָוִד (137, prefix left on); בְּדָוִד (12, prefix left on); דָּוִֽיד (10, a spelling from the text given as the headword) | דָּוִיד 1 Kings 3:14 |
| 370 | הִנֵּה (H2009, “behold”) | הִנֵּה (472); וְהִנֵּה (352, prefix left on); הִנָּם (8, a spelling from the text given as the headword); הֵם (7, a spelling from the text given as the headword); הִנְנִי (2, a spelling from the text given as the headword) | וְהִנֵּה Genesis 1:31 |
| 364 | נָכָה (H5221, “to smite”) | יָכָה (136); יָכַה (51, pointing or accents only); הִכָּה (46, different headwords); כָּהָה (36, a spelling from the text given as the headword); יָכַל (29, a spelling from the text given as the headword) | הִכָּה Exodus 9:25 |
| 363 | כֹּהֵן (H3548, “priest”) | כֹּהֵן (387); הַכֹּהֵן (328, prefix left on); לַכֹּהֵן (17, prefix left on); כֹּהֲנֵי (12, a spelling from the text given as the headword); כֹּהֲנֶיהָ (4, a spelling from the text given as the headword) | הַכֹּהֵן Exodus 29:30 |
| 359 | בַּ֫יִת (H1004B, “house: home”) | בַּיִת (539); בֵּית (219, pointing or accents only); בְּבֵית (26, prefix left on); הַבָּֽיִת (26, prefix left on); הַבָּיִת (25, prefix left on) | בֵּית Genesis 19:2 |
| 332 | אָב (H0001G, “father”) | אָב (876); אָבִי (114, ending left on); אֲבוֹת (40, ending left on); אֲבֹתָם (38, ending left on); אֲבֹת (33, ending left on) | אָבִי Genesis 19:34 |
| 325 | עָלָה (H5927G, “to ascend: rise”) | עָלָה (292); וַיַּעַל (87, a spelling from the text given as the headword); יַעֲלֶה (55, a spelling from the text given as the headword); עֵץ (34, a spelling from the text given as the headword); יָרַע (25, a spelling from the text given as the headword) | וַיַּעַל Genesis 13:1 |
| 324 | עִם (H5973A, “with”) | עִם (656); עִמּוֹ (121, a spelling from the text given as the headword); עִמָּךְ (51, a spelling from the text given as the headword); עִמִּי (47, a spelling from the text given as the headword); עִמָּכֶם (35, a spelling from the text given as the headword) | עִמּוֹ Genesis 13:1 |
| 323 | מִן־ (H4480A, “from”) | מִן (863); וּמִן (98, prefix left on); מִמֶּנִּי (65, a spelling from the text given as the headword); מִמְּךָ (40, a spelling from the text given as the headword); מִנִּי (38, a spelling from the text given as the headword) | וּמִן Genesis 6:20 |
| 319 | זֹאת (H2063, “this”) | זֹאת (285); הַזֹּאת (270, prefix left on); כָּזֹאת (23, prefix left on); בְּזֹאת (15, prefix left on); הֲזֹאת (5, prefix left on) | הַזֹּאת Genesis 12:7 |
| 308 | אֶחָד (H0259, “one”) | אֶחָד (662); אַחַת (192, a spelling from the text given as the headword); הָֽאֶחָד (23, prefix left on); בָּד (18, a spelling from the text given as the headword); כְּאַחַד (12, prefix left on) | אַחַת Genesis 2:21 |
| 302 | עָשָׂה (H6213H, “to make”) | עָשָׂה (438); יָּסַד (117, different headwords); עֹשֶׂה (42, pointing or accents only); עֲשׂוֹת (22, a spelling from the text given as the headword); עֲשֹׂה (22, pointing or accents only) | וַיַּעַשׂ Genesis 1:7 |
| 301 | כֵּן (H3651C, “so”) | כֵּן (433); לָכֵן (200, prefix left on); כֵן (99, pointing or accents only); בְּכֵן (2, prefix left on) | לָכֵן Genesis 4:15 |
| 289 | שַׂר (H8269, “ruler”) | שָׂרֵי (132); שַׂר (94, a spelling from the text given as the headword); שָׂר (68, a spelling from the text given as the headword); שָׂרֶה (63, different headwords); שָּׂרִים (31, ending left on) | שַׂר Genesis 21:22 |
| 288 | צָוָה (H6680, “to command”) | צִוָּה (206); צָוָה (204, pointing or accents only); מְצַוְּךָ (25, a spelling from the text given as the headword); מזהה (14, different headwords); צַוָּה (11, pointing or accents only) | וַיְצַו Genesis 2:16 |
| 282 | יָצָא (H3318G, “to come out: come”) | יָצָא (341); יֵצֵא (113, pointing or accents only); צֵאת (51, a spelling from the text given as the headword); יֵצְאוּ (37, ending left on); צֵא (29, a spelling from the text given as the headword) | יֵצְאוּ Genesis 15:14 |
| 281 | שָׁנָה (H8141, “year”) | שָׁנָה (596); שָׁנִים (104, a spelling from the text given as the headword); בַּשָּׁנָה (49, prefix left on); שְׁנָה (48, pointing or accents only); שָׁנִֽים (22, a spelling from the text given as the headword) | שָׁנִים Genesis 5:6 |

## Merges: one of ours, several reference words

Sorted by the words that belong to a different reference word, the half to read; a sense
letter is STEPBible cutting one Strong's number more finely than a dictionary does.

| different words | sense letters | our lexeme | reference words also in it (words) | e.g. |
|---|---|---|---|---|
| 1003 | 39 | λέγω (eG00086, “to say”) | εἶπον (G2036, “to say”) (914); φημί (G5346, “to assert”) (42); ἐρέω (G4483, “to say”) (28); ἐρῶ (G2046, “to say”) (18) | εἶπαν Matthew 2:5 |
| 787 | 0 | ἐγώ (eG00189, “I, me”) | ἐγώ (G1473, “I/we”) (787) | κἀγὼ Matthew 2:8 |
| 348 | 0 | τίς (eG00314, “what, which”) | τις (G5100, “one”) (348) | τι Matthew 5:23 |
| 336 | 547 | אִישׁ (eH00253, “man”) | אֱנוֹשׁ (H0582, “human”) (322); אִישׁ־בֹ֫שֶׁת (H0378, “Ish-bosheth”) (10); אִישׁוֹן (H0380, “pupil”) (3); אִשׁ (H0786, “there is”) (1) | אַנְשֵׁי Genesis 6:4 |
| 312 | 0 | אֵת (eH00004, “object marker”) | אֵת (H0854, “with”) (303); אֵתָם (H0864, “Etham”) (4); אֵת (H0855, “plowshare”) (2); אֵיתָן (H0386, “strong”) (1) | אֶת Genesis 4:1 |
| 288 | 0 | הֵם (eH00084, “they”) | הֵ֫מָּה (H1992, “they(masc.)”) (221); הֶם (H9038, “them”) (48); הֵן (H2005, “look!”) (7); הִנֵּה (H2009, “behold”) (7) | הֵם Genesis 3:7 |
| 278 | 124 | עָלָה (eH01232, “to go up”) | עַל (H5921A, “upon”) (245); עֹל (H5923, “yoke”) (8); מָעַל (H4603, “be unfaithful”) (5); עָלַם (H5956, “to conceal”) (4) | עָלָֽיו Genesis 15:12 |
| 257 | 0 | יָשַׁב (eH00145, “to dwell”) | שׁוּב (H7725G, “to return: return”) (92); שָׁכַן (H7931, “to dwell”) (39); שָׁתָה (H8354, “to drink”) (16); שׁוּב (H7725I, “to return: turn back”) (11) | וַתָּשָׁב Genesis 8:9 |
| 190 | 19 | אֵל (eH00963, “god”) | אֶל (H0413, “to(wards)”) (90); בֵּֽיתְ־אֵל (H1008G, “Bethel”) (70); אֵל (H0411, “these”) (9); עֲשָׂהאֵל (H6214G, “Asahel”) (6) | אֵלֶיהָ Genesis 16:13 |
| 167 | 1 | לֵב (eH00556, “heart”) | לֵבָב (H3824, “heart”) (154); לִבָּה (H3826, “heart”) (7); גֵּו (H1460A, “back”) (3); לְבַב (H3825, “heart”) (3) | לְבָבִי Genesis 20:5 |
| 160 | 0 | רָב (eH00317, “much, many”) | רָבָה (H7235A, “to multiply”) (69); רַב (H7227A, “many”) (49); רָבַב (H7231, “to multiply”) (18); רִיב (H7378, “to contend”) (12) | הַרְבָּה Genesis 3:16 |
| 147 | 0 | ἄνθρωπος (eG00083, “man, human”) | ἀνήρ (G0435G, “man”) (112); ἀνήρ (G0435H, “man: husband”) (34); ἀνθρώπινος (G0442, “human”) (1) | ἄνδρες Matthew 12:41 |
| 136 | 524 | בֵּית (eH00936, “house”) | בַּ֫יִת (H1005, “house”) (25); בֵּית לֶ֫חֶם (H1035G, “Bethlehem”) (15); בֵּֽיתְ־אֵל (H1008G, “Bethel”) (15); בֵּית אָ֫וֶן (H1007, “Beth-aven”) (7) | בֵּית Ezra 4:24 |
| 132 | 301 | בַּיִת (eH00583, “house”) | בֵּֽיתְ־אֵל (H1008G, “Bethel”) (47); בֵּית לֶ֫חֶם (H1035G, “Bethlehem”) (21); בֵּית שֶׁ֫מֶשׁ (H1053G, “Beth-shemesh”) (7); בַּ֫יִת (H1005, “house”) (6) | בֵּֽית Genesis 12:8 |
| 129 | 0 | לֹא (eH00160, “not”) | בִּלְתִּי (H1115, “lest”) (108); בְּלִי (H1097, “without”) (16); לֹא רֻחָ֫מָה (H3819, “No Mercy”) (2); לוּלֵא (H3884, “unless”) (1) | לְבִלְתִּי Genesis 3:11 |
| 128 | 0 | γινώσκω (eG00157, “to know”) | οἶδα (G6063, “to know”) (78); εἴδω (G1492I, “to perceive: know”) (29); εἴδω (G1492H, “to perceive: see”) (5); γνωρίζω (G1107, “to make known”) (4) | οἶδεν Matthew 6:8 |
| 125 | 0 | εἰμί (eG00095, “to be”) | εἶναι (G1511, “to exist”) (123); ἐάω (G1439, “to allow”) (2) | εἶναι Matthew 16:13 |
| 122 | 192 | רָעָה (eH01439, “evil”) | רָעָה (H7462B, “to pasture”) (58); רָעַע (H7489A, “be evil”) (29); רֹעַ (H7455, “evil”) (15); רוּעַ (H7321, “to shout”) (4) | אֶרְעֶה Genesis 30:31 |
| 114 | 23 | יָם (eH00050, “sea”) | יוֹם (H3117G, “day”) (90); יוֹם (H3117L, “day: today”) (14); יַם (H3221, “sea”) (2); סָבַב (H5437H, “to turn: surround”) (2) | הַיּֽוֹם Genesis 18:1 |
| 112 | 10 | כֶּסֶף (eH01008, “silver”) | כְּלִי (H3627, “article/utensil”) (99); כְּסַף (H3702, “silver”) (8); כְּסוּת (H3682, “covering”) (4); כּוֹס (H3563A, “cup”) (1) | כְּלֵי Genesis 24:53 |
| 109 | 9 | עַל (eH00012, “on, over”) | עַל (H5922, “since”) (84); עָלָה (H5927G, “to ascend: rise”) (7); עֲלַל (H5954, “to come”) (5); עַל (H5920H, “height”) (4) | עַל Ezra 4:8 |
| 103 | 0 | לָךְ (eH00333, “to you”) | ךָּ (H9031, “you”) (84); הָלַךְ (H1980G, “to go: went”) (12); הָלַךְ (H1980L, “to go: continue”) (2); הָלַךְ (H1980I, “to go: walk”) (2) | לָךְ Genesis 3:18 |
| 97 | 0 | זָרַע (eH00129, “to sow”) | זֶ֫רַע (H2233H, “seed: children”) (37); זְרוֹעַ (H2220, “arm”) (21); זָרָה (H2219, “to scatter”) (18); זֶ֫רַע (H2233G, “seed”) (6) | וּֽלְזַרְעֲךָ Genesis 13:15 |
| 94 | 0 | אַף (eH00263, “nose”) | אַף (H0639G, “face: anger”) (85); אַף (H0639H, “face: nose”) (9) | אַף Genesis 27:45 |
| 90 | 0 | ὅς (eG00158, “who, which”) | ὁ (G3588, “the/this/who”) (36); ὅστις (G3748, “who/which”) (26); οὗ (G3757, “whither”) (24); οἷος (G3634, “such as”) (4) | Οἱ Matthew 16:14 |
| 89 | 0 | מִן (eH00167, “from”) | מִן־ (H4481, “from”) (80); כֶם (H9036, “you”) (5); הֶן (H9039, “them”) (2); נַ֫חַל (H5158A, “torrent: river”) (1) | מִן Ezra 4:12 |
| 89 | 0 | μή (eG00109, “not”) | μηδέ (G3366, “nor”) (55); μηκέτι (G3371, “never again”) (21); μήτι (G3385, “surely not”) (9); γέ (G1065, “indeed”) (4) | μηδὲ Matthew 6:25 |
| 87 | 16 | אַתָּה (eH00301, “you”) | אֵת (H0853, “[Obj.]”) (71); אֵת (H0854, “with”) (11); אַנְתָּה (H0607, “you”) (4); אַנְתּוּן (H0608, “you”) (1) | אֹתְךָ Genesis 7:1 |
| 86 | 0 | יָכַל (eH00142, “to be able”) | נָכָה (H5221, “to smite”) (29); כָּלָה (H3615G, “to end: finish”) (19); יְכִל (H3202, “be able”) (9); כָּשַׁל (H3782, “to stumble”) (8) | וַיַּכֵּם Genesis 14:15 |
| 86 | 0 | עַד (eH00338, “until”) | עַד (H5705, “till”) (35); עַד (H5703, “perpetuity”) (23); בַּ֫עַד (H1157, “about/through/for”) (22); עַד (H5706, “prey”) (2) | עַד Ezra 4:21 |
| 85 | 5 | עָנָה (eH01234, “to answer”) | עָנָה (H6031B, “to afflict”) (44); עֲנָה (H6032, “to answer”) (24); יַעֲנָה (H3284, “ostrich”) (3); עָנַן (H6049B, “to divine”) (2) | וְעִנּוּ Genesis 15:13 |
| 84 | 0 | אָמַר (eH00018, “to say”) | אֲמַר (H0560, “to say”) (54); אֵמֶר (H0561, “word”) (12); אִמְרָה (H0565A, “word”) (11); אֹמֶר (H0562, “word”) (5) | אָמְרִין Ezra 5:3 |
| 83 | 4 | חָלַל (eH00479, “to profane”) | חָלַל (H2490H, “to profane/begin: profane”) (38); חָלַל (H2490C, “to profane/begin: begin”) (10); יָחַל (H3176H, “to wait: hope”) (6); חָלָה (H2470B, “to beg”) (5) | חִלַּלְתָּ Genesis 49:4 |
| 81 | 2 | יְהוָה (eH00154, “YHWH”) | יֵהוּא (H3058H, “Jehu”) (40); יְהֹוִה (H3069, “YHWH/God”) (35); יֵהוּא (H3058G, “Jehu”) (5); יֵהוּא (H3058I, “Jehu”) (1) | יֵהוּא 1 Kings 19:16 |
| 81 | 0 | יָדַע (eH00269, “to know”) | יְדַע (H3046, “to know”) (14); דַּ֫עַת (H1847, “knowledge”) (11); יָדָה (H3034, “to give thanks”) (11); אָמַר (H0559, “to say”) (6) | יָדְעֵי Ezra 7:25 |
| 79 | 36 | יָרָא (eH00295, “to fear”) | רָאָה (H7200G, “to see: see”) (55); יָרֵא (H3373, “afraid”) (14); רָעַע (H7489A, “be evil”) (5); רָאָה (H7200L, “to see: seer”) (2) | וַיֵּרָא Genesis 12:7 |
| 77 | 58 | קָרַב (eH01518, “to draw near”) | קֶ֫רֶב (H7130G, “entrails: among”) (35); קָרֵב (H7131, “approaching”) (10); קָרֹב (H7138, “near”) (7); קֶ֫רֶב (H7130H, “entrails: inner parts”) (7) | בְּקִרְבּֽוֹ Genesis 24:3 |
| 67 | 42 | בַּעַל (eH01134, “master, owner”) | בַּעַל (H1168A, “Baal”) (19); בַּ֫עַל חָנָן (H1177G, “Baal-hanan”) (4); בַּ֫עַל מְעוֹן (H1186, “Baal-meon”) (4); בַּ֫עַל פְּרָצִים (H1188, “Baal-perazim”) (4) | הַבְּעָלִֽים Judges 2:11 |
| 65 | 65 | כָּלָה (eH00592, “to finish”) | כְּלִי (H3627, “article/utensil”) (31); כָּלָא (H3607, “to restrain”) (11); כָּלָה (H3617, “consumption”) (9); כָּלַם (H3637, “be humiliated”) (5) | וּכְלִי Leviticus 6:21 |
| 64 | 10 | קָרָה (eH01148, “to meet”) | קִיר (H7023, “wall”) (11); קֶ֫רֶב (H7130G, “entrails: among”) (8); קָרָה (H7136A, “to meet”) (7); קֶ֫רֶן (H7161A, “horn”) (6) | קִיר Leviticus 1:15 |
| 63 | 55 | יוֹם (eH00027, “day”) | יוֹמָם (H3119, “by day”) (49); יוֹם (H3118, “day”) (10); לַ֫יְלָה (H3915, “night”) (3); יָוֵן (H3121, “mire”) (1) | יוֹמָם Exodus 13:21 |
| 63 | 0 | קֵץ (eH00571, “end”) | קֵץ (H7093, “end”) (35); קָצָה (H7098, “end”) (20); קַ֫יִץ (H7019, “summer”) (2); קְצָת (H7118, “end”) (2) | קֵץ Genesis 6:13 |
| 61 | 37 | αἰών (eG01095, “age, eternity”) | αἰώνιος (G0166, “eternal”) (61) | αἰώνιον Matthew 18:8 |
| 61 | 0 | הָיָה (eH00008, “was”) | הֲוָא (H1934, “to be”) (20); יֵשׁ (H3426, “there”) (17); אַ֫יִן (H0369, “nothing”) (11); הָוָה (H1933B, “to be”) (4) | הֱווֹ Ezra 4:22 |
| 61 | 0 | רָחַב (eH00589, “to be wide”) | רֹ֫חַב (H7341, “width”) (16); רָחַב (H7337, “to enlarge”) (16); רָחָב (H7342H, “broad: wide”) (6); רָחָב (H7343, “Rahab”) (5) | רָחְבָּהּ Genesis 6:15 |
| 61 | 0 | גָּדַל (eH00939, “to grow”) | נָגַד (H5046, “to tell”) (22); גָּדוֹל (H1419A, “great: large”) (17); גֹּ֫דֶל (H1433, “greatness”) (13); גָּדֵל (H1432, “growing”) (4) | וַנַגֶּד Genesis 43:7 |
| 61 | 0 | נָחַל (eH01467, “to inherit”) | נַ֫חַל (H5158A, “torrent: river”) (21); נוּחַ (H5117, “to rest”) (17); נַ֫חַל (H5158N, “torrent: valley”) (12); נָהָר (H5104H, “river”) (2) | הַנָּחַל Genesis 32:24 |
| 60 | 3 | קָדוֹשׁ (eH03644, “holy”) | קָדוֹשׁ (H6918G, “holy”) (54); קָדוֹשׁ (H6918H, “holy: saint”) (6) | קָדוֹשׁ Exodus 19:6 |
| 58 | 0 | חָטָא (eH01394, “to sin”) | חַטָּאת (H2403B, “sin”) (38); חֲטָאָה (H2401, “sin”) (6); חֵטְא (H2399, “sin”) (2); חַטָּאת (H2403H, “sin: sin offering”) (2) | וְחַטָּאתָם Genesis 18:20 |
| 57 | 0 | חָרַב (eH00694, “to destroy”) | חׇרְבָּה (H2723, “desolation”) (16); חָרֵב (H2717B, “to destroy”) (14); חָרֵב (H2717A, “to dry”) (11); חָרֵב (H2720B, “desolate”) (8) | חָרְבָּה Leviticus 26:31 |
| 56 | 101 | שָׁלַח (eH00354, “to send”) | שָׁלַךְ (H7993, “to throw”) (42); שֶׁ֫לַח (H7974, “Shelah”) (7); שְׁלַח (H7972, “to send”) (3); שֶׁ֫לַח (H7973, “missile”) (3) | וַתַּשְׁלֵךְ Genesis 21:15 |
| 56 | 0 | כָּל (eH00097, “all”) | כֹּל (H3606, “all”) (26); /ל (H9005, “to/for”) (22); אַ֫יִן (H0369, “nothing”) (3); כָּלָה (H3615G, “to end: finish”) (1) | כָּל Ezra 6:12 |
| 56 | 0 | קָדַם (eH00212, “before”) | קֶ֫דֶם (H6924H, “front: old”) (17); קָדַם (H6923, “to meet”) (16); קֶ֫דֶם (H6924A, “East”) (6); קִדְמָה (H6926, “east”) (4) | קֶדֶם Deuteronomy 33:15 |
| 55 | 97 | שָׁבַב (eH00340, “to return”) | יָשַׁב (H3427, “to dwell”) (27); שָׁבָה (H7617, “to take captive”) (15); שׁוֹבֵב (H7728, “backsliding”) (3); שִׂיב (H7867, “be gray”) (2) | שֵֽׁב Genesis 20:15 |
| 55 | 33 | יָסַר (eH00695, “to remove, to uncover”) | יָסַר (H3256, “to discipline”) (29); אָסַר (H0631, “to bind”) (11); סָתַר (H5641, “to hide”) (9); יָסַף (H3254G, “to add: again”) (1) | לְיַסְּרָה Leviticus 26:18 |
| 55 | 0 | גָּבַר (eH00643, “man”) | גְּבוּרָה (H1369, “might”) (22); גָּבֶר (H1397, “great man”) (18); גִּבּוֹר (H1368, “mighty man”) (8); גְּבִיר (H1376, “lord”) (2) | וְכִגְבוּרֹתֶֽךָ Deuteronomy 3:24 |
| 54 | 172 | עֵץ (eH00058, “tree”) | עָלָה (H5927G, “to ascend: rise”) (34); עָצָב (H6091, “idol”) (7); עָלֶה (H5929, “leaf”) (4); יַ֫עַר (H3293A, “wood”) (4) | עֲלֵה Genesis 35:1 |
| 54 | 0 | שָׁנָה (eH00073, “year”) | לָשׁוֹן (H3956G, “tongue”) (18); שָׁנָה (H8138A, “to change”) (10); שָׁנָה (H8138B, “to repeat”) (5); שֵׁנָה (H8142, “sleep”) (3) | לְשֹׁנוֹ Exodus 11:7 |
| 54 | 0 | מוֹת (eH00223, “death”) | מָ֫וֶת (H4194, “death”) (53); הָמָה (H1993, “to roar”) (1) | בְּמוֹת Genesis 21:16 |
| 53 | 85 | שָׁמַע (eH00288, “to hear”) | שֵׁ֫מַע (H8088B, “report”) (10); קָשַׁב (H7181, “to listen”) (9); שָׁמֵם (H8074H, “be desolate: appalled”) (7); שְׁמַע (H8086, “to hear”) (6) | שֵׁמַע Genesis 29:13 |

## Homographs: one spelling, more than one word

The reference tags each occurrence; we answer once per spelling, so these are lost whatever
the model knows. The parse (step 2) works word by word in its verse and can recover them.

| words off | spelling | reference words (words) |
|---|---|---|
| 509 | בֵּית | בַּ֫יִת (H1004M, “house: household”) (275); בַּ֫יִת (H1004Q, “house: temple”) (241); בַּ֫יִת (H1004B, “house: home”) (146); בַּ֫יִת (H1005, “house”) (17) |
| 456 | אִישׁ | אִישׁ (H0376G, “man”) (610); אִישׁ (H0376I, “man: anyone”) (448); אִישׁ (H0376H, “man: husband”) (5); אִישׁ־בֹ֫שֶׁת (H0378, “Ish-bosheth”) (3) |
| 451 | ὅτι | ὅτι (G3754G, “that/since: that”) (826); ὅτι (G3754H, “that/since: since”) (451) |
| 331 | בְּנֵי | בֵּן (H1121G, “son: descendant/people”) (783); בֵּן (H1121A, “son: child”) (271); בֵּן (H1121H, “son: young animal”) (20); בֵּן (H1121I, “son: type of”) (17) |
| 314 | אִם | אִם (H0518A, “if”) (434); [כִּי] אם (H0518B, “if: except”) (141); אִם (H0518H, “if: surely no”) (85); אִם (H0518I, “if: surely yes”) (70) |
| 232 | אֶת | אֵת (H0853, “[Obj.]”) (6249); אֵת (H0854, “with”) (232) |
| 212 | בֶּן | בֵּן (H1121A, “son: child”) (983); בֵּן (H1121L, “son: aged”) (101); בֵּן (H1121G, “son: descendant/people”) (40); בֵּן (H1121H, “son: young animal”) (33) |
| 169 | פְּנֵי | פָּנֶה (H6440J, “face: surface”) (91); פָּנֶה (H6440G, “face: before”) (90); פָּנֶה (H6440H, “face”) (47); פָּנֶה (H6440L, “face of”) (16) |
| 161 | הַיּוֹם | יוֹם (H3117G, “day”) (252); יוֹם (H3117L, “day: today”) (155); יוֹם (H3117J, “day: daily”) (4); יוֹם (H3117K, “day: always”) (2) |
| 141 | כִּי | כִּי (H3588A, “for”) (2775); כִּי [אם] (H3588B, “that if: except”) (137); כִּי [עַל כֵּן] (H3588C, “for as that: since”) (3); כִּי (H3587, “branding”) (1) |
| 117 | וַיַּעַשׂ | עָשָׂה (H6213H, “to make”) (117); עָשָׂה (H6213A, “to make: do”) (113); עָשָׂה (H6213I, “to make: offer”) (4) |
| 117 | עָשָׂה | עָשָׂה (H6213A, “to make: do”) (208); עָשָׂה (H6213H, “to make”) (106); עָשָׂה (H6213I, “to make: offer”) (11) |
| 113 | εἰ | εἰ (G1487G, “if”) (253); εἰ (G1487H, “if: not”) (80); εἰ (G1487M, “if: even though”) (14); εἰ (G1487L, “if: else”) (9) |
| 111 | בְּיַד | יָד (H3027H, “hand: power”) (127); יָד (H3027J, “hand: by”) (64); יָד (H3027G, “hand”) (31); יָד (H3027K, “hand: to”) (13) |
| 107 | תַּחַת | תַּחַת (H8478G, “underneath: under”) (131); תַּחַת (H8478H, “underneath: instead”) (75); תַּחַת (H8478J, “underneath: because of”) (18); תַּחַת (H8478L, “underneath: swear”) (4) |
| 106 | דִּבְרֵי | דָּבָר (H1697G, “word”) (132); דָּבָר (H1697K, “word: deed”) (57); דָּבָר (H1697O, “Chronicles”) (34); דָּבָר (H1697I, “word: thing”) (7) |
| 99 | הַדָּבָר | דָּבָר (H1697I, “word: thing”) (112); דָּבָר (H1697G, “word”) (78); דָּבָר (H1697J, “word: promised”) (7); דָּבָר (H1697M, “word: because”) (5) |
| 98 | דֶּרֶךְ | דֶּ֫רֶךְ (H1870J, “way: direction”) (54); דֶּ֫רֶךְ (H1870K, “way: road”) (46); דֶּ֫רֶךְ (H1870G, “way: conduct”) (28); דֶּ֫רֶךְ (H1870L, “way: journey”) (23) |
| 95 | וַיִּקְרָא | קָרָא (H7121G, “to call: call to”) (106); קָרָא (H7121H, “to call: call by”) (64); קָרָא (H7121I, “to call: call out”) (22); קָרָא (H7121J, “to call: read out”) (9) |
| 95 | מִפְּנֵי | פָּנֶה (H6440G, “face: before”) (87); פָּנֶה (H6440I, “face: because”) (71); פָּנֶה (H6440L, “face of”) (20); פָּנֶה (H6440H, “face”) (4) |
| 93 | פַּרְעֹה | פַּרְעֹה (H6547J, “Pharaoh”) (71); פַּרְעֹה (H6547H, “Pharaoh”) (45); פַּרְעֹה (H6547R, “Pharaoh”) (13); פַּרְעֹה (H6547K, “Pharaoh”) (11) |
| 92 | אֵל | אֵל (H0410G, “God”) (122); בֵּֽיתְ־אֵל (H1008G, “Bethel”) (61); אֵל (H0410K, “god”) (14); עֲשָׂהאֵל (H6214G, “Asahel”) (5) |
| 83 | וּבְנֵי | בֵּן (H1121A, “son: child”) (121); בֵּן (H1121G, “son: descendant/people”) (74); בֵּן (H1121I, “son: type of”) (4); בֵּן (H1121H, “son: young animal”) (3) |
| 81 | רֹאשׁ | רֹאשׁ (H7218A, “head”) (65); רֹאשׁ (H7218I, “head: top”) (38); רֹאשׁ (H7218H, “head: leader”) (25); רֹאשׁ (H7218L, “head: count”) (6) |
| 79 | קוֹל | קוֹל (H6963A, “voice”) (79); קוֹל (H6963H, “voice: sound”) (65); קוֹל (H6963J, “voice: message”) (7); קוֹל (H6963K, “voice: [sound of]”) (6) |
| 78 | רוּחַ | רוּחַ (H7307G, “spirit”) (95); רוּחַ (H7307H, “spirit: breath”) (64); רוּחַ (H7307J, “spirit: temper”) (5); רוּחַ (H7308, “spirit”) (5) |
| 73 | מִן | מִן־ (H4480A, “from”) (609); מִן־ (H4481, “from”) (73) |
| 71 | טוֹב | טוֹב (H2896A, “pleasant”) (165); טוֹב (H2896B, “good”) (44); טוֹב (H2895, “be pleasing”) (24); טוֹב (H2897, “Tob”) (3) |
| 70 | אֱלֹהִים | אֱלֹהִים (H0430G, “God”) (537); H0430J (70) |
| 69 | נֶפֶשׁ | נֶ֫פֶשׁ (H5315J, “soul: person”) (39); נֶ֫פֶשׁ (H5315H, “soul: life”) (30); נֶ֫פֶשׁ (H5315G, “soul”) (15); נֶ֫פֶשׁ (H5315K, “soul: animal”) (12) |
| 68 | עַל | עַל (H5921A, “upon”) (3346); עַל (H5922, “since”) (54); [כִּי] עַל [כֵּן] (H5921B, “as”) (9); עֲלַל (H5954, “to come”) (4) |
| 68 | וַיִּתֵּן | נָתַן (H5414G, “to give: give”) (82); נָתַן (H5414H, “to give: put”) (56); נָתַן (H5414I, “to give: make”) (6); נָתַן (H5414O, “to give: give(marriage)”) (2) |
| 66 | רָעָה | רָעָה (H7451I, “distress: evil”) (42); רָעָה (H7451C, “distress: harm”) (41); רַע (H7451A, “bad: harmful”) (19); רַע (H7451H, “bad: evil”) (4) |
| 65 | וְאִישׁ | אִישׁ (H0376G, “man”) (70); אִישׁ (H0376I, “man: anyone”) (65) |
| 64 | אִשָּׁה | אִשָּׁה (H0802G, “woman”) (74); אִשָּׁה (H0802H, “woman: wife”) (50); אִשָּׁה (H0802I, “woman: another”) (14) |
| 63 | לָךְ | ךְ (H9032, “you”) (159); ךָּ (H9031, “you”) (63) |
| 60 | אַף | אַף (H0637, “also”) (105); אַף (H0639G, “face: anger”) (58); אַף (H0639H, “face: nose”) (2) |
| 59 | לֶחֶם | לֶ֫חֶם (H3899H, “food: bread”) (118); לֶ֫חֶם (H3899G, “food”) (34); בֵּית לֶ֫חֶם (H1035G, “Bethlehem”) (22); לֶ֫חֶם (H3899I, “food: allowance”) (3) |
| 59 | יָדוֹ | יָד (H3027G, “hand”) (94); יָד (H3027H, “hand: power”) (24); יָד (H3027I, “hand: themselves”) (19); יָד (H3027T, “hand: expend”) (5) |
| 59 | נַפְשִׁי | נֶ֫פֶשׁ (H5315G, “soul”) (85); נֶ֫פֶשׁ (H5315H, “soul: life”) (31); נֶ֫פֶשׁ (H5315I, “soul: myself”) (25); נֶ֫פֶשׁ (H5315L, “soul: appetite”) (3) |
