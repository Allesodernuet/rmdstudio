# Release and GitHub notes

## Current state

- Inno Setup 6.7.3 is installed and `installer/RmdStudio.iss` compiles.
  Inno Setup 6.7.3 prints **“Non-commercial use only”**; a commercial license is
  required if you distribute this commercially. Personal/academic use is fine
  under its non-commercial terms.
- GitHub CLI 2.105 is installed.
- A local git repository exists on branch `main` with the source committed.
- There is no GitHub remote and `gh` is not authenticated yet.
- The build is unsigned; see `SIGNING.md`.

## Build

```powershell
.\.venv\python build.py
```

Outputs:

- `release\Rmd Studio.exe`
- `release\Rmd Studio Setup 0.2.0.exe`
- `release\INSTALL.cmd`

`INSTALL.cmd` stages the setup file in `%TEMP%` before launching it. This works
around the Inno Setup launch failure observed when the setup file itself sits in
the workspace's non-ASCII `züg` path. The installed app runs fine from a Unicode
path.

To sign both exe and installer:

```powershell
$env:RMD_SIGN_THUMBPRINT = "CERT_THUMBPRINT"
.\.venv\python build.py
```

## First GitHub push

Run these once, after choosing the repository name and visibility:

```powershell
gh auth login
gh repo create rmd-studio --private --source=. --remote=origin --push
```

If you already created an empty repository:

```powershell
git remote add origin https://github.com/<you>/rmd-studio.git
git push -u origin main
```

`gh` installed its executable under `C:\Program Files\GitHub CLI`. Open a new
terminal if the current one does not see the updated PATH.

## Create a release

Build first, then:

```powershell
gh release create v0.2.0 `
  "release/Rmd Studio Setup 0.2.0.exe" `
  "release/Rmd Studio.exe" `
  --title "Rmd Studio 0.2.0" `
  --notes "Quarto/R Markdown project browser, work log, standalone Render PDF." `
  --draft
```

Review the draft, then publish it. Uploading the unsigned exe is fine for
private testing; for public distribution, sign it first.
