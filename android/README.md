# eBible Android wrapper

Minimal WebView APK around `site/index.html`. No frameworks, no network
permission — the app is fully offline.

## Build (needs Android SDK; not installed on the Spark)

```sh
./sync_assets.sh              # copy the current site/index.html into assets/
gradle assembleDebug          # or open this folder in Android Studio
# APK lands in app/build/outputs/apk/debug/app-debug.apk
```

After translating more chapters, re-run `scripts/build_site.py`,
`./sync_assets.sh`, and rebuild — the page is the whole app.

TODO before a release build: launcher icon (`app/src/main/res/mipmap-*`),
signing config, `versionCode` bump.
