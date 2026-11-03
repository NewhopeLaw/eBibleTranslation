package org.ebible.reader;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtException;
import ai.onnxruntime.OrtSession;

/**
 * Search by meaning with the model itself: a question in, the verses nearest it out.
 *
 * The page can find verses by meaning on its own, from a table of what each
 * word piece means alone (scripts/build_vectors.py), and for English that does
 * well. For Thai it does not: Thai is cut into short pieces that mean little by
 * themselves, and only a model that reads them together knows the sentence.
 * So the app carries the model - multilingual-e5-small, cut down and stored as
 * int8 by scripts/build_encoder.py - and ONNX Runtime to run it, and answers the
 * page's question here.
 *
 * Nothing here touches Android, so the same class runs on a desktop JVM against
 * the same files, which is how it is checked against the Python that built them.
 * The files are read through {@link Source}: the APK's assets on a phone, a
 * folder on a desktop.
 *
 * Every method may be slow the first time (the model is copied out of the APK
 * and loaded, the language's verses read), so the caller runs them off the UI
 * thread, one at a time.
 */
final class Meaning {

    /** Where the files come from. */
    interface Source {
        InputStream open(String name) throws IOException;
    }

    static final String DIR = "model/";
    private static final String QUERY = "query: ";     // the prefix e5 was trained to read a question with
    private static final int MAXLEN = 128;             // as in build_encoder.py; a question never comes near it

    private final Source src;
    private final File modelFile;

    private OrtEnvironment env;
    private OrtSession session;
    private Map<String, Integer> pieceId;
    private float[] score;
    private int maxPiece, bos, eos, unk;
    private float unkScore;
    private float[] mu, proj;                          // the projection every language's verses were reduced with
    private int din, dout;
    private final Map<String, Verses> langs = new HashMap<>();

    /**
     * @param modelFile where the model is to be found, or copied to if it is
     *                  not there yet. ONNX Runtime wants a file it can open; an
     *                  asset in an APK is compressed and has no path, so on a
     *                  phone the model is written out once to the app's own
     *                  storage and read from there every time after.
     */
    Meaning(Source src, File modelFile) {
        this.src = src;
        this.modelFile = modelFile;
    }

    private static final class Verses {
        int n, d;
        float scale;
        int[] ids;
        byte[] v;
    }

    /** -> [[cosine, verse id], ...] for the k verses nearest the question, nearest first. */
    synchronized float[][] nearest(String lang, String question, int k) throws IOException, OrtException {
        load();
        Verses vs = verses(lang);
        float[] q = project(embed(question));
        float[] top = new float[k], tid = new float[k];
        int have = 0;
        for (int j = 0, o = 0; j < vs.n; j++, o += vs.d) {
            float s = 0;
            for (int i = 0; i < vs.d; i++) s += vs.v[o + i] * q[i];
            s *= vs.scale;
            if (have < k) { insert(top, tid, have++, s, vs.ids[j]); }
            else if (s > top[k - 1]) { insert(top, tid, k - 1, s, vs.ids[j]); }
        }
        float[][] out = new float[have][];
        for (int i = 0; i < have; i++) out[i] = new float[]{top[i], tid[i]};
        return out;
    }

    /** Put (s, id) at `at` and let it rise to its place; the list stays sorted, highest first. */
    private static void insert(float[] top, float[] tid, int at, float s, int id) {
        int i = at;
        while (i > 0 && top[i - 1] < s) { top[i] = top[i - 1]; tid[i] = tid[i - 1]; i--; }
        top[i] = s;
        tid[i] = id;
    }

    /** Whether this copy of the app has verses for that language at all. */
    boolean has(String lang) {
        try (InputStream in = src.open(DIR + "vecm_" + lang + ".bin")) {
            return in != null;
        } catch (IOException e) {
            return false;
        }
    }

    synchronized boolean loaded() {
        return session != null;
    }

    // ------------------------------------------------------------ the model

    private void load() throws IOException, OrtException {
        if (session != null) return;
        if (pieceId == null) readVocab();
        readProj();
        if (!modelFile.exists()) {
            File part = new File(modelFile.getPath() + ".part");
            try (InputStream in = src.open(DIR + "encoder.onnx"); OutputStream out = new FileOutputStream(part)) {
                byte[] buf = new byte[1 << 16];
                for (int r; (r = in.read(buf)) > 0; ) out.write(buf, 0, r);
            }
            // Renamed only when whole: a copy cut short by the app being closed
            // must not be found next time and taken for the model.
            if (!part.renameTo(modelFile)) throw new IOException("could not keep " + modelFile);
        }
        env = OrtEnvironment.getEnvironment();
        OrtSession.SessionOptions opt = new OrtSession.SessionOptions();
        // Two threads: a cheap phone has four slow cores and the page is still
        // drawing the verses that matched by their words on another.
        opt.setIntraOpNumThreads(2);
        session = env.createSession(modelFile.getPath(), opt);
    }

    private void readVocab() throws IOException {
        String[] lines = new String(readAll(DIR + "vocab.tsv"), StandardCharsets.UTF_8).split("\n");
        pieceId = new HashMap<>(lines.length * 2);
        score = new float[lines.length];
        float lo = 0;
        for (int i = 0; i < lines.length; i++) {
            int tab = lines[i].lastIndexOf('\t');
            String p = lines[i].substring(0, tab);
            score[i] = Float.parseFloat(lines[i].substring(tab + 1));
            pieceId.putIfAbsent(p, i);
            maxPiece = Math.max(maxPiece, p.codePointCount(0, p.length()));
            lo = Math.min(lo, score[i]);
        }
        bos = pieceId.get("<s>");
        eos = pieceId.get("</s>");
        unk = pieceId.get("<unk>");
        // The tokenizer gives a character no piece covers the lowest score less
        // ten, so an unknown letter is only ever the last resort.
        unkScore = lo - 10;
    }

