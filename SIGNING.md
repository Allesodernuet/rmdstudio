# Code signing

## Current status

- `tools/sign.ps1` works and has been tested with a temporary self-signed
  certificate; the signature was present but not trusted (as expected).
- The release build is currently **unsigned**.
- Obtaining a trusted certificate requires your verified identity and, usually,
  payment. I cannot complete that step on your behalf.
- `build.py` can sign both the app exe and the Inno Setup installer when a
  certificate is available.

## What you need to choose

### 1. Azure Trusted Signing

Cloud-based signing. No USB token. Requires an Azure subscription and identity
validation for the publisher. Signing is done through Microsoft's service and
usually integrates well into CI. It has a different signing command/tool than
`tools/sign.ps1`.

Best if you already have Azure or want to avoid a hardware token.

### 2. OV code-signing certificate

Purchased from a public CA (Sectigo, DigiCert, Certum, etc.). Publisher identity
is validated. Usually delivered as a `.pfx` or installed on a hardware token.
Cheaper than EV, but SmartScreen reputation is built over time.

### 3. EV code-signing certificate

Highest validation level. Usually hardware token/HSM. More expensive. It is the
most direct route to established publisher trust.

### 4. Self-signed certificate

Only for testing the signing pipeline. Windows does not trust it. It will not
remove SmartScreen warnings.

## If you have an OV/EV certificate installed

1. Find the thumbprint:

   ```powershell
   Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
       Select-Object Subject, Thumbprint, NotAfter
   ```

2. Build and sign:

   ```powershell
   $env:RMD_SIGN_THUMBPRINT = "THE_THUMBPRINT"
   .\.venv\python build.py
   ```

3. Verify:

   ```powershell
   Get-AuthenticodeSignature "release\Rmd Studio.exe"
   Get-AuthenticodeSignature "release\Rmd Studio Setup 0.1.0.exe"
   ```

The build signs the app exe before Inno Setup compiles the installer, then signs
the installer. Both signatures are timestamped with DigiCert's public timestamp
service.

For a hardware-token certificate, install the vendor CSP/KSP, connect the token,
and run the script in the same user session. If your CA only supports
`signtool.exe`, use its Windows SDK tool instead of `tools/sign.ps1`; the rest of
the pipeline is unchanged.

## What I need from you to finish it

- Which route: Azure Trusted Signing, OV, or EV.
- Legal publisher name and the identity/billing details the CA requires.
- For OV/EV: install the certificate/token locally and give me the thumbprint
  (never send the private key or password in chat).
- For Azure: the Azure tenant/subscription and a Trusted Signing account after
  identity verification; then we can wire its signing command into `build.py`.

Without that, the installer and exe remain unsigned and SmartScreen will warn.
