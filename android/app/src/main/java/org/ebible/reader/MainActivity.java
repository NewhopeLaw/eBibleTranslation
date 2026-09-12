package org.ebible.reader;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
import android.webkit.ValueCallback;
import android.webkit.WebSettings;
import android.webkit.WebView;

public class MainActivity extends Activity {
    private WebView web;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);      // reader logic
        s.setDomStorageEnabled(true);      // text size, theme, mode and language preferences
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
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
        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
    }

    @Override
    public void onBackPressed() {
        // The reader keeps its own trail of what has been looked at (a theme
        // or a lexicon entry has no address of its own, so browser history
        // cannot cover them) and its trays close before the page moves. The
        // system back button therefore asks the page first, and the app only
        // exits when the page says there is nowhere left to go.
        web.evaluateJavascript(
            "(function(){ if (window.canGoBack && canGoBack()) { goBack(); return true; } return false; })()",
            new ValueCallback<String>() {
                @Override
                public void onReceiveValue(String handled) {
                    if ("true".equals(handled)) return;
                    if (web.canGoBack()) web.goBack();
                    else finish();
                }
            });
    }
}
