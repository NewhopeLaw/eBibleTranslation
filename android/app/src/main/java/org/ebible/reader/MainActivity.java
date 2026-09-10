package org.ebible.reader;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
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
        s.setDomStorageEnabled(true);      // font-size preference
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        web.loadUrl("file:///android_asset/index.html");
        setContentView(web);
    }

    @Override
    public void onBackPressed() {
        // hash-router history: back steps through chapters, then exits
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
