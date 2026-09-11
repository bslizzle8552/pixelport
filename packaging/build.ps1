param([ValidateSet('Onedir', 'Onefile')][string]$Format = 'Onedir')

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$originalPath = $env:PATH
Push-Location $repoRoot
try {
    $pythonBase = & $python -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate build interpreter' }
    # Prevent DLL discovery from unrelated tools in the caller's PATH.
    $env:PATH = "$pythonBase;$pythonBase\DLLs;$env:SystemRoot\System32;$env:SystemRoot"
    if ($Format -eq 'Onefile') {
        & $python -m PyInstaller --noconfirm --clean --distpath dist/onefile --workpath build/onefile packaging/pixelport-onefile.spec
    } else {
        & $python -m PyInstaller --noconfirm --clean packaging/pixelport.spec
    }
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
