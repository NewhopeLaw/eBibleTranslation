#!/bin/sh
# Copy the built reader into the APK's assets. The page loads its word tags,
# lexicon, themes and the rest from morph/*.js beside it, so that folder ships
# too or every analysis view would come up empty in the app.
cd "$(dirname "$0")"
mkdir -p app/src/main/assets
cp ../site/index.html app/src/main/assets/index.html
rm -rf app/src/main/assets/morph
cp -r ../site/morph app/src/main/assets/morph
echo "assets updated: $(wc -c < app/src/main/assets/index.html) bytes, $(ls app/src/main/assets/morph | wc -l) data files"
