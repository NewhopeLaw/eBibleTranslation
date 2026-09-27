# Emma Htoo's Karen: pronunciation and phonics notes

Emma Htoo's course "Learn the Karen Language" (YouTube, 16 lessons) teaches
a Karen speaker's reading of the script to Karen children abroad. She says
every letter's sound several times on its own, which is the cleanest kind of
evidence a spelling-to-sound table can have, and the cuts of her saying them
are in `audio/cuts/emma_*` (not in git) with their index in `words/`.

Each lesson is digested on its own: frames tiled from the video say what is on
screen when, the automatic captions say what she said in English and how an
English ear heard her Karen, and the loud stretches between her English are
her Karen sounds. "Heard as" below is YouTube's English speech recogniser
mishearing her Karen, which is a crude phonics note of its own: it says which
English sound a listener with no Karen reaches for.

## Lesson 1: the 25 consonants (o8u-xNHviDg, 12:41)

Karen has 25 letters, she says, and she reads them in the order of the chart
(five rows of five); the chart is on screen from 2:00, then one letter at a
time from 3:48 to 11:12. Our table's value is beside hers; where they differ
it is marked.

| letter | our IPA | heard as (auto-captions) | her remark | sound cuts | time |
|---|---|---|---|---|---|
| က | k | "gah" | first letter; unaspirated k, which an English ear hears as g | 5 | 3:48 |
| ခ | kʰ | "cut", "kaw" | aspirated | 10 | 4:04 |
| ဂ | ɣ | "go", "he" | voiced fricative; she names it with a longer descriptive name | 7 | 4:28 |
| ဃ | x | "gah" | close to က to the recogniser; a velar fricative | 9 | 4:52 |
| င | ŋ | "nah" | "like the -ng at the end of sing, only the ng part" | 8 | 5:12 |
| စ | s | "sap", "sad" | she gives a descriptive name ("because it's round we call it ...") | 7 | 5:36 |
| ဆ | sʰ | "hop", "be sad" | aspirated s; the recogniser hears an h | 5 | 6:00 |
| ၡ | ʃ | "sha" | the letter Karen added to the Burmese set | 3 | 6:16 |
| ည | ɲ | "yeah", "nya" | palatal nasal | 3 | 6:32 |
| တ | t | "does he", "that was" | unaspirated t, heard as d | 2 | 6:48 |
| ထ | tʰ | "ha", "sadly" | "because it's two of them, it's twin, so we call it ..." | 6 | 7:12 |
| ဒ | d | "duh" | "this one looks like number three but we pronounce it duh" | 7 | 7:32 |
| န | n | "na" | | 5 | 7:52 |
| ပ | p | "but", "pat" | unaspirated p, heard as b | 0 clean | 8:08 |
| ဖ | pʰ | "pat", "paths" | aspirated | 7 | 8:24 |
| ဘ | b | "back" | voiced | 4 | 8:40 |
| မ | m | "ma", "my" | | 6 | 8:52 |
| ယ | j | "yeah" | | 3 | 9:08 |
| ရ | r | "rah", "rocky" | a real r, trilled or tapped | 8 | 9:20 |
| လ | l | "la", "like" | | 4 | 9:40 |
| ဝ | w | "wow", "wacka" | "it looks like an O" | 7 | 9:52 |
| သ | θ | "that", "stop that" | the th of "that" to the recogniser; Thai-side Karen say s | 0 clean | 10:08 |
| ဟ | h | "ha" | | 4 | 10:20 |
| အ | ʔ | "ah" | the glottal onset; "kiss her" is her descriptive name | 4 | 10:36 |
| ဧ | ɦ | "good", "ee" | the last letter; rare; a breathy h or a vowel onset | 8 | 10:56 |

What lesson 1 settles: the consonant table agrees with hers throughout, and the
recogniser's mishearings confirm the aspiration contrasts (က heard as g and ခ
as k; တ as d and ထ as t or h; ပ as b and ဖ as p). The two letters with no clean
cut, ပ and သ, were said over her own English and can be taken from lesson 2.

