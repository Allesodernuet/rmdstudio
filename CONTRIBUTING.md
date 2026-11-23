# Contributing

## Requirements

- Windows 10/11
- Python 3.12+
- R and Rscript for R chunks and `.Rmd` rendering
- Quarto CLI for `.qmd` rendering
- Pandoc for import and HTML previews
- LaTeX (TinyTeX, MiKTeX or TeX Live) for PDF output
- Inno Setup 6 for the Windows installer

Plain Markdown editing does not require R, Quarto or LaTeX. The app discovers the
other tools on PATH and in common install locations. Paths can be overridden in
Settings.

## Development

```powershell
python -m venv .venv
.\.venv\pip install -r requirements-dev.txt
.\.venv\python launcher.py
```

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\python -m pytest -q
```

## Build

```powershell
.\.venv\python build.py
```

This creates:

- `release\Rmd Studio.exe`
- `release\Rmd Studio Setup <version>.exe`
- `release\INSTALL.cmd`

`INSTALL.cmd` stages the installer in the system temp directory before launching
it. This also makes the installer work when the release directory path contains
non-ASCII characters or when GitHub changes spaces in asset names to dots.

The Inno Setup 6.7.3 compiler reports **non-commercial use only**. Commercial
distribution requires an Inno Setup commercial license.

## Signing

The release build is unsigned by default. To sign the executable and installer
with an Authenticode certificate installed for the current user:

```powershell
$env:RMD_SIGN_THUMBPRINT = "CERTIFICATE_THUMBPRINT"
.\.venv\python build.py
```

The build signs the exe before compiling the installer, then signs the
installer. `tools/sign.ps1` uses PowerShell's `Set-AuthenticodeSignature` and
DigiCert's timestamp service. A self-signed certificate is suitable only for
testing the signing pipeline; Windows does not trust it.

## Release

Build first, then create a draft GitHub release with the exe, installer,
`INSTALL.cmd` and `READ ME.txt` as assets. Review the draft before publishing.
Unsigned binaries trigger Windows SmartScreen warnings.
