$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Join-Path (Get-Location) "venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    throw "Project environment not found. Create it with: py -3.12 -m venv .venv"
}

& $Python -m pip install --upgrade "pyinstaller>=6.10"
if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
& $Python -m PyInstaller packaging/smolchat-Windows.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
Write-Host "Built dist\smolchat.exe"