Her descriptive letter names ("go war cat", "does he", "back to cool" as the
recogniser heard them) are the traditional Karen names of the letters, like
Burmese "ka-gyi, kha-gway"; they are not the sounds and are not used here.

## Lesson 3: the nine vowels (a_0j53ep4VY, 5:33)

She carries each vowel sign on အ, "the circle that says ah", and shows the
sum: အ + sign = syllable. Her order, the sign, our value, and a rough
formant reading of her cuts (first and second formant in Hz, the median over
her repetitions, from a plain LPC, so a check on the table rather than a
measurement to quote):

| order | sign | written | our IPA | her cuts | F1, F2 | reads as |
|---|---|---|---|---|---|---|
| 1 | ၢ | အၢ | ə | 5 | unreliable | a short central vowel; the recogniser heard "ee" |
| 2 | ံ | အံ | i | 3 | 331, 2900 | a clear high front i, as the table says (not a nasal, as in Burmese) |
| 3 | ါ | အါ | a | 7 | unreliable | open a |
| 4 | ု | အု | ɨ | 7 | 440, 2519 | high and central-to-front: ɨ, not Burmese u |
| 5 | ူ | အူ | u | 10 | 420, 1731 | high back u |
| 6 | ့ | အ့ | e | 6 | 472, 2727 | mid front e: a vowel sign in Karen, not the Burmese creaky-tone dot |
| 7 | ဲ | အဲ | ɛ | 8 | 473, 2665 | open-mid front; the recogniser heard "ay" |
| 8 | ိ | အိ | o | 9 | 484, 1161 | mid back rounded o, not Burmese i |
| 9 | ီ | အီ | ɔ | 6 | 1070, 2170 | open back; consistent with ɔ ("K'nyaw") |

What lesson 3 settles: the three places where Karen reuses a Burmese sign
with a different sound, ိ as o, ီ as ɔ and ံ as i, are exactly as the table
has them, and ့ is a vowel. The order she teaches (ၢ ံ ါ ု ူ ့ ဲ ိ ီ) is the
traditional Karen vowel order and is kept in the notes.

## Lesson 4: "another five vowels", which are the five tone marks (dQGvZ3G7K4U, 3:20)

Karen literacy counts the tone marks among the vowels, and this lesson is the
five of them: ၢ် ၤ း ၣ် ာ်, each on screen alone while she says it several
times, then "two that almost sound alike, one without a leg and one with",
which are ၤ and ၣ် (the same S-shape, ၣ် with a descender), then two
"complete sounds". The syllable she says them on is not on screen, so what
can be measured is the pitch movement, not the vowel: her pitch over each
repetition, in semitones from her own middle (212 Hz), averaged.

| mark | Wade 1861 | her cuts | start, mid, end | length s | what her voice does |
|---|---|---|---|---|---|
| ၢ် | heavy falling | 6 | +0.8, +0.2, -0.8 | 0.65 | level at the middle, a slight fall, and the longest of the five |
| ၤ | prolonged, even | 6 | +1.8, -2.4, -1.1 | 0.43 | falls from above the middle to below it; short, not prolonged |
| း | abrupt, at ordinary pitch | 5 | -3.0, +1.0, +5.7 | 0.45 | a strong rise from low to high |
| ၣ် | falling circumflex | 6 | -2.7, -0.1, -0.1 | 0.52 | rises from low to the middle and stays |
| ာ် | abrupt, low | 4 | +0.5, +1.8, +1.1 | 0.52 | a little above the middle, level |

Three independent readings now agree and Wade's words do not: ၤ falls, ၣ်
rises from low, း rises steeply. The vocabulary speaker's words with those
final tones move the same way, and the Vietnamese tone that fitted each best
in the Piper voice was the falling huyền for ၤ and the rising ngã and sắc for
ၣ် and း. Wade may have heard an older or a different Karen; the modern
speakers are what the voice must copy. Four to six repetitions each is still
thin, and her carrier syllable is unknown, so these are the working curves
until the syllabary has hundreds of words per tone.

Not yet measured: the unmarked syllable (Wade: rising), which she does not
demonstrate alone here.

