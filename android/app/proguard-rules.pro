# R8 has almost nothing of ours to shrink - one activity - but it does strip
# the parts of the androidx libraries the app never calls, which is most of
# them. Nothing here needs keeping by name: the app has no reflection and no
# @JavascriptInterface, because the page and the shell talk one way only,
# through evaluateJavascript.
#
# The page talks to the phone through AndroidApp - speech, the clipboard, the
# share sheet - and R8 would otherwise rename methods only JavaScript calls,
# leaving a release build where every one of those buttons does nothing.
-keepclassmembers class org.ebible.reader.** {
    @android.webkit.JavascriptInterface <methods>;
}

# A crash report from Play is only worth reading with the line numbers in it;
# the mapping file that goes with the build translates the rest.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# ONNX Runtime's native library calls back into its Java classes by name, so
# R8 must leave them as they are or a release build loses search by meaning.
-keep class ai.onnxruntime.** { *; }
