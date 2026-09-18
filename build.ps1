# Rebuild the Windows GUI without relying on conda activation.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$pythonExe = 'C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$buildDirectory = Join-Path $projectRoot 'build'
$applicationDirectory = Join-Path $projectRoot 'dist\MusicMetadataCleaner'
$specFile = Join-Path $projectRoot 'packaging\MusicMetadataCleaner.spec'
$executable = Join-Path $applicationDirectory 'MusicMetadataCleaner.exe'
$buildExitCode = 0
$originalPath = $env:PATH
$originalPythonPath = $env:PYTHONPATH

function Remove-BuildOutput {
    param([Parameter(Mandatory = $true)][string]$Target)

    # Only these two exact outputs may be removed. Refuse junctions/symlinks,
    # including an aliased dist parent, before any recursive deletion.
    $absoluteTarget = [System.IO.Path]::GetFullPath($Target)
    if ($absoluteTarget -notin @($buildDirectory, $applicationDirectory) -or
        -not $absoluteTarget.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an unexpected path: $absoluteTarget"
    }
    $ancestor = $absoluteTarget
    while ($ancestor -and $ancestor -ne $projectRoot) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "Refusing to clean linked output: $ancestor"
            }
        }
        $ancestor = Split-Path -Path $ancestor -Parent
    }
    if (Test-Path -LiteralPath $absoluteTarget) {
        $linkedChildren = Get-ChildItem -LiteralPath $absoluteTarget -Recurse -Force |
            Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }
        if ($linkedChildren) {
            throw "Refusing to clean output containing links: $absoluteTarget"
        }
        Remove-Item -LiteralPath $absoluteTarget -Recurse -Force
    }
}

Push-Location -LiteralPath $projectRoot
try {
    Write-Host '========================================'
    Write-Host 'Music Metadata Cleaner - Windows Build'
    Write-Host '========================================'
    Write-Host "`nPython:`n$pythonExe"

    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw "Python executable not found: $pythonExe"
    }
    & $pythonExe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'PyInstaller is not installed in the music-cleaner environment.'
        Write-Host "Install it explicitly with:`n& '$pythonExe' -m pip install pyinstaller"
        throw 'PyInstaller validation failed. No dependencies were installed.'
    }
    if (-not (Test-Path -LiteralPath $specFile -PathType Leaf)) {
        throw "PyInstaller spec not found: $specFile"
    }

    # Do not collect incompatible DLLs from unrelated tools on the caller's PATH
    # (for example a Poppler ICU DLL instead of Windows' Qt-compatible ICU).
    $environmentRoot = Split-Path -Path $pythonExe -Parent
    $env:PATH = @(
        $environmentRoot
        (Join-Path $environmentRoot 'Library\bin')
        (Join-Path $environmentRoot 'Scripts')
        (Join-Path $environmentRoot 'Lib\site-packages\PySide6')
        (Join-Path $env:SystemRoot 'System32')
        $env:SystemRoot
    ) -join [System.IO.Path]::PathSeparator
    $env:PYTHONPATH = $null

    Write-Host "`nCleaning previous build..."
    Remove-BuildOutput -Target $buildDirectory
    Remove-BuildOutput -Target $applicationDirectory

    Write-Host "`nRunning PyInstaller (windowed, onedir)..."
    # A spec owns --windowed/--onedir: console=False + EXE/COLLECT.
    # PyInstaller does not accept those makespec flags when building a spec.
    & $pythonExe -m PyInstaller --noconfirm --clean --workpath $buildDirectory --distpath (Join-Path $projectRoot 'dist') $specFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE. Review its output above."
    }
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "PyInstaller finished without the expected executable: $executable"
    }

    Write-Host "`nBuild completed successfully."
    Write-Host "`nExecutable:`n$executable"
    Write-Host 'Distribute the entire MusicMetadataCleaner folder, including _internal.'
}
catch {
    Write-Host "`nBuild failed: $($_.Exception.Message)" -ForegroundColor Red
    $buildExitCode = 1
}
finally {
    $env:PATH = $originalPath
    $env:PYTHONPATH = $originalPythonPath
    Pop-Location
}
exit $buildExitCode
