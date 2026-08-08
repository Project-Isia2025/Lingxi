# Install MinGit to user profile (no admin required)
# Usage: .\scripts\install_git_portable.ps1
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\MinGit"
)

$ErrorActionPreference = "Stop"

function Find-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $paths = @(
        "$InstallDir\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe",
        "C:\Program Files\Git\cmd\git.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$existing = Find-GitExe
if ($existing) {
    Write-Host "Git already available: $existing"
    & $existing --version
    exit 0
}

$tag = "v2.55.0.windows.3"
$fileName = "MinGit-2.55.0.3-64-bit.zip"
$url = "https://github.com/git-for-windows/git/releases/download/$tag/$fileName"
$cache = Join-Path $env:TEMP $fileName

Write-Host "Downloading MinGit from GitHub ..."
if (-not (Test-Path $cache)) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $cache -UseBasicParsing
    } catch {
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if (-not $curl) { throw }
        Write-Host "Invoke-WebRequest failed, trying curl.exe ..."
        & curl.exe -fsSL -o $cache $url
        if ($LASTEXITCODE -ne 0) { throw "curl download failed with exit code $LASTEXITCODE" }
    }
}

if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Expand-Archive -Path $cache -DestinationPath $InstallDir -Force

$gitExe = Join-Path $InstallDir "cmd\git.exe"
if (-not (Test-Path $gitExe)) {
    throw "git.exe not found after extract: $gitExe"
}

$gitCmdDir = Join-Path $InstallDir "cmd"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$gitCmdDir*") {
    $newPath = if ($userPath) { "$userPath;$gitCmdDir" } else { $gitCmdDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}
$env:Path = "$env:Path;$gitCmdDir"

Write-Host ""
Write-Host "Git installed successfully."
& $gitExe --version
Write-Host ""
Write-Host "You can continue in this shell, or reopen PowerShell and run:"
Write-Host "  git --version"
Write-Host "  .\scripts\setup_git_repo.ps1 -RemoteUrl https://github.com/YOUR_ORG/YOUR_REPO.git"
