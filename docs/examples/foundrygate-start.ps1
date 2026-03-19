$ErrorActionPreference = "Stop"

$RepoRoot = Join-Path $env:USERPROFILE "services\foundrygate"
$ConfigDir = Join-Path $env:APPDATA "FoundryGate"
$StateDir = Join-Path $env:LOCALAPPDATA "FoundryGate"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ConfigPath = Join-Path $ConfigDir "config.yaml"
$EnvPath = Join-Path $ConfigDir "foundrygate.env"
$DbPath = Join-Path $StateDir "foundrygate.db"

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if (Test-Path $EnvPath) {
    Get-Content $EnvPath | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
            return
        }
        $parts = $_ -split '=', 2
        if ($parts.Length -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
        }
    }
}

$env:FOUNDRYGATE_DB_PATH = $DbPath

& $PythonExe -m foundrygate --config $ConfigPath