    private void readProj() throws IOException {
        ByteBuffer b = ByteBuffer.wrap(readAll(DIR + "proj.bin")).order(ByteOrder.LITTLE_ENDIAN);
        if (b.getInt() != 0x4a4f5250) throw new IOException("proj.bin is not a projection");   // "PROJ"
        din = b.getInt();
        dout = b.getInt();
        mu = new float[din];
        proj = new float[din * dout];
        b.asFloatBuffer().get(mu);
        b.position(12 + 4 * din);
        b.asFloatBuffer().get(proj);
    }

    private Verses verses(String lang) throws IOException {
        Verses vs = langs.get(lang);
        if (vs != null) return vs;
        // One language at a time is held: a reader who changes language does not
        // need the last one's six megabytes kept on a phone that has little.
        langs.clear();
        ByteBuffer b = ByteBuffer.wrap(readAll(DIR + "vecm_" + lang + ".bin")).order(ByteOrder.LITTLE_ENDIAN);
        if (b.getInt() != 0x4d434556) throw new IOException("vecm_" + lang + ".bin is not a verse file");  // "VECM"
        vs = new Verses();
        vs.n = b.getInt();
        vs.d = b.getInt();
        vs.scale = b.getFloat();
        if (vs.d != dout) throw new IOException("vecm_" + lang + ".bin does not match proj.bin - rebuild both together");
        vs.ids = new int[vs.n];
        b.asIntBuffer().get(vs.ids);
        b.position(16 + 4 * vs.n);
        vs.v = new byte[vs.n * vs.d];
        b.get(vs.v);
        langs.put(lang, vs);
        return vs;
    }

    // ------------------------------------------------------------ a question

    /** The question cut into pieces as the model's own tokenizer cuts it, framed by <s> and </s>. */
    int[] tokens(String text) throws IOException {
        if (pieceId == null) readVocab();
        List<Integer> ids = new ArrayList<>();
        ids.add(bos);
        String norm = Normalizer.normalize(QUERY + text, Normalizer.Form.NFKC).trim();
        for (String word : norm.split("\\s+")) {
            if (word.isEmpty()) continue;
            int[] cp = ("▁" + word).codePoints().toArray();     // every word starts with the tokenizer's space mark
            int n = cp.length;
            double[] best = new double[n + 1];
            int[] from = new int[n + 1], piece = new int[n + 1];
            java.util.Arrays.fill(best, Double.NEGATIVE_INFINITY);
            best[0] = 0;
            for (int i = 0; i < n; i++) {
                if (best[i] == Double.NEGATIVE_INFINITY) continue;
                StringBuilder sub = new StringBuilder();
                for (int j = i; j < n && j - i < maxPiece; j++) {
                    sub.appendCodePoint(cp[j]);
                    Integer r = pieceId.get(sub.toString());
                    if (r != null && best[i] + score[r] > best[j + 1]) {
                        best[j + 1] = best[i] + score[r]; from[j + 1] = i; piece[j + 1] = r;
                    }
                }
                if (best[i] + unkScore > best[i + 1]) {
                    best[i + 1] = best[i] + unkScore; from[i + 1] = i; piece[i + 1] = unk;
                }
            }
            List<Integer> got = new ArrayList<>();
            for (int k = n; k > 0; k = from[k]) got.add(0, piece[k]);
            // Unknown letters in a row are one <unk> to the tokenizer, not several.
            for (int g : got) if (!(g == unk && !ids.isEmpty() && ids.get(ids.size() - 1) == unk)) ids.add(g);
        }
        if (ids.size() > MAXLEN - 1) ids = ids.subList(0, MAXLEN - 1);
        ids.add(eos);
        int[] out = new int[ids.size()];
        for (int i = 0; i < out.length; i++) out[i] = ids.get(i);
        return out;
    }

    /** The model's vector for a question: mean-pooled and unit length, as the graph returns it. */
    float[] embed(String text) throws IOException, OrtException {
        int[] t = tokens(text);
        long[][] ids = new long[1][t.length], mask = new long[1][t.length];
        for (int i = 0; i < t.length; i++) { ids[0][i] = t[i]; mask[0][i] = 1; }
        Map<String, OnnxTensor> in = new HashMap<>();
        try (OnnxTensor a = OnnxTensor.createTensor(env, ids); OnnxTensor m = OnnxTensor.createTensor(env, mask)) {
            in.put("input_ids", a);
            in.put("attention_mask", m);
            try (OrtSession.Result r = session.run(in)) {
                return ((float[][]) r.get(0).getValue())[0];
            }
        }
    }

    /** Into the reduced space the verses are stored in, unit length again. */
    private float[] project(float[] e) {
        float[] q = new float[dout];
        for (int i = 0; i < din; i++) {
            float c = e[i] - mu[i];
            for (int j = 0, o = i * dout; j < dout; j++) q[j] += c * proj[o + j];
        }
        double mag = 0;
        for (float x : q) mag += x * x;
        float inv = (float) (1 / Math.sqrt(Math.max(mag, 1e-12)));
        for (int j = 0; j < dout; j++) q[j] *= inv;
        return q;
    }

    private byte[] readAll(String name) throws IOException {
        try (InputStream in = src.open(name)) {
            if (in == null) throw new IOException(name + " is not in this copy");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[1 << 16];
            for (int r; (r = in.read(buf)) > 0; ) out.write(buf, 0, r);
            return out.toByteArray();
        }
    }
}