## Lesson 5: "five vowels, part III", which are the five medials (aeKedX1LUPc, 5:23)

The chart on screen pairs each medial sign with the letter it is made from
(literally "ဂ, its tool-form ှ" and so on): ဂ → ှ, ယ → ၠ, ရ → ြ, လ → ျ,
ဝ → ွ. That is the table as karen_phonemes has it: ှ is /ɣ/, ၠ is /j/, ြ is
/r/, ျ is /l/ (Wade) or /j/ in most speakers today, ွ is /w/. She then
writes example syllables by hand beside each; at the 240-pixel download
those are not legible, and her captions for this lesson are still held by
YouTube's rate limit, so her pronunciation of ျ, the one medial whose
modern value is in question, waits for the captions or a sharper copy.

## Lesson "3" (video 8): consonants with the three tone marks ၢ် ၣ် ၤ (QxDGlLCV0zs, 11:27)

A table of 14 consonants (က ခ ဂ စ ဆ တ ဒ / န ပ ဖ ဘ မ ရ ဝ), each with the
three marks, 42 syllables, and she reads every cell while a blue highlight
sits on it. The highlight was tracked frame by frame, so every cell has its
time, and the syllable cuts inside each cell's time (away from her English,
by the captions) are labelled with certainty: the same consonant, the same
vowel, only the mark differing. 276 clean cuts, about a hundred per mark,
her middle pitch 217 Hz:

| mark | cuts | start, mid, end (semitones) | length s | on a fixed carrier |
|---|---|---|---|---|
| ၢ် | 101 | +0.4, -0.5, -1.0 | 0.31 | a slight fall through the syllable |
| ၣ် | 94 | +0.4, +0.8, +0.1 | 0.31 | rises a little, then settles back |
| ၤ | 81 | +0.9, +0.4, -0.3 | 0.41 | level, and a third longer than the others |

The spread of the fall across cuts is about four semitones for each mark, so
the differences between marks are smaller than the variation within one, and
on an isolated syllable the marks are told apart at least as much by length
and voice quality as by pitch. This is the most trustworthy tone measurement
in these notes (fixed carrier, many repetitions, one speaker), and it sits
nearer Wade's "prolonged, even" for ၤ and "falling" for ၢ် than lesson 4's
windows did, whose larger movements probably came from different carrier
words and sentence intonation. The tone table carries these three; ာ်, း
and the unmarked syllable still rest on the smaller samples.

The lesson's five bonus phrases (good evening; close or turn off; can you
please close the door; can you turn off the light before you go to bed; can
you go and get me a cup of water) are in her captions with times but their
Karen is not on screen in a form the download can read.

## Lesson "4" (video 9): two-syllable words (-JwdOGfb0rE, 7:26)

Eight words, each sounded out letter by letter under a pink highlight and
then said whole: တနၢ်, တတၢ်, ကတၢ်, ကနၣ်, သရၣ် (teacher), ကမၣ်, သမၣ်, ဟးသဒၣ်.
The highlight gives each word its half-minute; the whole-word sayings come
in the latter part of it, and 15 of them were cut with their spelling (six
of တနၢ်, none of three words whose windows were all sounding-out). The
first two-syllable blocks in the cuts, and the first with the reduced first
syllable (တ-, က-) that so much Karen vocabulary begins with.

## Lesson "5" (video 10): consonants with the vowel ံ and the marks း and ၢ် (3ugSu3RcZ8M, 26:41)

Thirty syllables built on screen, "က + ံ = ကံ", then with း and with ၢ်,
across fourteen consonants, each screen up to a minute and a half of her
saying it and sounding it out; the screens were found by frame change and
read from a sheet. 439 cuts labelled by screen (noisier than the tone table
of video 8: a window that long holds letter names too), her middle 218 Hz:

| mark | cuts | start, mid, end (semitones) | length s | on the vowel i |
|---|---|---|---|---|
| unmarked | 113 | +0.9, -0.5, +0.0 | 0.41 | level |
| း | 65 | -0.3, -0.4, -1.6 | 0.31 | a little low and falling, and the shortest: "abrupt" is right |
| ၢ် | 261 | +0.8, +0.0, +0.3 | 0.40 | level |

