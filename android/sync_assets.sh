#!/bin/sh
# Copy the built reader into the APK's assets.
cd "$(dirname "$0")"
mkdir -p app/src/main/assets
cp ../site/index.html app/src/main/assets/index.html
echo "assets updated: $(wc -c < app/src/main/assets/index.html) bytes"
