<#
.SYNOPSIS
    Retrieves the stored server credential, diagnoses Android connectivity, and optionally types the password.

.DESCRIPTION
    1. Authenticates current user against the server creds.
    2. Checks Android device connectivity to server (Ping, DNS).
    3. Types the password into the Android device to ensure no typos.
#>
param(
    [switch]$Type,
    [switch]$Fix
)

$ErrorActionPreference = "Stop"

# --- LOCATE ADB ---
$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$ADBPath = Join-Path $RepoRoot "androidtk\androidtk\bin\platform-tools\adb.exe"

if (-not (Test-Path $ADBPath)) {
    # Fallback to system ADB
    if (Get-Command adb -ErrorAction SilentlyContinue) {
        $ADBPath = "adb"
    } else {
        Write-Warning "ADB not found. Integration disabled."
        $ADBPath = $null
    }
}

# --- RETRIEVE CREDENTIALS ---
$CredPath = "$HOME\.ssh\.server_cred"
if (-not (Test-Path $CredPath)) {
    throw "Credential file not found at: $CredPath"
}

Write-Host "Reading credential..." -ForegroundColor Gray
try {
    $SecureString = Get-Content $CredPath | ConvertTo-SecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    $Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
} catch {
    throw "Decryption failed. $_"
}

Write-Host "`nPassword: " -NoNewline
Write-Host $Password -ForegroundColor Cyan

# --- DIAGNOSTICS ---
if ($ADBPath) {
    Write-Host "`n[ DIAGNOSTICS ]" -ForegroundColor Yellow
    $Devs = & $ADBPath devices
    if ($Devs.Count -lt 2) {
        Write-Warning "No Android device connected."
    } else {
        # 1. Get Phone IP
        $PhoneIP = & $ADBPath shell ip -f inet addr show wlan0 | Select-String "inet (\d+\.\d+\.\d+\.\d+)"
        if ($PhoneIP.Matches.Groups[1].Value) {
            $IP = $PhoneIP.Matches.Groups[1].Value
            Write-Host "Phone IP: $IP" -ForegroundColor Gray
        } else {
            Write-Warning "Could not determine Phone IP (WiFi off?)."
        }

        # 2. Check Reachability
        Write-Host "Checking server reachability..." -NoNewline
        $Ping = & $ADBPath shell ping -c 1 -W 2 m3trikserver
        if ($Ping -match "1 packets transmitted, 1 received") {
            Write-Host " OK (Hostname resolves)" -ForegroundColor Green
        } else {
            Write-Host " FAIL" -ForegroundColor Red
            Write-Warning "Phone cannot resolve 'm3trikserver'. Try using IP: 192.168.1.100"
            
            $PingIP = & $ADBPath shell ping -c 1 -W 2 192.168.1.100
            if ($PingIP -match "1 received") {
                Write-Host "IP (192.168.1.100) is reachable." -ForegroundColor Green
            } else {
                Write-Error "Phone cannot reach Server IP. Check WiFi connection!"
            }
        }
    }
}

# --- ACTION ---
if ($Type -and $ADBPath) {
    Write-Host "`n[ ACTION ]" -ForegroundColor Yellow
    Write-Host "Open the password field on your phone..."
    Pause
    
    Write-Host "Typing in 3..."
    Start-Sleep 1
    Write-Host "2..."
    Start-Sleep 1
    Write-Host "1..."
    Start-Sleep 1
    
    $Escaped = $Password -replace "'", "'\''" -replace '[&|<>;$()!]', '\$&'
    # Use single quotes for outer shell
    & $ADBPath shell input text "'$Escaped'"
    Write-Host "Done." -ForegroundColor Green
}