The first measurement of the unmarked syllable: level, not Wade's "rising".
The bonus words are family terms: ဖံဖံ grandmother, ဖုဖု grandfather, မိမိ
mother, ပါပါ father, and the step-parent terms.

## Lesson "6" (video 11): the whole tone paradigm on eighteen consonants (JoGf8QF0o0g, 29:38)

Six screens of three consonants each (က ခ ဂ / ဃ စ ဆ / ၡ ည တ / ထ ဒ န /
ပ ဖ ဘ / လ ဝ သ), every consonant in all six tone forms on the vowel a:
ကါ ကၢ် ကာ် ကး ကၣ် ကၤ. Her mouse pointer rests on each cell as she says it,
and tracking the pointer gave 143 timed cells covering 87 of the 108
syllables, 236 clean cuts. The first time all six tones were measured on
one speaker, one vowel, in one sitting; her middle 203 Hz:

| form | mark | cuts | start, mid, end (semitones) | length s | where it sits |
|---|---|---|---|---|---|
| ကၣ် | ၣ် | 28 | +0.1, +1.2, +0.7 | 0.34 | the highest: up and a little down |
| ကၢ် | ၢ် | 71 | +0.5, +0.6, +0.2 | 0.36 | high and level |
| ကၤ | ၤ | 29 | -0.0, -0.6, -1.0 | 0.41 | mid, drifting down, long |
| ကး | း | 49 | +0.4, -0.6, -1.3 | 0.35 | mid falling, short |
| ကါ | none | 20 | -1.4, -1.0, -0.7 | 0.43 | low and level, long |
| ကာ် | ာ် | 39 | -1.0, -1.3, -1.6 | 0.42 | the lowest, falling |

The whole range is under three semitones, which is how flatly she says
isolated syllables, but the order is clear and is the one the table now
carries: ၣ် above ၢ် above ၤ and း in the middle, the unmarked syllable and
ာ် at the bottom. Against Wade: ၤ is indeed the long even one and ာ် the low
one; ၣ် and ၢ် are his two high tones; the unmarked syllable is low and
level here, not rising; း is short, as "abrupt" says, but falls rather than
holds. Length separates them as much as pitch: ၤ, unmarked and ာ် long, the
other three short.

## Lesson "7" (video 12): seventeen words and short phrases (AsQdO1ExyPg, 14:39)

A list in three columns, each item turning yellow as she reaches it (and
staying yellow, so the newest yellow is the one she is on): တကံ, ပှဝံ (reading
uncertain), သဒံ, အဒံး, အဆံး, ပအံ; အဂံၢ်, အတၢ်, အကံၢ်, ထံးတၢ်, ဆံးစၢ်, စၢ်ယၤ;
ပတဘၣ်ဟး, ပဘၣ်မံသး, ယဖါတံၢ်ဟး, ယဂံၢ်ယဘါ, အဂံၢ်ထံးအါ. Half a minute to a
minute each; 102 cuts of whole words and phrases, the first connected
speech in the cuts with certain spellings (the four-syllable phrases are
short sentences: "we must not go", "we must sleep", "my uncle goes").

## Lesson "8" (video 13): eighteen words, mostly with the vowel ံ (ElD0-18-zxM, 16:32)

The same three-column list with an accumulating yellow highlight: တယၢ်,
ကတၢ်, ဝံလံး, ထးရံး, ဝံၣ်တရံး, နံၣ်ကံၣ်; တၢ်တၢ်, သံၣ်တံၢ်, တနံၤအံၤ (today),
ဘၣ်ဖးလံာ် (must read), ကရံၣ်ဒံၣ်, ယဟံၣ်အံၣ်; ယလံာ်သးဝံၣ် (my hymn book),
သးဝံၣ်ဒံအံၤ, တဝံဒံးဘၣ်, တနံၣ်တလါ (a year and a month), ကယံာ်တနံၣ်,
ဒံသၣ်အံၤဝံၣ်. Six readings are marked uncertain at this resolution and their
cuts unconfirmed. 246 cuts, the second half of the lesson a review that
gave each word a second window.

