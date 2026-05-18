$ErrorActionPreference = "Stop"

$CredPath = "$HOME\.ssh\.server_cred"
if (-not (Test-Path $CredPath)) {
    throw "Credential file not found at: $CredPath"
}

Write-Host "Reading credential from $CredPath..." -ForegroundColor Gray

# Decrypt the SecureString stored in the file
try {
    # File content is standard PowerShell SecureString export (DPAPI)
    $SecureString = Get-Content $CredPath | ConvertTo-SecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    $Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
} catch {
    throw "Failed to decrypt password. Error: $_"
}

if ([string]::IsNullOrWhiteSpace($Password)) {
    throw "Decrypted password is empty."
}

# Escape single quotes for bash single-quoted string
$EscapedPassword = $Password -replace "'", "'\''"

Write-Host "Updating Samba password for user 'm3trik' on 'm3trikserver'..." -ForegroundColor Cyan

# Remote command:
# Use parentheses to grouping echo commands, creating a single stream.
# Send 3 times to cover Sudo consumption.
$RemoteCmd = "(echo '$EscapedPassword'; echo '$EscapedPassword'; echo '$EscapedPassword') | sudo -S smbpasswd -a m3trik -s"

# Execute SSH
# Note: This assumes SSH key authentication is set up for the login itself.
ssh m3trik@m3trikserver $RemoteCmd

if ($LASTEXITCODE -eq 0) {
    Write-Host "Successfully updated Samba credentials." -ForegroundColor Green
} else {
    Write-Error "Failed to update Samba credentials. Exit Code: $LASTEXITCODE"
}
