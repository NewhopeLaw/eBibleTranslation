package org.ebible.reader;

import android.annotation.SuppressLint;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
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
import androidx.core.graphics.ColorUtils;
import androidx.core.graphics.Insets;
import androidx.core.splashscreen.SplashScreen;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import java.io.InputStream;

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
     * address of its own, so browser history cannot cover them - and its trays
     * close before the page moves. Three ways of asking, in the order they are
     * worth trying: a hook the page may grow for us, the state of its own back
     * button, and otherwise nothing, which leaves the decision here.
     */
    private static final String BACK_JS =
            "(function(){try{"
            + "if(typeof window.androidBack==='function')return !!androidBack();"
            + "var b=document.getElementById('back');"
            + "if(b&&!b.disabled&&typeof window.goBack==='function'){goBack();return true;}"
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
        // heights. Because the padding is applied out here, the page's own
        // safe-area CSS has nothing left to correct.
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, windowInsets) -> {
            Insets in = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout()
                    | WindowInsetsCompat.Type.ime());
            v.setPadding(in.left, in.top, in.right, in.bottom);
            return windowInsets;
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
                web.evaluateJavascript(BACK_JS, handled -> {
                    if ("true".equals(handled)) return;
                    if (web != null && web.canGoBack()) web.goBack();
                    else leave(self);
                });
            }
        });

        openReader(savedInstanceState);
    }

    /** Step aside and let the system finish the activity, gesture animation and all. */
    private void leave(OnBackPressedCallback callback) {
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
        web.evaluateJavascript(THEME_JS, value -> {
            Integer colour = parseCssColour(value);
            if (colour == null) return;
            root.setBackgroundColor(colour);
            if (web != null) web.setBackgroundColor(colour);
            boolean lightBehind = ColorUtils.calculateLuminance(colour) > 0.5;
            WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(getWindow(), root);
            bars.setAppearanceLightStatusBars(lightBehind);     // dark icons on a pale page, pale icons on a dark one
            bars.setAppearanceLightNavigationBars(lightBehind);
        });
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
        root.postDelayed(this::matchBarsToPage, 200L);
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
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            holder.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
