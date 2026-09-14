# eBible Android wrapper

A WebView around `site/index.html`. The whole reader - text, morphology,
lexicon, themes, parallels - is in the APK, and the app asks for no
permissions at all, the INTERNET one least of any: nothing is fetched and
nothing is reported back.

## Building

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
  deciding in the page.
- **Read aloud.** The Android System WebView has no `speechSynthesis`, so the
  page's read-aloud menu does not appear in the app. The page checks for it and
  hides the item rather than failing. Bringing it back would take a bridge to
  Android's `TextToSpeech`.
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
