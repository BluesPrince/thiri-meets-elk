#!/bin/bash -e
# render_png.sh — rasterize the slide SVGs to projector-resolution PNGs.
#
# Uses headless Chrome (the only SVG rasterizer present on this Mac — no
# rsvg-convert, ImageMagick, Inkscape or cairosvg). Each SVG is wrapped in a
# minimal HTML page sized to the figure's own aspect so Chrome's screenshot
# comes out at exactly the requested pixel size with no letterboxing.
#
#   tools/slides/render_png.sh [scale]      # default 2400px wide (~2.4K, plenty for 1080p/4K slides)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$ROOT/figures"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH="${1:-2400}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -x "$CHROME" ] || { echo "!! Chrome not found at $CHROME"; exit 1; }

shopt -s nullglob
for svg in "$DIR"/*.svg; do
  base="$(basename "$svg" .svg)"
  # read the figure's intrinsic size out of the SVG header
  read -r vw vh < <(python3 - "$svg" <<'PY'
import re, sys
head = open(sys.argv[1]).read(400)
m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
print(m.group(1), m.group(2))
PY
)
  h=$(python3 -c "print(round($WIDTH * $vh / $vw))")
  # inline the SVG so there is no file:// sub-request to block
  python3 - "$svg" "$TMP/$base.html" <<'PY'
import sys
svg = open(sys.argv[1]).read()
open(sys.argv[2], "w").write(
    "<!doctype html><meta charset=utf-8>"
    "<style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block;width:100vw;height:auto}</style>"
    + svg)
PY
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
      --screenshot="$DIR/$base.png" --window-size="$WIDTH,$h" \
      "file://$TMP/$base.html" >/dev/null 2>&1
  echo "  $base.png  ${WIDTH}x${h}"
done
echo "rendered to assets/slides/"
