# eBible Android wrapper

A WebView around `site/index.html`. The whole reader - text, morphology,
lexicon, themes, parallels - is in the APK, and the app asks for no
permissions at all, the INTERNET one least of any: nothing is fetched and
nothing is reported back.

Before building, `python scripts/build_encoder.py` makes the search model and
its verses in `site/model/` (gitignored); without it the APK searches by
meaning with the page's table alone.

## The reader APK, in one step

`python scripts/build_apk.py` - or **Make Android APK** in the PC dashboard - builds the reader-only page (`build_site.py --reader-only`: always
basic mode, no study layers), stages it with the search indexes in
`reader-assets/`, runs Gradle with `-PappAssets` pointing there, and copies
the APK to `dist/`. The full build's `app/src/main/assets/` is not touched.
Each build gets a version code that rises by the minute, so a new APK installs
over the last one.

It finds a JDK 17, the SDK and Gradle where Android Studio or its own
`--setup` put them; `--setup --accept-android-sdk-license` fetches all three
into `tools/android/`. With `keystore.properties` present it makes a signed
release; without, a debug build.

## Building the full app

Needs the Android SDK (platform 36), JDK 17 and Gradle 8.13 or later. There is
no Gradle wrapper committed - generating one means committing the wrapper jar,
and a binary in this repository would have to be taken on trust. Android Studio
supplies its own; on the command line, `gradle wrapper` once in this folder
makes a local one that is gitignored along with the rest of the build.

```sh
./sync_assets.sh              # copy the current site/ into app/src/main/assets/
gradle assembleDebug          # APK in app/build/outputs/apk/debug/
gradle bundleRelease          # AAB in app/build/outputs/bundle/release/ - what Play takes
```

The assets are not in git: they are a second copy of `site/`, and eighty
megabytes of it. `sync_assets.sh` puts them there, refuses a page too small to
be a full reader, and the build stops with the same advice if the folder is
empty.

After translating more chapters: re-run `scripts/build_site.py` **on the PC**
(see the root `CLAUDE.md` - a site built anywhere else holds only the chapters
that checkout happens to have), then `./sync_assets.sh`, then rebuild. Bump
`versionCode` in `app/build.gradle` for every upload; `versionName` is what the
listing shows.

### Signing

`app/build.gradle` reads `android/keystore.properties`, which is gitignored,
and leaves the release unsigned when it is absent so that anyone can still
build a debug APK. To set it up on the release machine:

```sh
keytool -genkeypair -v -keystore ~/keys/ebible-release.jks \
        -alias ebible -keyalg RSA -keysize 4096 -validity 10000
cp keystore.properties.example keystore.properties    # then fill it in
```

`storeFile` in `keystore.properties` must be written out in full: Gradle does
not expand `~` the way the shell did for `keytool`.

Keep the keystore and its passwords off this repository and backed up
somewhere else; Play signs the delivered app with its own key, but an upload
key that is lost has to be reset with Google before another release can go up.

## What the shell decides, and why

- **Insets.** The window draws edge to edge and the content is padded by the
  insets the system reports - bars, cutout, keyboard - so the page never has to
  guess. The insets are consumed there rather than passed on, so the page's own
  `safe-area` CSS reads zero and does not pad a second time.
- **Colour.** After every load, on returning to the app, and just after every
  tap or key, the shell asks the page what colour it actually painted
  (`meta[name=theme-color]`, or the body background) and gives the window and
  the bar icons the same. The taps are what catch the reader's own colour
  choice - sepia, dark, true black - which changes the page without a load.
  That keeps them one surface even where the page and the phone disagree about
  dark mode.
- **Dark mode.** From Android 13 the page's `prefers-color-scheme` follows the
  phone's setting through the WebView by itself. Below that it does not, and
  the app would need `androidx.webkit` to make it; for now an older phone in
  dark mode gets the page's light palette, and the bars follow the page rather
  than the system so nothing looks half-converted.
- **Text size.** `setTextZoom` is never called. Left alone the WebView already
  scales text by the phone's own font-size setting, which is what a reader who
  has enlarged everything expects; the page's own +/- then moves up and down
  from there. The system scale wins the argument, and the page adjusts within
  it.
- **Zoom.** Pinch zoom stays on with the +/- overlay hidden - it covers the
  text, and a pinch does the same job.
- **Back.** The system back button asks the page, because the reader keeps a
  trail of themes and lexicon entries that have no address of their own. It
  closes a popup first, then calls the page's `canGoBack()` and `goBack()`
  (which close an open tray before moving), and leaves the app when the page
  says there is nowhere to go. The WebView's own history is never walked: it
  holds every chapter address the trail re-enters on its way back, and walking
  it fed the trail again, so back could never leave. Because the answer comes
  from JavaScript, the back callback is always registered and the predictive
  gesture shows no preview of the home screen; that is the documented cost of
  deciding in the page. What the page puts away, in order, is the verses it is
  holding, a popup, a tray, and a page drawn over a chapter; chapter after chapter is not
  a stack to climb down on a phone, so from a plain chapter the page says it
  has nothing left. The first press then says "press back again to leave" and
  the second one leaves - the convention is to leave at once, but a reader deep
  in a chapter should not lose their place to a stray touch.
