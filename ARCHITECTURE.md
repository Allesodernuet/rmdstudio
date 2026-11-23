# Rmd Studio — architecture and feasibility notes

## Verdict

Yes, this is feasible, with one important caveat: **Word's presentational
formatting does not map 1:1 onto R Markdown**. Markdown can express structure
and emphasis; it cannot express fonts, sizes, colours or line spacing. R Markdown
also executes R chunks, so the file format has semantics a Word document does
not.

The current target is **PDF via Quarto or rmarkdown**, inside a standalone
project workspace rather than RStudio. The workable design is a rich
**semantic** editor plus a two-layer serializer:

1. Emit clean, PDF-safe Markdown for everything Markdown/LaTeX can express.
2. Optionally emit Pandoc HTML attributes/spans/divs for visual extras, clearly
   marked as HTML-only and **off by default**.

That gives a Word-like writing experience and a valid `.Rmd` whose PDF output
is indistinguishable in structure from a file written directly in RStudio.
Font/colour/spacing controls remain editor-side conveniences; they are not
serialized in the default PDF mode.

## Primary concerns

1. **Formatting fidelity.** Fonts, colours, highlights and spacing are not part
   of Markdown. They require HTML/CSS attributes and only render in HTML-family
   outputs. Exact PDF typography should be controlled by the R Markdown theme,
   a CSS file, or LaTeX, not by a Word-like selection.
2. **Round-tripping existing Rmd.** Pandoc's Markdown dialect is larger than the
   visual editor. Citations, cross-references, footnote bodies, raw LaTeX,
   merged table cells and complex fenced divs cannot all be edited visually
   without losing or normalising syntax. The importer preserves YAML and code
   chunks exactly, uses the Pandoc AST for prose, and warns about approximations.
3. **Two editors on one file.** Another editor and Rmd Studio can both write the
   same file. A naive autosave can destroy the other editor's changes. The app
   uses atomic writes plus a SHA-256 baseline and prompts on external change.
4. **External editor reload behaviour.** Other editors do not expose a general
   external "push text into this open editor" API. Writing the file and letting
   the editor reload is the robust path.
5. **Render environment.** The app discovers Quarto, Pandoc, Rscript and
   pdflatex, and sets the environment those tools need. Quarto on Windows is
   sensitive to non-ASCII paths and temp/cache permissions, so the app supplies
   a writable cache root, a UTF-8 codepage cache, short ASCII temp/cache paths
   and the original `R_LIBS_USER`. If LaTeX is missing, the app offers a
   one-click TinyTeX install (including `soul` for underline/strikeout).
6. **Build log.** RStudio's Build pane is output-only and has no standard
   editable build-log file. The app therefore provides a dedicated Work log
   panel and writes to a user-designated append-only file (default
   `build.log` next to the document). If a specific log schema is required,
   it must be matched explicitly.
7. **Packaging.** PySide6 produces a large but reliable executable. Windows
   SmartScreen warnings are expected because the exe is unsigned. Code signing
   is a distribution concern, not a technical one.
