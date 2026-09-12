#!/bin/sh
# Copy the built reader into the APK's assets. The page loads its word tags,
# lexicon, themes and the rest from morph/*.js beside it, so that folder ships
# too or every analysis view would come up empty in the app.
#
# The assets are not in git - they are a second copy of site/, and eighty
# megabytes of it - so this has to be run on a fresh checkout before the first
# build. app/build.gradle stops the build with the same advice if it is not.
set -eu
cd "$(dirname "$0")"

if [ ! -f ../site/index.html ]; then
    echo "site/index.html is missing - build it on the PC with scripts/build_site.py" >&2
    exit 1
fi
if [ ! -d ../site/morph ]; then
    echo "site/morph is missing - the analysis views would all be empty" >&2
    exit 1
fi

bytes=$(wc -c < ../site/index.html)
# A full reader is tens of megabytes because the whole translated text is in
# it. Anything much smaller is a site built somewhere without the chapters,
# and shipping that would quietly publish a Bible with a few books in it.
if [ "$bytes" -lt 4000000 ]; then
    echo "site/index.html is only $bytes bytes - that is not a full reader." >&2
    echo "Rebuild it on the machine that holds output/ before syncing." >&2
    exit 1
fi

mkdir -p app/src/main/assets
cp ../site/index.html app/src/main/assets/index.html
rm -rf app/src/main/assets/morph
cp -r ../site/morph app/src/main/assets/morph
echo "assets updated: $bytes bytes, $(ls app/src/main/assets/morph | wc -l) data files"
