"""Canonical book metadata shared by the pipeline scripts.

Keys are the OSIS/SBLGNT file codes used by the source repositories.
`name` is the English book name used for output files and prompts.
`num` gives canonical (Protestant) order, 1-66.
"""

BOOKS = {
    # --- Old Testament (WLC OSIS codes) ---
    "Gen":    {"num": 1,  "name": "Genesis",         "testament": "OT"},
    "Exod":   {"num": 2,  "name": "Exodus",          "testament": "OT"},
    "Lev":    {"num": 3,  "name": "Leviticus",       "testament": "OT"},
    "Num":    {"num": 4,  "name": "Numbers",         "testament": "OT"},
    "Deut":   {"num": 5,  "name": "Deuteronomy",     "testament": "OT"},
    "Josh":   {"num": 6,  "name": "Joshua",          "testament": "OT"},
    "Judg":   {"num": 7,  "name": "Judges",          "testament": "OT"},
    "Ruth":   {"num": 8,  "name": "Ruth",            "testament": "OT"},
    "1Sam":   {"num": 9,  "name": "1 Samuel",        "testament": "OT"},
    "2Sam":   {"num": 10, "name": "2 Samuel",        "testament": "OT"},
    "1Kgs":   {"num": 11, "name": "1 Kings",         "testament": "OT"},
    "2Kgs":   {"num": 12, "name": "2 Kings",         "testament": "OT"},
    "1Chr":   {"num": 13, "name": "1 Chronicles",    "testament": "OT"},
    "2Chr":   {"num": 14, "name": "2 Chronicles",    "testament": "OT"},
    "Ezra":   {"num": 15, "name": "Ezra",            "testament": "OT"},
    "Neh":    {"num": 16, "name": "Nehemiah",        "testament": "OT"},
    "Esth":   {"num": 17, "name": "Esther",          "testament": "OT"},
    "Job":    {"num": 18, "name": "Job",             "testament": "OT"},
    "Ps":     {"num": 19, "name": "Psalms",          "testament": "OT"},
    "Prov":   {"num": 20, "name": "Proverbs",        "testament": "OT"},
    "Eccl":   {"num": 21, "name": "Ecclesiastes",    "testament": "OT"},
    "Song":   {"num": 22, "name": "Song of Songs",   "testament": "OT"},
    "Isa":    {"num": 23, "name": "Isaiah",          "testament": "OT"},
    "Jer":    {"num": 24, "name": "Jeremiah",        "testament": "OT"},
    "Lam":    {"num": 25, "name": "Lamentations",    "testament": "OT"},
    "Ezek":   {"num": 26, "name": "Ezekiel",         "testament": "OT"},
    "Dan":    {"num": 27, "name": "Daniel",          "testament": "OT"},
    "Hos":    {"num": 28, "name": "Hosea",           "testament": "OT"},
    "Joel":   {"num": 29, "name": "Joel",            "testament": "OT"},
    "Amos":   {"num": 30, "name": "Amos",            "testament": "OT"},
    "Obad":   {"num": 31, "name": "Obadiah",         "testament": "OT"},
    "Jonah":  {"num": 32, "name": "Jonah",           "testament": "OT"},
    "Mic":    {"num": 33, "name": "Micah",           "testament": "OT"},
    "Nah":    {"num": 34, "name": "Nahum",           "testament": "OT"},
    "Hab":    {"num": 35, "name": "Habakkuk",        "testament": "OT"},
    "Zeph":   {"num": 36, "name": "Zephaniah",       "testament": "OT"},
    "Hag":    {"num": 37, "name": "Haggai",          "testament": "OT"},
    "Zech":   {"num": 38, "name": "Zechariah",       "testament": "OT"},
    "Mal":    {"num": 39, "name": "Malachi",         "testament": "OT"},
    # --- New Testament (SBLGNT file codes) ---
    "Matt":   {"num": 40, "name": "Matthew",         "testament": "NT"},
    "Mark":   {"num": 41, "name": "Mark",            "testament": "NT"},
    "Luke":   {"num": 42, "name": "Luke",            "testament": "NT"},
    "John":   {"num": 43, "name": "John",            "testament": "NT"},
    "Acts":   {"num": 44, "name": "Acts",            "testament": "NT"},
    "Rom":    {"num": 45, "name": "Romans",          "testament": "NT"},
    "1Cor":   {"num": 46, "name": "1 Corinthians",   "testament": "NT"},
    "2Cor":   {"num": 47, "name": "2 Corinthians",   "testament": "NT"},
    "Gal":    {"num": 48, "name": "Galatians",       "testament": "NT"},
    "Eph":    {"num": 49, "name": "Ephesians",       "testament": "NT"},
    "Phil":   {"num": 50, "name": "Philippians",     "testament": "NT"},
    "Col":    {"num": 51, "name": "Colossians",      "testament": "NT"},
    "1Thess": {"num": 52, "name": "1 Thessalonians", "testament": "NT"},
    "2Thess": {"num": 53, "name": "2 Thessalonians", "testament": "NT"},
    "1Tim":   {"num": 54, "name": "1 Timothy",       "testament": "NT"},
    "2Tim":   {"num": 55, "name": "2 Timothy",       "testament": "NT"},
    "Titus":  {"num": 56, "name": "Titus",           "testament": "NT"},
    "Phlm":   {"num": 57, "name": "Philemon",        "testament": "NT"},
    "Heb":    {"num": 58, "name": "Hebrews",         "testament": "NT"},
    "Jas":    {"num": 59, "name": "James",           "testament": "NT"},
    "1Pet":   {"num": 60, "name": "1 Peter",         "testament": "NT"},
    "2Pet":   {"num": 61, "name": "2 Peter",         "testament": "NT"},
    "1John":  {"num": 62, "name": "1 John",          "testament": "NT"},
    "2John":  {"num": 63, "name": "2 John",          "testament": "NT"},
    "3John":  {"num": 64, "name": "3 John",          "testament": "NT"},
    "Jude":   {"num": 65, "name": "Jude",            "testament": "NT"},
    "Rev":    {"num": 66, "name": "Revelation",      "testament": "NT"},
}