- **What the page cannot do alone.** The WebView has no speech, no clipboard a
  reader would expect, and no share sheet, so the shell exposes those three to
  the page as `AndroidApp` (see the `Bridge` class): speak a passage, copy one,
  send one, and send the app itself. Only our own page is ever loaded in this
  WebView - every other address goes out to the browser - so nothing from the
  web is on the other end of that bridge, and R8 is told to keep its methods or
  a release build would silently lose all four.
- **Read aloud.** The phone's own `TextToSpeech`, not the page's: whichever
  languages the reader has installed are the ones it can read. Hebrew, Aramaic
  and Greek are spoken with the modern Hebrew and Greek voices - the
  pronunciation is not ancient, but it is the language, and it is what exists.
  A phone with no speech engine says so, and the Listen button is not offered.
  Speaking stops when the app goes into the background.

  A reader can take a dozen verses at once, and past the length the engine
  accepts - `getMaxSpeechInputLength()`, four thousand characters on most
  phones - it speaks nothing at all rather than what it can. The passage is
  therefore broken at a space and queued piece by piece, the first flushing
  whatever was being said and the rest following it.

  The page is told how each reading ended. The "Who is Jesus?" stories count
  only when they were heard to the end, so `speak` takes a number from the
  page, and an `UtteranceProgressListener` sends it back through
  `speechDone(id, finished)` - true when the last piece was spoken, false the
  moment anything stopped it, including the app going into the background.
  Each reading answers once, and a reading already flushed by the next one
  does not answer at all: the number is what keeps them apart. The engine's
  "done" is not taken on its own, because one phone kept reporting it before
  the story was over: after it, the shell watches the phone's music stream
  (`AudioManager.isMusicActive`, where speech is played) and reports the end
  once the stream has been silent for a moment and at least half the time the
  text should take has passed - or, if something else keeps the stream busy,
  when twice that time has gone.
- **Sharing the app.** The share sheet, which is where Quick Share lives, is
  handed a copy of our own APK through a `FileProvider` - Android will not let
  one app read another's file by path. The copy goes to `cache/share/`, and
  that folder is the only thing the provider exposes.
- **Search by meaning.** A reader who describes a passage ("the man thrown to
  the lions") is answered by a model, not by the page: the app carries
  multilingual-e5-small, cut down to this project's vocabulary and stored as
  int8 by `scripts/build_encoder.py`, and ONNX Runtime to run it (`Meaning.java`).
  The page asks through `AndroidApp.meaning(n, lang, question)` and is answered
  with `meaningDone(n, [[cosine, verse id], ...])`, by number, because the
  reader types on while the model reads. The page could search by meaning alone
  with the table `build_vectors.py` makes, and does in a browser, but a table
  of word pieces knows little about Thai, whose pieces mean little alone; the
  model found the passage for five Thai questions of eight where the table
  found two. ONNX Runtime opens a file and an asset has no path, so the model is
  copied into the app's own storage the first time, under a name for this
  install, and the last install's copy is removed. Only the two ARM builds of
  the runtime are carried (`abiFilters`); on an x86 phone the app still runs
  and the page falls back to the table, or to no such section. `?diag` says
  which.
- **Rotation.** The activity handles the configuration changes itself rather
  than being rebuilt: parsing an eighteen-megabyte page again would lose the
  reader's place every time the phone turns. Process death is covered
  separately, by `WebView.saveState`.
- **When the page cannot open.** Missing assets, a WebView that is being
  updated, or a renderer killed for memory each show a plain screen saying
  which, with a retry where retrying could help.

## Before the Play listing

- **Privacy policy.** Required for every listing, even one that collects
  nothing. A page saying the app has no network permission, collects nothing,
  shares nothing and keeps its settings on the device covers it; the manifest
  is the proof.
- **Data safety form.** No data collected, no data shared, no data types at
  all. There is no encryption-in-transit question to answer because there is no
  transit; the deletion question is answered by uninstalling.
- **Content rating questionnaire.** A reference text with no user content, no
  ads, no purchases and no communication. Answer the violence and sexuality
  questions in terms of what the biblical text itself contains rather than what
  the app does, and say in the notes that it is a translation of a religious
  work.
- **App category.** Books & Reference.
- **Graphics.** Icon 512 x 512 PNG (32-bit, no alpha for the listing);
  feature graphic 1024 x 500 PNG or JPEG; at least two phone screenshots
  between 320 and 3840 px on a side with a 16:9 or 9:16 ratio; a 7-inch and a
  10-inch tablet set if the listing claims tablet support - it should, the
  reader lays out well on a wide screen. The launcher icon in `res/` is a
  vector and is not the listing icon; export the 512 px PNG from it.
- **Size.** The base AAB is close to eighty megabytes of text before
  compression. Play's limit for an install-time bundle is 200 MB, so there is
  room, but a future language will need either Play Asset Delivery or a
  download-on-demand of `morph/`.
- **Target API.** 36, which Play requires of new apps and updates from
  31 August 2026 (an extension to 1 November can be requested in the Console);
  `minSdk 24` covers Android 7 and later. The level rises every August, so
  check it again before each year's first upload.
