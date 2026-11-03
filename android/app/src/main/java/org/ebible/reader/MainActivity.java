package org.ebible.reader;

import android.annotation.SuppressLint;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.ComponentActivity;
import androidx.activity.EdgeToEdge;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.Nullable;
import androidx.annotation.RequiresApi;
import androidx.core.content.FileProvider;
import androidx.core.graphics.ColorUtils;
import androidx.core.graphics.Insets;
import androidx.core.splashscreen.SplashScreen;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.json.JSONObject;

/**
 * The app is a window and nothing else: the reader is the page in assets, and
 * everything below is about getting out of its way - the right colour behind
 * it, the back button handed to it, its place kept when Android takes the
 * process away, and a plain explanation on the one screen where the page
 * cannot be shown at all.
 */
public class MainActivity extends ComponentActivity {

    private static final String PAGE = "file:///android_asset/index.html";
    private static final String ASSET = "index.html";

    /**
     * The page is eighteen megabytes and takes a moment to parse on a slow
     * phone. Holding the splash until it has painted is better than showing an
     * empty window, but only up to a point: after this the splash goes whether
     * the page is ready or not, so the app never looks stuck.
     */
    private static final long SPLASH_CEILING_MS = 4000L;

    /**
     * Ask the page to go back before the app does. The reader keeps its own
     * trail of what has been looked at - a theme or a lexicon entry has no
     * address of its own, so browser history cannot cover them. In the order a
     * reader expects them undone: a popup over the text, then the page's own
     * canGoBack()/goBack(), which also close an open tray. The page's back
     * arrow is not a stand-in for canGoBack(): it stays disabled while a tray
     * is open over the first page, and back would then skip the tray.
     */
    private static final String BACK_JS =
            "(function(){try{"
            + "if(typeof window.androidBack==='function')return !!androidBack();"
            + "var w=document.getElementById('wpop');"
            + "if(w&&!w.hidden&&typeof hidePop==='function'){hidePop();return true;}"
            + "var r=document.getElementById('vpop');"
            + "if(r&&!r.hidden&&typeof hideRefs==='function'){hideRefs();return true;}"
            + "var c=document.getElementById('ctx');"
            + "if(c&&!c.hidden){c.hidden=true;return true;}"
            + "if(typeof canGoBack==='function'&&typeof goBack==='function'&&canGoBack()){goBack();return true;}"
            + "}catch(e){}return false;})()";

    /** The colour the page is actually painted in, asked for rather than assumed. */
    private static final String THEME_JS =
            "(function(){try{"
            + "var m=document.querySelector('meta[name=\"theme-color\"]');"
            + "if(m&&m.content)return m.content;"
            + "return getComputedStyle(document.body).backgroundColor;"
            + "}catch(e){return ''}})()";

    private FrameLayout root;
    private FrameLayout holder;
    private View errorView;
    private WebView web;               // null when this phone could not give us one
    private boolean painted;           // the splash waits on this
    @Nullable private Integer barColour;                          // what the bars were last given
    @Nullable private volatile Speech speech;                     // the phone's voice, started when first asked for
    @Nullable private Meaning meaning;                            // search by meaning, built the first time it is asked
    @Nullable private String meaningFailed;                       // why it could not be, once that is known
    @Nullable private ExecutorService meaningWork;                // one question at a time, off every thread the page waits on
    private long leaveAskedAt;                                    // when back was last pressed with nowhere to go
    private final Runnable recheckBars = this::matchBarsToPage;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        SplashScreen splash = SplashScreen.installSplashScreen(this);
        super.onCreate(savedInstanceState);
        EdgeToEdge.enable(this);
        setContentView(R.layout.activity_main);

        root = findViewById(R.id.root);
        holder = findViewById(R.id.web_holder);
        errorView = findViewById(R.id.error);
        findViewById(R.id.error_retry).setOnClickListener(v -> recreate());