# Aramaic sections of the OT, as (chapter, verse) inclusive ranges per book.
# Gen 31:47 is only two words inside a Hebrew verse, so it is not tagged.
ARAMAIC = {
    "Dan":  [((2, 4), (7, 28))],
    "Ezra": [((4, 8), (6, 18)), ((7, 12), (7, 26))],
    "Jer":  [((10, 11), (10, 11))],
}


def is_aramaic(code: str, chapter: int, verse: int) -> bool:
    for (c1, v1), (c2, v2) in ARAMAIC.get(code, []):
        if (c1, v1) <= (chapter, verse) <= (c2, v2):
            return True
    return False


def slug(name: str) -> str:
    """File-system-safe book name: '1 Samuel' -> '1_Samuel'."""
    return name.replace(" ", "_")


# --- Original languages -------------------------------------------------
# One table for the whole pipeline: the driver labels prompts with it, the
# reader and live dashboard render with it. Codes are ISO 639-3 as used in the
# normalized sources (OT verses carry "lang": "arc" in the Aramaic sections:
# Daniel 2:4-7:28, Ezra 4:8-6:18 and 7:12-26, Jeremiah 10:11; NT is all Greek).
LANGS = {
    "hbo": {"name": "Hebrew",  "dir": "rtl", "script": "Hebrew",
            "source": "Westminster Leningrad Codex"},
    "arc": {"name": "Aramaic", "dir": "rtl", "script": "Hebrew",
            "source": "Westminster Leningrad Codex"},
    "grc": {"name": "Greek",   "dir": "ltr", "script": "Greek",
            "source": "SBLGNT"},
}
MIXED = {"name": "Hebrew / Aramaic", "dir": "rtl", "script": "Hebrew"}


def verse_lang(meta, verse) -> str:
    """Language code of one normalized verse record."""
    return "grc" if meta["testament"] == "NT" else verse.get("lang", "hbo")


def chapter_lang(meta, verses) -> str:
    """'hbo' | 'arc' | 'grc' | 'mixed' for a list of normalized verses."""
    langs = {verse_lang(meta, v) for v in verses}
    return next(iter(langs)) if len(langs) == 1 else "mixed"


def lang_info(code) -> dict:
    return MIXED if code == "mixed" else LANGS[code]