8. **Words that Markdown treats specially.** Inline Markdown punctuation is
   escaped (`*`, `_`, `[`, `]`, `\`, `$`, `~`, `^`, `<`, `>`); `#`, `>` and
   list markers are protected only at line start, and `|` only inside tables.
   This keeps the source looking hand-written rather than machine-escaped.
9. **Merged/complex tables.** Markdown pipe tables cannot represent merged cells
   or multi-paragraph cells. These are flattened with a warning. An HTML table
   fallback is a future option.
10. **AI privacy and audit.** AI prompts may contain private document text and
    are sent to the configured provider. The local JSONL log can contain that
    text, is editable, and is not an institutional audit service. The API key is
    DPAPI-encrypted; full-content logging is optional.

## Stack choice

**Python 3.12+ / PySide6 (Qt 6) / PyInstaller.**

Why:

- The existing `pdf-studio` project in this workspace already uses PySide6 and
  PyInstaller successfully, so the packaging path and dark theme are proven.
- `QTextDocument` gives a real rich-text model with undo/redo, tables, lists,
  images, anchor links, custom char/block formats and document traversal.
- A native Windows app starts faster and is smaller than an Electron build
  (38 MB one-file vs a browser runtime).
- Python has straightforward, robust process/file integration.

Alternative considered: Electron/Tauri + TipTap. TipTap gives a nicer
browser-grade editing experience, but adds a Node/Chromium runtime, a much larger
installer, and still has exactly the same Markdown/HTML mapping problem. Tauri
would be smaller but requires a Rust toolchain that is not installed here.
A C#/WPF FlowDocument editor would give good Word parity but would need a
hand-built Markdown converter and a different packaging stack.

## Components

```
┌──────────────────────────────────────────────────────────────┐
│ MainWindow (main_window.py)                                  │
│  ribbon · page · front matter · Files tree · work log        │
│  AI chat · preview · autosave · conflicts · Render PDF       │
└───────────────┬───────────────┬───────────────┬─────────────┘
                │               │               │
      ┌─────────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────┐
      │ MarkdownEditor │ │ FileSync    │ │ logbook.py      │
      │ QTextEdit      │ │ hash+watch  │ │ append-only log │
      │ chunks, paste  │ │ atomic save │ │ designated file │
      └─────────┬──────┘ └─────────────┘ └─────────────────┘
                │
      ┌─────────▼────────────────────────────────────────────┐
      │ chat_panel.py → ai_client.py → OpenAI-compatible API │
      │ credentials.py (DPAPI) · ai_log.py (JSONL usage log) │
      └──────────────────────────────────────────────────────┘
                │
      ┌─────────▼────────────────────────────────────────────┐
      │ model/                                               │
      │  markdown.py  QTextDocument → Rmd (PDF-clean default)│
      │  importer.py  Rmd → QTextDocument (Pandoc AST)       │
      │  blocks.py    formatting/chunk/table/image helpers   │
      │  style.py     custom property IDs + defaults         │
      └──────────────────────────────────────────────────────┘
```

### `model/style.py`

Defines the document defaults (Georgia 11.5 pt, éclair #f2ebdd) and the custom
`QTextFormat` properties used to carry R Markdown-specific concepts through
undo/redo:

- `PROP_BLOCK_KIND` — paragraph, heading, quote, chunk header/line, raw, hr.
- `PROP_CHUNK_ID` / `PROP_CHUNK_HEADER` — group code lines into one chunk.
- `PROP_INLINE_CODE`, `PROP_RAW_INLINE` — inline code and preserved raw syntax.
- `PROP_IMAGE_ALT`, `PROP_IMAGE_WIDTH` — image metadata.
- `PROP_TABLE_HEADER` — whether the first row is a Markdown header.
- `PROP_BLOCK_LINE_SPACING`, `PROP_BLOCK_SPACE_BEFORE/AFTER` — explicit visual
  spacing that should be serialized (not the editor-only heading margins).

### `model/markdown.py`

Walks top-level blocks and table frames in document order:

- Headings → `#`…`######`
- Paragraphs → escaped text with inline formatting
- Bold/italic/strike → `**`, `*`, `~~`
- Underline → `[text]{.underline}` (Pandoc bracketed span)
- Superscript/subscript → `^text^` / `~text~`
- Inline code → backtick fence sized to the content
- Links → `[label](href)`
- Lists → `-` / `1.` with 2-space nesting
- Blockquotes → `>`
- Chunks → ```` ```{r ...} ```` with the original options
- Tables → pipe tables with column alignment
- HR → `---`
- Visual font/size/colour/background → `[text]{style="..."}`
- Visual paragraph alignment/spacing → `::: {style="..."}` fenced divs

The serializer returns warnings for unsafe cases (missing image, merged table
cells, multi-paragraph cells, non-portable bullet styles) and the UI surfaces
them in the generated-markdown pane and status bar.

### `model/importer.py`

R code chunks are not Pandoc Markdown: Pandoc sees ```` ```{r} ```` as an
unknown code block. The importer therefore:

1. Splits YAML front matter.
2. Pulls fenced R chunks and generic code out of the body, replacing them with
   unique marker paragraphs.
3. Runs Pandoc on the remaining prose (`-f markdown -t json`).
4. Maps the AST blocks/inlines into `QTextDocument` with the same custom
   properties the writer uses.
5. Replaces markers with structured chunk blocks.

This preserves YAML and code exactly and lets the app understand Pandoc spans,
fenced divs, tables and links. Unknown syntax is kept as raw text with a warning
or, if Pandoc is unavailable, the whole body is shown as one raw block so a save
cannot silently rewrite it.

### `logbook.py`

Resolves the designated log file relative to the document (or uses an absolute
path), formats timestamped entries, and appends with `O_APPEND`-style writes
plus `fsync`. The UI keeps a read-only view and a small input box; `Ctrl+Enter`
or **Add entry** writes the entry and refreshes the view. Default:
`<document folder>/build.log`. There is no standard editable RStudio build
log; this is a separate file the user can point at whatever their workflow
expects.

### Project tree

The Files tab uses `QFileSystemModel` + `QTreeView` rooted at a project folder.
Project roots are detected by walking up from the opened document for
`_quarto.yml`, `_quarto.yaml`, `*.Rproj` or `.git`; otherwise the document folder
is used. Double-clicking `.qmd`, `.Rmd` and `.md` files calls the same guarded
`open_path` path used by menus/recent files, so unsaved changes prompt before a
switch. The current document is selected and revealed after open. The last
project root is persisted, and the tree auto-refreshes through
`QFileSystemModel`.

### AI chat and usage log

- `chat_panel.py` owns the AI tab, conversation, context selector, reply copy /
  insertion, and request metadata.
- `ai_client.py` is a minimal non-streaming OpenAI-compatible chat-completions
  client using `QNetworkAccessManager`; it is asynchronous and cancellable.
- `credentials.py` encrypts the API key with Windows DPAPI; the ciphertext is in
  QSettings and the key is never in the AI log.
- `ai_log.py` appends one JSONL record per request: timestamp, request id,
  endpoint, model, status, latency, context, document name, token usage, prompt
  messages and response (content logging can be disabled), and error/cancel
  details. The default is `ai-usage.jsonl` in the project root, falling back to
  the document folder or app data.
- The assistant does not edit the document automatically. **Insert reply** uses
  `QTextDocumentFragment.fromMarkdown` so the user reviews and inserts text into
  the rich model.
- Context is opt-in: none, current selection, or whole document (capped at
  16,000 characters). The log path is user-configurable.
- No background AI calls. A request is sent only when the user presses Send.

### Zotero citations

`citations.py` parses Better BibTeX `.bib` files and CSL JSON exports without
requiring Zotero to be running. The citation dialog searches keys/authors/titles/
years, supports multi-selection, and returns keys that `MainWindow` inserts as
Pandoc citations (`[@key]`, `[@key1; @key2]`). On first use it adds
`bibliography: "relative/path.bib"` to YAML if absent. The bibliography path is
also stored in Settings as a fallback. The file is re-read on each dialog open,
which works well with Better BibTeX auto-export.

### `sync.py`

- Debounced autosave (default 800 ms) in the main window.
- SHA-256 of the last written text is the baseline.
- Atomic write to a temporary file in the same folder, `fsync`, then
  `os.replace`.
- `QFileSystemWatcher` watches the file and its parent; after an atomic replace
  the file watch is re-added.
- An external change emits only once per distinct content hash. The main window
  reloads if clean, otherwise offers reload / keep / save-copy / cancel.
- File deletion is handled separately.

### Standalone Quarto / R integration

- `external.py` discovers `quarto.exe`, `Rscript.exe`, `pdflatex.exe` and
  `pandoc.exe` in PATH, `%ProgramFiles%`, `%LOCALAPPDATA%`, and the copies
  bundled with RStudio/Quarto. RStudio is not exposed in the UI.
- **Render PDF for `.qmd`** runs the standalone Quarto CLI
  (`quarto render file.qmd --to pdf`) in the project root, with R and LaTeX on
  PATH. **Render PDF for `.Rmd`** runs
  `rmarkdown::render(..., output_format='pdf_document')`.
- Quarto's Windows cache/codepage handling is fragile under non-ASCII paths and
  sandboxed temp folders, so the app supplies:
  - a writable `LOCALAPPDATA` fallback and a UTF-8 codepage cache;
  - an ASCII short path for Quarto/R temp files and the TeX font cache;
  - the user's original `R_LIBS_USER` so Quarto's R chunks can find packages.
- **TinyTeX installation** is offered when pdflatex is missing. It installs into
  the app's local TinyTeX folder with the `soul` package included, so
  underline/strikeout in PDF work.
- R gets a dedicated writable `rtemp` folder inside the app's data directory,
  because locked-down sessions and sandboxed child processes can make the system
  TEMP folder unusable.
- No process injection, no RStudio dependency in normal use. The app makes
  network calls only for the explicit TinyTeX installation (and future AI chat,
  if enabled).

## Formatting policy in detail

| Word-like feature | Rmd output | HTML | PDF/Word |
|---|---|---|---|
| Bold, italic, strike | `**`, `*`, `~~` | yes | yes (soul for strike) |
| Underline | `[text]{.underline}` | yes | yes, with `soul` LaTeX package |
| Heading levels | `#`… | yes | yes |
| Font family/size | `[text]{style="..."}` | yes | no |
| Colour/highlight | `[text]{style="color/background-color..."}` | yes | no |
| Alignment | fenced div `text-align` | yes | no |
| Line/paragraph spacing | fenced div `line-height/margin` | yes | no |
| Lists, quotes, tables | Markdown constructs | yes | yes |
| Links, images | Markdown links/images | yes | yes |
| R chunks / inline R | R Markdown fences / backticks | via knitr | via knitr |

This is why the app has a **Preserve visual formatting** toggle and why it is
**off by default** for the PDF target. The normal source uses only the first
column of the table; the HTML style layer is opt-in.

## Packaging

- `RmdStudio.spec` — PyInstaller one-file, windowed, with icon/version info and
  unused Qt modules excluded.
- `build.py` — builds and copies the exe to `release\Rmd Studio.exe`, then
  compiles the Inno Setup installer and writes `release\INSTALL.cmd`.
- `installer/RmdStudio.iss` — per-user Inno Setup installer, Start Menu/desktop
  shortcuts and uninstaller.
- `tools/sign.ps1` — Authenticode signing hook using a certificate in the
  current user's store; wired to `RMD_SIGN_THUMBPRINT`.
- `tools/make_icon.py` — generates the PNG/ICO from the QPainter logo.
- Runtime data lives in `%APPDATA%\Rmd Studio` with a `userdata` fallback next
  to the exe; the generated preview HTML is in that data folder.
- Images are copied into a sibling `assets/` folder; paths in the `.Rmd` stay
  relative and portable.

### Inno Setup path quirk

Some Inno Setup 6.7.3 builds fail to launch the setup executable from a release
folder whose path contains non-ASCII characters. The installed app itself runs
fine from a Unicode path, and the installer works when copied to an ASCII folder.
`INSTALL.cmd` stages the setup file in `%TEMP%` before launching it and is the
recommended entry point when the release folder path is not ASCII.

### Signing

The build supports an OV/EV-style Authenticode certificate from the current
user's certificate store:

```powershell
$env:RMD_SIGN_THUMBPRINT = "THUMBPRINT"
.\.venv\python build.py
```

The exe is signed before the installer is built, then the installer is signed.
A trusted certificate must be purchased/issued with the publisher's verified
identity. Options: OV certificate, EV certificate, or Azure Trusted Signing.
A self-signed certificate can validate the pipeline but will not remove
SmartScreen warnings.

## Tools / plugins that help this project

No runtime plugin is required. The recommended development additions are:

- **Python 3.12+** and **PySide6-Essentials 6.12** (installed in `.venv`).
- **PyInstaller 6.22** and **Pillow** for the exe and icon.
- **pytest** for the converter/sync/UI tests.
- **R** for code chunks and rmarkdown files.
- **Quarto CLI** for `.qmd`. A standalone installation is recommended; the app
  can also discover the copy bundled with RStudio.
- **Pandoc** for import and HTML previews. It can come from Quarto, RStudio or a
  standalone install.
- **RStudio** is optional and no longer exposed in the UI; it is only one
  possible source of bundled Quarto/Pandoc on a machine.
- **Inno Setup 6** for the installer, **GitHub CLI** for releases, and
  PowerShell's `Set-AuthenticodeSignature` for signing with an installed
  certificate.
- **TinyTeX** is installed through the app's Knit to PDF prompt, not a developer
  dependency. MiKTeX or TeX Live work too.
- **Optional:** `markdown-it-py` if we later replace the importer with a pure
  Python parser; `pyenchant` or the Windows Spell Checking API for spell check;
  PySide6-Addons/QtWebEngine only if we want an embedded rendered preview.

This version intentionally does not add a Node/Electron runtime, a cloud service,
or a database. They do not solve the Markdown mapping problem and make packaging
worse.

## Roadmap

1. Direct `.docx` import (Pandoc `-f docx`), with a review screen for styling.
2. Spell check using the Windows spell-check API.
3. Project-wide search/replace and a faster project index for large folders.
4. Embedded HTML preview (QWebEngine optional build) with a "no execution"
   Pandoc mode.
5. Footnotes/citations/cross-reference preservation in the importer.
6. Table cell spans → HTML table fallback when visual fidelity is requested.
7. CSS-class generation instead of inline styles for large documents, so the
   Rmd stays readable and a single `css:` file controls the look.
8. Code signing with a trusted OV/EV or Azure Trusted Signing certificate.
9. Streaming AI responses and provider-native Anthropic/Gemini adapters.
10. Match a specific institutional/build-log schema if one is required.
11. Optional tamper-evident AI log export (hash chain) for formal audit needs.