## Lesson "9" (video 14): ten consonants with the vowel ၢ (ə) in three tones (4JTFL3YZOYk, 8:54)

ကၢ ကၢး ကၢၢ် and so on for က ခ ဂ ဃ င ဒ ပ မ ထ ရ, each cell turning yellow as
she reaches it: all 30 syllables timed, 239 cuts. On the vowel ə: the
unmarked syllable low again (-1.1 to +0.2 semitones), း and ၢ် around the
middle, all about 0.38 s. The vowel ၢ is the one Burmese lacks and the
Vietnamese voice cannot say; these cuts are its only source.

## Lesson "10" (video 15): fourteen words, most with the vowel ၢ (hKNvy6vM5RE, 11:09)

A four-column list (စၢယာ်, ပၢၢ်ဆၢ, တၢၢ်နၢ, တၢၢ်ဆံၣ်; လၢၢ်ဆံၣ်, ပၢၢ်တကါ,
ကၢၢ်ပၤနံၤ, ဂၢၢ်တပၢၢ်; စၢၢ်တလၢၢ်, အၢကတၢၢ်, ပဆံတဟၢ, တမံဒံးဘၣ်; တဘၣ်အခး,
ကလံၤတဂၢၢ်) and vegetable names as the bonus (cabbage တဘၣ်ဘီၣ်ခိၣ်, spinach,
spring onion). At this resolution ၢ and ၢၢ် are hard to tell apart, so only
four readings are marked certain and the rest of the 204 cuts unconfirmed:
they serve the syllabary and the hybrid voice, not the training set, until a
Karen reader confirms the spellings.

## Lesson "11" (video 16): eleven consonants with ာ်, ၣ် and ၤ (4TKOpmwpr-Q, 12:54)

ကာ် ကၣ် ကၤ and so on for က ခ ဂ စ ထ န and ပ ဘ မ ယ လ, with a selection box
as her cursor; the box was found in 14 of the 33 cells, 91 cuts, her middle
189 Hz. On the vowel a again: ာ် low then rising at the end (+1.4), ၣ် from
above the middle down, ၤ from high down and the longest of the three
(0.42 s) - the same relative order as in the full paradigm of video 11.

## Lesson "1" (video 6): every consonant with း and with ါ (JQo2_YcUFXY, 11:48)

Two tables of 25: ကး ခး ဂး ... and ကါ ခါ ဂါ ..., every consonant with the
short း form and with the plain ါ form. Her cursor here is a text I-beam,
found by its difference from the page; 39 of the 50 cells timed, 239 cuts.
Its captions came through on a later retry, so her English is filtered
and the cuts confirmed. What the pair
shows across all 25 consonants: ကါ 0.53 s, ကး 0.33 s, the pitch nearly the
same. The plain syllable is long and the း syllable short: "abrupt" is a
length, not a pitch.

## Lesson "2" (video 7): twelve words with the reduced first syllable (4xE8uZMfyyc, 8:47)

ကဖး, တဟး, တခး, တဝး; တဆါ, ယဘါ, မဟါ, မဆါ; တကလး, တကဒါ, တကသါ, ယတဟးခး - words
whose first syllable is the light တ-, က-, ယ-, မ- prefix that so much Karen
vocabulary carries, half a minute each under a blue selection box. 74 cuts
with certain spellings and her English filtered by the captions; the
two-syllable blocks for the syllabary.

## The alphabet again (video 2, xpS4YW50cCw, 7:20)

The 25 letters one per screen in alphabet order, as in video 1, at a
faster pace; the screens found by frame change match the order exactly.
150 cuts of her letter sounds, unconfirmed only because this lesson's
captions are still held back and her English between the sounds could not
be filtered out.

That completes her course: all sixteen lessons digested, one at a time,
from the alphabet through the vowels, medials and tones to words and
phrases, 2,391 cuts of her and the vocabulary speaker in all.