        // The window draws behind the status and gesture bars so the page's
        // background reaches the edges of the screen, and the content is then
        // held clear of them - and of a camera cutout, and of the keyboard -
        // by the insets the system actually reports rather than by guessed
        // heights. The insets are then consumed: passed on, a recent WebView
        // turns them into the page's env(safe-area-inset-*) as well, and the
        // page would pad again for bars it is already clear of.
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, windowInsets) -> {
            Insets in = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout()
                    | WindowInsetsCompat.Type.ime());
            v.setPadding(in.left, in.top, in.right, in.bottom);
            return WindowInsetsCompat.CONSUMED;
        });

        splash.setKeepOnScreenCondition(() -> !painted);
        root.postDelayed(() -> painted = true, SPLASH_CEILING_MS);

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                OnBackPressedCallback self = this;
                if (web == null) {
                    leave(self);
                    return;
                }
                // The WebView's own history is deliberately not consulted. It
                // holds every chapter address the page has moved to, including
                // the ones its trail re-enters on the way back, so walking it
                // re-fed the trail and back could never leave the app. The page
                // is the only judge of where there is to go.
                web.evaluateJavascript(BACK_JS, handled -> {
                    if (!"true".equals(handled)) leave(self);
                });
            }
        });

        openReader(savedInstanceState);
    }

    /**
     * Back, when the page says it has nothing left to put away.
     *
     * Leaving on the first press is how a phone app is expected to behave, but
     * a reader deep in a chapter can hit back by accident and lose their place
     * to a stray touch. The first press says what the second one will do; a
     * second press within a couple of seconds does it.
     */
    private void leave(OnBackPressedCallback callback) {
        long now = System.currentTimeMillis();
        if (web != null && now - leaveAskedAt > 2500) {       // no reading to lose on the error screen
            leaveAskedAt = now;
            Toast.makeText(this, R.string.back_again, Toast.LENGTH_SHORT).show();
            return;
        }
        callback.setEnabled(false);
        getOnBackPressedDispatcher().onBackPressed();
        callback.setEnabled(true);
    }

    private void openReader(@Nullable Bundle savedInstanceState) {
        if (!assetPresent()) {
            // Nothing to retry: the text is missing from this copy of the app.
            showError(getString(R.string.error_missing_assets), false);
            return;
        }
        try {
            web = new WebView(this);
        } catch (Throwable t) {
            // A phone whose WebView is being updated, or has been disabled,
            // throws here rather than returning null. It is worth trying again
            // in a minute, so the button stays.
            showError(getString(R.string.error_webview), true);
            return;
        }
        configure(web);
        holder.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // Coming back from a process Android killed to make room: the WebView's
        // own saved state carries the history and the fragment, which is where
        // the reader's place lives, so it reloads itself at the right verse.
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) {
            web.loadUrl(PAGE);
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configure(WebView w) {
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);      // the reader is all script
        // The badge for a story heard to the end rings a bell, minutes after
        // the tap that started the reading. Only our own page is loaded here,
        // so it may sound without a touch just before.
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setDomStorageEnabled(true);      // text size, view, language and theme preferences live in local storage

        // The page is in the APK and asks for nothing outside it. Assets and
        // resources still load with file access off; ordinary file:// paths on
        // the phone do not, and neither does anything the page might be
        // tricked into reading across origins.
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);
        s.setGeolocationEnabled(false);

        // Pinch zoom is the magnifier for a reader who cannot see the text at
        // its set size. The page never turns it off (no maximum-scale in its
        // viewport), and the WebView must not either: zoom is off by default
        // here. The on-screen +/- controls are hidden because they cover the
        // text and a pinch does the same job.
        s.setSupportZoom(true);
        s.setBuiltInZoomControls(true);
        s.setDisplayZoomControls(false);

        s.setUseWideViewPort(true);        // honour the page's viewport meta, so the text reflows at device width
        s.setLoadWithOverviewMode(true);

        // setTextZoom is deliberately not called. Left alone, the WebView
        // already scales text by the phone's own font-size setting, which is
        // how a reader who has made everything larger expects this app to
        // behave; the page's +/- then moves up and down from there. Pinning it
        // to 100 would quietly overrule an accessibility setting.

        w.setBackgroundColor(getColor(R.color.page_bg));   // no white flash before the first paint
        w.setWebViewClient(new ReaderClient());
        // The page can ask the phone for the things a page alone cannot do:
        // speak a verse, put one on the clipboard, hand one to another app.
        // Only our own page is ever loaded here - every other address is sent
        // out to the browser in shouldOverrideUrlLoading - so nothing from the
        // web is on the other end of this.
        w.addJavascriptInterface(new Bridge(), "AndroidApp");

        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);   // only in a debug build, never in what Play receives
        }
    }

    private class ReaderClient extends WebViewClient {

        @Override
        public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
            return openOutside(request.getUrl());
        }

        @Override
        @SuppressWarnings("deprecation")
        public boolean shouldOverrideUrlLoading(WebView v, String url) {
            return openOutside(Uri.parse(url));
        }

        @Override
        public void onPageCommitVisible(WebView v, String url) {
            painted = true;
            matchBarsToPage();
        }

        @Override
        public void onPageFinished(WebView v, String url) {
            painted = true;
            matchBarsToPage();
        }

        @Override
        public void onReceivedError(WebView v, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) return;   // a missing morph/*.js is the page's own business
            painted = true;
            showError(getString(R.string.error_load_failed), true);
        }

        @Override
        @RequiresApi(Build.VERSION_CODES.O)
        public boolean onRenderProcessGone(WebView v, RenderProcessGoneDetail detail) {
            // The page's renderer died - out of memory on a small phone, most
            // likely. Saying we handled it keeps the app alive; the WebView
            // itself is finished with and has to go.
            painted = true;
            holder.removeAllViews();
            if (web != null) {
                web.destroy();
                web = null;
            }
            showError(getString(R.string.error_load_failed), true);
            return true;
        }
    }

    /**
     * What the page cannot do by itself, the phone does for it.
     *
     * The Android System WebView has no speech of its own, no way to reach the
     * clipboard a reader would expect, and no share sheet; all three live out
     * here. Every method is called from a binder thread, so anything that
     * touches the window or the UI is posted back to the main one.
     */
    private class Bridge {

        /**
         * Read a verse aloud in the language it is written in, at the speed the
         * reader has chosen.
         *
         * Left to itself the engine speaks at whatever rate the phone's own
         * accessibility settings ask for, which on some phones is very fast
         * indeed - the page therefore always says what it wants, and the
         * reader can change it in the display tray.
         */
        @JavascriptInterface
        public void speak(String text, String lang, float rate, float pitch, String voice) {
            speak(text, lang, rate, pitch, voice, 0);
        }

        /**
         * The same, with a number the page will hear back.
         *
         * A story only counts as listened to when it was heard to the end, so
         * the page needs to know how a reading ended - finished, or stopped -
         * and which reading it was: its stop for one passage and its start of
         * the next are a moment apart, and an answer about the first must not
         * be taken for the second. Speech.report() sends the number back with
         * the verdict.
         */
        @JavascriptInterface
        public void speak(String text, String lang, float rate, float pitch, String voice, int id) {
            runOnUiThread(() -> speech().say(text, lang, rate, pitch, voice, id));
        }

        /**
         * The voices this phone can read that language with, as JSON.
         *
         * Only the ones held on the device: the app has no internet permission,
         * so a voice that needs the network would simply never speak. Quality
         * is the engine's own rating, and it is what separates the flat compact
         * voice most phones default to from the fuller one beside it.
         */
        @JavascriptInterface
        public String voices(String lang) {
            Speech sp = speech;
            return sp == null ? "[]" : sp.voiceList(lang);
        }

        /**
         * Stop, if there is anything to stop.
         *
         * The page calls this whenever the verses being held change, which is
         * long before anyone has asked to hear one: going through speech()
         * would build a text-to-speech engine on a phone whose reader never
         * wants to hear anything.
         */
        @JavascriptInterface
        public void stopSpeaking() {
            Speech sp = speech;
            if (sp != null) runOnUiThread(sp::stop);
        }

        /**
         * -> "" while the voices are still loading, "yes", or "no".
         *
         * This one answers on the calling thread, because the page waits on it
         * to decide whether to offer Listen at all. The engine itself is only
         * ever built on the main thread; until it is there, the answer is "not
         * yet" and the page asks again the next time a verse is taken up.
         */
        @JavascriptInterface
        public String voiceFor(String lang) {
            if (speech == null) {
                runOnUiThread(MainActivity.this::speech);
                return "";
            }
            return speech.state(lang);
        }

        @JavascriptInterface
        public void copy(String text, String said) {
            runOnUiThread(() -> {
                ClipboardManager cb = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                if (cb != null) {
                    cb.setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), text));
                    // Android 13 and later shows its own copy confirmation; saying
                    // it again over the top would be one notice too many.
                    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) toast(said);
                }
            });
        }

        /** Hand a verse to whatever the reader shares with - messages, mail, notes. */
        @JavascriptInterface
        public void share(String text, String subject) {
            Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain")
                    .putExtra(Intent.EXTRA_TEXT, text)
                    .putExtra(Intent.EXTRA_SUBJECT, subject);
            runOnUiThread(() -> open(send, subject));
        }

        /**
         * Hand the app itself to the phone next to you. The share sheet this
         * opens is where Quick Share lives, so a copy can go over the air with
         * no shop and no network in between.
         */
        @JavascriptInterface
        public void shareApp() {
            // The app is eleven megabytes at least, and copying that where the
            // screen is drawn would freeze it long enough for Android to offer
            // to kill us. The copy is made here, on the thread the page called
            // from; only the share sheet goes back to the main one.
            ApplicationInfo info = getApplicationInfo();
            if (info.splitSourceDirs != null && info.splitSourceDirs.length > 0) {
                // An app delivered by Play arrives in pieces; handing on the
                // base piece alone would give the other phone something that
                // cannot install. Only the APK built here is a single file.
                toast(getString(R.string.share_app_split));
                return;
            }
            try {
                File dir = new File(getCacheDir(), "share");
                if (!dir.exists() && !dir.mkdirs()) throw new IOException("no share folder");
                File copy = new File(dir, getString(R.string.app_name) + ".apk");
                try (InputStream in = new FileInputStream(info.sourceDir);
                     OutputStream out = new FileOutputStream(copy)) {
                    byte[] buf = new byte[1 << 16];
                    for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                }
                Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".files", copy);
                Intent send = new Intent(Intent.ACTION_SEND)
                        .setType("application/vnd.android.package-archive")
                        .putExtra(Intent.EXTRA_STREAM, uri)
                        .putExtra(Intent.EXTRA_SUBJECT, getString(R.string.share_app_subject))
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                runOnUiThread(() -> open(send, getString(R.string.share_app_subject)));
            } catch (IOException | RuntimeException e) {                  // noqa: the reader gets told, not a crash
                toast(getString(R.string.share_app_failed));
            }
        }

        /**
         * The page's own word about the colour it has just painted.
         *
         * The reader's choice of skin changes nothing the shell can see, so
         * before this the bars were re-read after every tap and caught up a
         * moment later. Now the page says so as it happens.
         */
        @JavascriptInterface
        public void theme(String css) {
            runOnUiThread(() -> applyBars(parseCssColour(css)));
        }

        /** The share sheet, or a word about why there is none. */
        private void open(Intent send, String title) {
            try {
                startActivity(Intent.createChooser(send, title));
            } catch (ActivityNotFoundException | SecurityException e) {
                toast(getString(R.string.share_app_failed));
            }
        }

        @JavascriptInterface
        public void toast(String msg) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show());
        }

        /**
         * The languages this copy can search by meaning with the model, comma
         * separated; "" when it carries no model, and the page then uses its
         * own table if it has one.
         *
         * Read from the assets rather than asked of the model, so answering
         * costs nothing and loads nothing: the page asks once, before anyone
         * has searched.
         */
        @JavascriptInterface
        public String meaningLangs() {
            if (meaningFailed != null) return "";
            try {
                String[] files = getAssets().list(Meaning.DIR.substring(0, Meaning.DIR.length() - 1));
                if (files == null) return "";
                StringBuilder out = new StringBuilder();
                boolean model = false;
                for (String f : files) {
                    if (f.equals("encoder.onnx")) model = true;
                    else if (f.startsWith("vecm_") && f.endsWith(".bin"))
                        out.append(out.length() > 0 ? "," : "").append(f, 5, f.length() - 4);
                }
                return model ? out.toString() : "";
            } catch (IOException e) {
                return "";
            }
        }

        /**
         * Find the verses nearest a question, and answer the page with
         * meaningDone(seq, [[cosine, verse id], ...]) - or with null and the
         * reason, which ?diag shows.
         *
         * The answer goes back by number, as speech does, because the reader
         * types on while the model reads: an answer to an earlier question must
         * not be drawn under a later one, and the page drops it by its number.
         * Sixty are sent back so the page can leave out the verses it has
         * already found by their words and still have a dozen to choose from.
         */
        @JavascriptInterface
        public void meaning(int seq, String lang, String question) {
            meaningWorker().execute(() -> {
                String hits = "null", why = "";
                try {
                    float[][] near = meaningModel().nearest(lang, question, 60);
                    StringBuilder b = new StringBuilder("[");
                    for (float[] h : near)
                        b.append(b.length() > 1 ? "," : "").append('[').append(h[0]).append(',').append((int) h[1]).append(']');
                    hits = b.append(']').toString();
                } catch (Throwable e) {        // a phone whose processor the runtime does not support says so, rather than crash
                    why = e.getClass().getSimpleName() + ": " + e.getMessage();
                    if (e instanceof LinkageError) meaningFailed = why;
                }
                final String js = "if(typeof window.meaningDone==='function')meaningDone(" + seq + ","
                        + hits + "," + JSONObject.quote(why) + ")";
                runOnUiThread(() -> { if (web != null) web.evaluateJavascript(js, null); });
            });
        }

        /** For ?diag: whether the model has been loaded, or why it cannot be. */
        @JavascriptInterface
        public String meaningState() {
            if (meaningFailed != null) return "failed - " + meaningFailed;
            Meaning m = meaning;
            return m != null && m.loaded() ? "ready" : "not loaded yet (it loads with the first search)";
        }
    }

    private synchronized ExecutorService meaningWorker() {
        if (meaningWork == null) meaningWork = Executors.newSingleThreadExecutor();
        return meaningWork;
    }

    /**
     * The model is copied out of the APK into the app's own storage the first
     * time, because ONNX Runtime opens a file and an asset has no path. The
     * copy is named for this install, so an update brings its own model and the
     * last one's copy is cleared rather than left taking forty megabytes.
     */
    private Meaning meaningModel() {
        if (meaning != null) return meaning;
        long stamp;
        try {
            stamp = getPackageManager().getPackageInfo(getPackageName(), 0).lastUpdateTime;
        } catch (Exception e) {
            stamp = 0;
        }
        String keep = "encoder-" + stamp + ".onnx";
        File[] old = getFilesDir().listFiles((d, n) -> n.startsWith("encoder-") && !n.equals(keep));
        if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
            f.delete();
        meaning = new Meaning(name -> getAssets().open(name), new File(getFilesDir(), keep));
        return meaning;
    }

    /**
     * The phone's own text-to-speech, held open while the app is.
     *
     * A voice is the phone's, not ours: whichever languages the reader has
     * installed are the ones that can be heard. Hebrew and Greek are read with
     * the modern voices for those languages - the pronunciation is not
     * ancient, but it is the language, and it is what exists.
     */
    private Speech speech() {
        if (speech == null) speech = new Speech();
        return speech;
    }

    private class Speech implements TextToSpeech.OnInitListener {
        private final TextToSpeech tts = new TextToSpeech(MainActivity.this, this);
        private volatile boolean ready;          // set on the main thread, read from the page's binder thread
        private volatile boolean failed;         // no speech engine on this phone at all
        private String pendingText, pendingLang, pendingVoice;
        private float pendingRate = 1f, pendingPitch = 1f;
        private int pendingId;
        /*
         * One reading is one run: its utterances are named after it, so the
         * engine's callbacks - which arrive on the engine's own thread, and for
         * pieces of a reading already flushed by the next one - can be told
         * apart from the reading the page is waiting on. Each run is reported
         * once, finished or stopped, whichever comes first.
         */
        private volatile int run;
        private volatile int pageId;
        private volatile String lastPiece;
        private volatile boolean reported;
        /*
         * "Done" is not taken at its word. Some engines say an utterance is
         * finished while the phone is still speaking it - on one phone the
         * badge for a story kept arriving before the reading was over - so
         * the end is judged by the phone's own audio instead: after the engine
         * has said done, the reading is over once the music stream has been
         * silent for a moment and at least half the time the text should take
         * has passed. If something else keeps the stream busy, twice that time
         * is taken as the end. Only the last piece of a reading is watched.
         */
        private final AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        private volatile long startedAt, floorAt;   // when the reading began, and when it should be over
        private volatile long quietSince;            // when the stream last fell silent; 0 while it sounds
        private volatile boolean doneSeen;
        private final Runnable finish = this::maybeFinish;

        {
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String id) {}
                @Override public void onDone(String id) {
                    if (id.equals(lastPiece)) { doneSeen = true; runOnUiThread(finish); }
                }
                @Override public void onError(String id) { report(id, false); }
                @Override public void onError(String id, int code) { report(id, false); }
                @Override public void onStop(String id, boolean interrupted) { report(id, false); }
            });
        }

        /** On the main thread: finished, if every sign agrees; otherwise look again shortly. */
        private void maybeFinish() {
            if (reported || !doneSeen || lastPiece == null) return;
            long now = System.currentTimeMillis();
            boolean busy = tts.isSpeaking() || (audio != null && audio.isMusicActive());
            if (busy) quietSince = 0; else if (quietSince == 0) quietSince = now;
            long span = floorAt - startedAt;
            boolean quiet = quietSince != 0 && now - quietSince >= 1500 && now >= startedAt + span / 2;
            boolean overdue = now >= floorAt + span;
            if (quiet || overdue) { report(lastPiece, true); return; }
            root.postDelayed(finish, 400);
        }

        /** Characters a second an engine speaks at rate 1: rough, and only used to bound the wait. */
        private double pace(String lang) {
            switch (lang == null ? "" : lang) {
                case "zh": case "yue": case "nan": case "hak": return 4.5;
                case "ja": case "ja-easy": return 5;
                case "th": return 8;
                default: return 15;
            }
        }

        /** Tell the page how the reading it asked for ended, once, and never about an older one. */
        private void report(String id, boolean finished) {
            if (id == null || !id.startsWith("ebible" + run + "-")) return;
            synchronized (this) {
                if (reported) return;
                reported = true;
            }
            final int which = pageId;
            runOnUiThread(() -> {
                if (web != null)
                    web.evaluateJavascript("if(typeof window.speechDone==='function')speechDone("
                                           + which + "," + finished + ")", null);
            });
        }

        @Nullable
        private Voice pick(Locale loc, String wanted) {
            Voice best = null;
            try {
                for (Voice v : tts.getVoices()) {
                    if (v == null || v.isNetworkConnectionRequired()) continue;
                    if (!v.getLocale().getLanguage().equals(loc.getLanguage())) continue;
                    if (wanted != null && wanted.equals(v.getName())) return v;
                    if (best == null || v.getQuality() > best.getQuality()) best = v;
                }
            } catch (RuntimeException e) {                      // some engines throw rather than answer
                return null;
            }
            return best;
        }

        String voiceList(String lang) {
            if (!ready) return "[]";
            Locale loc = locale(lang);
            StringBuilder out = new StringBuilder("[");
            try {
                for (Voice v : tts.getVoices()) {
                    if (v == null || v.isNetworkConnectionRequired()) continue;
                    if (!v.getLocale().getLanguage().equals(loc.getLanguage())) continue;
                    if (out.length() > 1) out.append(',');
                    out.append("{\"name\":\"").append(v.getName().replace("\"", ""))
                       .append("\",\"locale\":\"").append(v.getLocale().toLanguageTag())
                       .append("\",\"quality\":").append(v.getQuality()).append('}');
                }
            } catch (RuntimeException e) {                      // noqa: an engine that will not list is one voice to us
                return "[]";
            }
            return out.append(']').toString();
        }

        /** Nothing outside what an engine will do, whatever the page asks for. */
        private float clamp(float v) {
            return v < 0.3f ? 0.3f : v > 2.5f ? 2.5f : v;
        }

        @Override
        public void onInit(int status) {
            ready = status == TextToSpeech.SUCCESS;
            failed = !ready;
            if (ready && pendingText != null) say(pendingText, pendingLang, pendingRate, pendingPitch, pendingVoice, pendingId);
            pendingText = null;
        }

        private Locale locale(String tag) {
            final String lang = tag == null ? "" : tag;
            switch (lang) {
                case "hbo": case "arc": return new Locale("he", "IL");    // modern Hebrew voice for the Hebrew text
                case "grc": return new Locale("el", "GR");                // modern Greek for the Greek
                case "zh": return Locale.SIMPLIFIED_CHINESE;
                case "yue": return Locale.forLanguageTag("zh-HK");
                case "nan": case "hak": return Locale.forLanguageTag("zh-TW");
                case "ja-easy": return Locale.JAPANESE;
                default: return Locale.forLanguageTag(lang.isEmpty() ? "en" : lang);
            }
        }

        String state(String lang) {
            // A phone with no speech engine installed never becomes ready, and
            // the page must hear "no" rather than wait for a voice that is not
            // coming, or it would offer a Listen button that does nothing.
            if (failed) return "no";
            if (!ready) return "";                                          // still starting up; the page asks again
            int r = tts.isLanguageAvailable(locale(lang));
            return r >= TextToSpeech.LANG_AVAILABLE ? "yes" : "no";
        }

        void say(String text, String lang, float rate, float pitch, String wanted, int id) {
            if (text == null || text.isEmpty()) return;
            if (!ready) { pendingText = text; pendingLang = lang; pendingRate = rate; pendingPitch = pitch;
                          pendingVoice = wanted; pendingId = id; return; }
            root.removeCallbacks(finish);
            run++;
            pageId = id;
            reported = false;
            lastPiece = null;
            doneSeen = false; quietSince = 0;
            startedAt = System.currentTimeMillis();
            floorAt = startedAt + (long) (text.trim().length() * 1000.0 / (pace(lang) * clamp(rate)));
            Locale loc = locale(lang);
            tts.setLanguage(loc);
            // Left alone the engine takes its default, which on most phones is
            // the compact voice - the one that sounds like a machine reading
            // letters. The best one installed for that language is chosen here
            // instead, unless the reader has picked one themselves.
            Voice v = pick(loc, wanted);
            if (v != null) tts.setVoice(v);
            tts.setSpeechRate(clamp(rate));
            tts.setPitch(clamp(pitch));
            speakChunks(text);
        }

        /**
         * Say it, however long it is.
         *
         * A reader can now hold a dozen verses at once, and past the length the
         * engine accepts it speaks nothing at all - so the passage is broken at
         * a space and queued piece by piece rather than cut off at the limit.
         */
        private void speakChunks(String text) {
            text = text.trim();                // so the last piece is a real one, and can be named as the last
            int max = TextToSpeech.getMaxSpeechInputLength();
            if (max <= 0) max = 4000;
            int spoken = 0;
            for (int i = 0; i < text.length(); ) {
                int end = Math.min(text.length(), i + max);
                if (end < text.length()) {
                    int space = text.lastIndexOf(' ', end);
                    if (space > i) end = space;
                }
                String piece = text.substring(i, end).trim();
                i = end;
                if (piece.isEmpty()) continue;
                // The last piece is the one whose end is the end of the reading;
                // it is named before it is queued, because a short piece can be
                // over before speak() has returned.
                String name = "ebible" + run + "-" + spoken;
                if (end >= text.length()) lastPiece = name;
                tts.speak(piece, spoken == 0 ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD, null, name);
                spoken++;
            }
            if (spoken == 0) tts.stop();       // nothing but spaces: at least stop what was already going
        }

        void stop() {
            root.removeCallbacks(finish);
            if (ready) tts.stop();             // the listener's onStop tells the page
        }

        void shutdown() {
            root.removeCallbacks(finish);
            tts.stop();
            tts.shutdown();
        }
    }

    /**
     * The credits carry links out to the source texts. There is no INTERNET
     * permission here, so those pages could only fail inside the app; they
     * belong to whatever the reader uses for the web.
     */
    private boolean openOutside(Uri uri) {
        if (uri == null) return false;
        String url = uri.toString();
        if (url.startsWith("file:///android_asset/")) return false;   // the reader's own pages
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (ActivityNotFoundException | SecurityException e) {
            Toast.makeText(this, R.string.no_browser, Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    /**
     * Take the colour from the page rather than deciding it here. The reader
     * paints itself light or dark from the phone's own setting, and on older
     * WebViews it may stay light where the shell would have gone dark; asking
     * what it actually painted is the only way the bars and the page are
     * certain to be one surface.
     */
    private void matchBarsToPage() {
        if (web == null) return;
        web.evaluateJavascript(THEME_JS, value -> applyBars(parseCssColour(value)));
    }

    /** Put the window and the bar icons on the colour the page is painted in. */
    private void applyBars(@Nullable Integer colour) {
        if (colour == null || colour.equals(barColour) || root == null) return;
        barColour = colour;
        root.setBackgroundColor(colour);
        if (web != null) web.setBackgroundColor(colour);
        boolean lightBehind = ColorUtils.calculateLuminance(colour) > 0.5;
        WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(getWindow(), root);
        bars.setAppearanceLightStatusBars(lightBehind);     // dark icons on a pale page, pale icons on a dark one
        bars.setAppearanceLightNavigationBars(lightBehind);
    }

    /** "#faf8f4", "rgb(250, 248, 244)" or a colour name, as evaluateJavascript quotes it. */
    @Nullable
    private static Integer parseCssColour(@Nullable String raw) {
        if (raw == null) return null;
        String v = raw.trim();
        if (v.length() >= 2 && v.startsWith("\"") && v.endsWith("\"")) v = v.substring(1, v.length() - 1);
        v = v.replace("\\\"", "\"").trim();
        if (v.isEmpty() || "null".equals(v)) return null;
        try {
            if (v.startsWith("rgb")) {
                int open = v.indexOf('('), close = v.indexOf(')');
                if (open < 0 || close < open) return null;
                String[] part = v.substring(open + 1, close).trim().split("[,\\s/]+");
                if (part.length < 3) return null;
                // A see-through body tells us nothing about what the reader is
                // looking at, so leave the bars as they are.
                if (part.length > 3 && Float.parseFloat(part[3]) < 0.5f) return null;
                return Color.rgb(
                        Math.round(Float.parseFloat(part[0])),
                        Math.round(Float.parseFloat(part[1])),
                        Math.round(Float.parseFloat(part[2])));
            }
            return Color.parseColor(v);
        } catch (RuntimeException e) {
            return null;      // a colour we cannot read is no reason to change anything
        }
    }

    private boolean assetPresent() {
        try (InputStream in = getAssets().open(ASSET)) {
            return in.read() != -1;
        } catch (Exception e) {
            return false;
        }
    }

    private void showError(String detail, boolean retryable) {
        painted = true;                   // let the splash go; there is something to read
        holder.setVisibility(View.GONE);
        errorView.setVisibility(View.VISIBLE);
        ((TextView) findViewById(R.id.error_detail)).setText(detail);
        findViewById(R.id.error_retry).setVisibility(retryable ? View.VISIBLE : View.GONE);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // The activity rides out a rotation or a switch into dark mode itself,
        // so nothing here is rebuilt; the page may repaint in the other palette
        // though, and the bars follow it once it has.
        scheduleBarCheck();
    }

    /**
     * The page tells the shell its colour as it changes it (Bridge.theme), so
     * this is the net underneath: an older page in a newer shell, or a paint
     * that came from somewhere the page did not announce. A colour choice is
     * only ever made with a tap or a key, so asking once just after each
     * catches whatever the page did not say, and nothing is polled.
     */
    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        int action = ev.getActionMasked();
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) scheduleBarCheck();
        return super.dispatchTouchEvent(ev);
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent ev) {
        if (ev.getAction() == KeyEvent.ACTION_UP) scheduleBarCheck();
        return super.dispatchKeyEvent(ev);
    }

    private void scheduleBarCheck() {
        if (root == null) return;
        root.removeCallbacks(recheckBars);
        root.postDelayed(recheckBars, 300L);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) web.onPause();     // no timers or animation running behind another app
        if (speech != null) speech.stop();  // a verse being read does not follow the reader out of the app
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
        scheduleBarCheck();                 // the phone's theme may have changed while we were away
    }

    @Override
    protected void onDestroy() {
        if (root != null) root.removeCallbacks(recheckBars);
        if (speech != null) { speech.shutdown(); speech = null; }
        if (meaningWork != null) { meaningWork.shutdownNow(); meaningWork = null; }
        if (web != null) {
            holder.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
