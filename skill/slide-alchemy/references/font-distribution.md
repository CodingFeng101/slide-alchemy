# Font packs

The skill includes a small ONNX encoder and a pinned catalog with file hashes.
Font binaries and their licenses go into a separate local cache. The core pack
contains 8 families and 14 styles, totalling 71,429,896 font bytes. The remote
matching pack contains 30 families and 92 styles, totalling 375,551,368 font bytes.
Consult `font-catalog.json` for current exact totals and upstream sources.

The release also serves the core-only WenKai Lite font for installing the local
pack. The remote matching index uses the full WenKai family. Core fonts that
appear in both packs share a single server file.

## Install the core pack

```bash
python scripts/font_store.py --server http://182.254.211.241/fonts/v1 --include-system
```

The default cache is `%LOCALAPPDATA%/slide-alchemy/fonts/v1` on Windows and
`~/.cache/slide-alchemy/fonts/v1` elsewhere. `--cache` selects another directory.
The installer checks SHA-256 before accepting a file, repairs damaged cache
entries, and keeps the previous file if a replacement fails validation.
`--include-system` also indexes installed system fonts. The generated index
records the cache paths, so rebuild it after moving the cache.

The cache provides font files to the matcher. PowerPoint itself needs the
selected face installed through the operating system when rendering editable
text. Cross-device font embedding remains a separate task.

## Download fonts to a user-selected folder

Run a download command with a destination directory. The following command
downloads the 30-family server selection, including 92 styles.

```bash
python scripts/font_store.py --server http://182.254.211.241/fonts/v1 --download-pack server --output-dir "D:/PPT-fonts"
```

Use `--download-pack core` for the 8-family, 14-style core pack. To download a
single family or one matched face, use its catalog family name or asset ID.

```bash
python scripts/font_store.py --server http://182.254.211.241/fonts/v1 --download-font "ZCOOL XiaoWei" --output-dir "D:/PPT-fonts"
python scripts/font_store.py --server http://182.254.211.241/fonts/v1 --download-font source-han-sans-cn-bold --output-dir "D:/PPT-fonts"
```

Fonts go into `fonts/`, licenses into `licenses/`, and the selected font records
into `font-manifest.json` inside the destination directory. The command verifies
hashes, reuses intact files on subsequent runs and downloads missing or damaged
files. A completed selection publishes its manifest through an atomic rename.
These commands download desktop font files. Install the selected files through
the operating system when PowerPoint needs to render them. The PPT stores
colours, sizes and text effects.

## Extract with remote expansion

```bash
python scripts/extract_text.py run/source/slide_003.png --rich-text --font-server http://182.254.211.241/fonts/v1 --out run/analysis/texts_layout.json
```

Without explicit font index/model arguments, this command installs the core
pack and indexes it together with installed system fonts. Existing index/model
arguments continue to select the local candidate set. `--font-cache` selects
the download cache.

The local model and OpenCV run first. A missing supported face or a best shape
error above 0.12 triggers remote matching. This is the existing provisional
poor-match threshold, rather than a calibrated probability. The server refines
up to 10 candidates. If its best candidate improves on the local result, the
client downloads that face and its license. The report retains the remote
shortlist and the selected local cache path. Equal or worse remote results
preserve the local face. An unreachable server preserves the local result and
adds `remote_unavailable` to the review reasons.

`match_fonts.py match` also accepts `--font-server` and `--font-cache`. Inline
boundary proposal continues to use local fonts. Short same-colour boundaries
and combined effects retain the review limits documented in text extraction.
Newly added faces are flagged as absent from the encoder's training set. Pack
coverage does not establish recognition accuracy on real slides.

## Publication

Nginx serves the versioned catalog, model, fonts and licenses at `/fonts/v1/`.
`GET /fonts/v1/health` checks the matcher. `POST /fonts/v1/match` accepts JSON
with `text`, a base64 PNG `mask_png`, and `top_k` from 1 to 10. Masks contain
the measured ink, without the original slide background.

Run `scripts/serve_fonts.py --root <release-directory> --port 8010` behind
Nginx. It binds to loopback, accepts one matching task at a time, bounds input
dimensions, and limits its FreeType cache. The deployment uses a dedicated
systemd service. Runtime dependencies are numpy, Pillow, OpenCV, ONNX Runtime
and fonttools. The published catalog and its matching index belong to the same
immutable release. An expanded selection should publish a new release and
update the skill's pinned catalog together.

Variable fonts were instantiated at the selected weights. Derived Raleway,
Merriweather, Playfair Display and Source Sans 3 faces use SlideAlchemy family
names to respect their reserved font names. The catalog retains their original
family attribution and licenses.
