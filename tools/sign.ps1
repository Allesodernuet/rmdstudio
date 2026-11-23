#requires -Version 5.1
<#
.SYNOPSIS
    Sign a Windows executable or installer with an Authenticode certificate.

.DESCRIPTION
    Uses a code-signing certificate from the current user's certificate store.
    The certificate must have an accessible private key. Timestamping is enabled
    by default so signatures remain valid after the certificate expires.

    For an OV/EV certificate on a hardware token, make sure its CSP/KSP is
    installed and the token is connected. Azure Trusted Signing uses a different
    signing tool and is not covered by this script.

.EXAMPLE
    .\tools\sign.ps1 -File "release\Rmd Studio.exe" -Thumbprint "ABCDEF..."

.EXAMPLE
    $env:RMD_SIGN_THUMBPRINT = "ABCDEF..."
    .\tools\sign.ps1 -File "release\Rmd Studio Setup 0.1.0.exe"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$File,

    [string]$Thumbprint = $env:RMD_SIGN_THUMBPRINT,

    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $File)) {
    throw "File not found: $File"
}
if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
    throw "No certificate thumbprint supplied. Pass -Thumbprint or set RMD_SIGN_THUMBPRINT."
}

$normalized = $Thumbprint -replace '\s', ''
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.Thumbprint -eq $normalized -and $_.HasPrivateKey
} | Select-Object -First 1

if (-not $cert) {
    throw "No code-signing certificate with private key found for thumbprint $normalized in Cert:\CurrentUser\My."
}

Write-Host "Signing $File"
Write-Host "Certificate: $($cert.Subject) [$($cert.Thumbprint)]"

$parameters = @{
    FilePath = $File
    Certificate = $cert
    HashAlgorithm = "SHA256"
}
if (-not [string]::IsNullOrWhiteSpace($TimestampServer)) {
    $parameters["TimestampServer"] = $TimestampServer
}
$signature = Set-AuthenticodeSignature @parameters

$result = Get-AuthenticodeSignature -FilePath $File
Write-Host "Signature status: $($result.Status)"
if ($result.SignerCertificate) {
    Write-Host "Signer: $($result.SignerCertificate.Subject)"
}
if ($result.Status -notin @("Valid", "UnknownError")) {
    throw "Signing failed with status $($result.Status): $($result.StatusMessage)"
}
