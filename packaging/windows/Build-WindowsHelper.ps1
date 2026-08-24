[CmdletBinding()]
param(
    [string]$OutputRoot,
    [switch]$AllowDirty
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $FilePath $($Arguments -join ' ')"
    }
}

if ($env:OS -ne 'Windows_NT') {
    throw 'Windows helper packaging must run on Windows.'
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Windows helper packaging requires a 64-bit Windows host.'
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot 'artifacts\windows-helper'
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$BuildRoot = Join-Path $RepoRoot '.build\windows-helper'
$VenvRoot = Join-Path $BuildRoot 'venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$SpecPath = Join-Path $PSScriptRoot 'secure-messaging-helper.spec'
$RequirementsPath = Join-Path $PSScriptRoot 'build-requirements.txt'
$PackageInventory = Join-Path $BuildRoot 'packages.json'
$PyInstallerWork = Join-Path $BuildRoot 'pyinstaller-work'
$DistRoot = Join-Path $BuildRoot 'dist'
$BundleDir = Join-Path $DistRoot 'secure-messaging-helper'

Push-Location $RepoRoot
try {
    $SourceCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $SourceCommit) {
        throw 'Unable to resolve source commit.'
    }
    $DirtyText = (& git status --porcelain).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to determine source working-tree state.'
    }
    $SourceDirty = -not [string]::IsNullOrWhiteSpace($DirtyText)
    if ($SourceDirty -and -not $AllowDirty) {
        throw 'Working tree is dirty. Commit/stash changes or explicitly pass -AllowDirty for a non-release diagnostic build.'
    }

    if (Test-Path $BuildRoot) {
        Remove-Item -LiteralPath $BuildRoot -Recurse -Force
    }
    if (Test-Path $OutputRoot) {
        Remove-Item -LiteralPath $OutputRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

    Invoke-Checked -FilePath 'py' -Arguments @('-3.11', '-c', 'import struct,sys; assert sys.version_info[:2] == (3,11); assert struct.calcsize("P") == 8')
    Invoke-Checked -FilePath 'py' -Arguments @('-3.11', '-m', 'venv', $VenvRoot)
    Invoke-Checked -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $RequirementsPath)
    Invoke-Checked -FilePath $VenvPython -Arguments @('-c', 'import nio, vodozemac; print("Matrix E2EE imports: PASS")')

    $OldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $RepoRoot 'src'
        Invoke-Checked -FilePath $VenvPython -Arguments @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
        Invoke-Checked -FilePath $VenvPython -Arguments @('-m', 'compileall', '-q', 'src', 'packaging\windows')
    }
    finally {
        $env:PYTHONPATH = $OldPythonPath
    }

    Invoke-Checked -FilePath $VenvPython -Arguments @(
        '-m', 'PyInstaller', '--clean', '--noconfirm',
        '--distpath', $DistRoot,
        '--workpath', $PyInstallerWork,
        $SpecPath
    )

    $HelperPath = Join-Path $BundleDir 'secure-messaging-helper.exe'
    if (-not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) {
        throw "Packaged helper was not produced: $HelperPath"
    }

    $PackageJson = & $VenvPython -c 'import importlib.metadata as m, json; print(json.dumps([{"name": d.metadata["Name"], "version": d.version} for d in m.distributions() if d.metadata.get("Name")], sort_keys=True))'
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inventory resolved Python packages.'
    }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($PackageInventory, [string]$PackageJson, $Utf8NoBom)

    $PythonVersion = (& $VenvPython -c 'import platform; print(platform.python_version())').Trim()
    $PyInstallerVersion = (& $VenvPython -c 'import PyInstaller; print(PyInstaller.__version__)').Trim()
    $ManifestPath = Join-Path $BundleDir 'build-manifest.json'
    Invoke-Checked -FilePath $VenvPython -Arguments @(
        (Join-Path $PSScriptRoot 'write_build_manifest.py'),
        '--bundle-dir', $BundleDir,
        '--output', $ManifestPath,
        '--source-commit', $SourceCommit,
        '--source-dirty', $(if ($SourceDirty) { 'true' } else { 'false' }),
        '--python-version', $PythonVersion,
        '--pyinstaller-version', $PyInstallerVersion,
        '--packages-json', $PackageInventory
    )

    $SmokeState = Join-Path $BuildRoot 'helper-smoke-state'
    $Vector = Get-Content -LiteralPath (Join-Path $RepoRoot 'test-vectors\message-envelope-basic.json') -Raw | ConvertFrom-Json
    $Vector.message_id = [guid]::NewGuid().ToString()
    $Vector.created_at = [DateTimeOffset]::UtcNow.ToString('o')
    $Vector.expires_at = [DateTimeOffset]::UtcNow.AddMinutes(5).ToString('o')
    $Vector.idempotency_key = 'windows-package-smoke-' + [guid]::NewGuid().ToString('N')
    $RequestId = [guid]::NewGuid().ToString('N')
    $RequestJson = [ordered]@{
        op = 'send'
        request_id = $RequestId
        envelope = $Vector
    } | ConvertTo-Json -Depth 20 -Compress

    $OldTransport = $env:SECURE_MESSAGING_TEST_TRANSPORT
    $OldStateDir = $env:SECURE_MESSAGING_STATE_DIR
    try {
        $env:SECURE_MESSAGING_TEST_TRANSPORT = 'memory'
        $env:SECURE_MESSAGING_STATE_DIR = $SmokeState
        $ResponseText = $RequestJson | & $HelperPath --stdio-once
        if ($LASTEXITCODE -ne 0) {
            throw "Packaged helper smoke exited with $LASTEXITCODE"
        }
        $Response = $ResponseText | ConvertFrom-Json
        if (-not $Response.accepted -or $Response.request_id -ne $RequestId -or $Response.message_id -ne $Vector.message_id -or $null -ne $Response.error_code) {
            throw 'Packaged helper smoke returned an unexpected stdio-v1 response.'
        }

        $DotnetState = Join-Path $BuildRoot 'dotnet-smoke-state'
        $env:SECURE_MESSAGING_STATE_DIR = $DotnetState
        $env:SECURE_MESSAGING_HELPER_PATH = $HelperPath
        Invoke-Checked -FilePath 'dotnet' -Arguments @(
            'run', '--project', 'tests-dotnet\SecureMessaging.Conformance\SecureMessaging.Conformance.csproj', '--configuration', 'Release'
        )
    }
    finally {
        $env:SECURE_MESSAGING_TEST_TRANSPORT = $OldTransport
        $env:SECURE_MESSAGING_STATE_DIR = $OldStateDir
        Remove-Item Env:SECURE_MESSAGING_HELPER_PATH -ErrorAction SilentlyContinue
    }

    Copy-Item -LiteralPath $BundleDir -Destination $OutputRoot -Recurse -Force
    $FinalBundle = Join-Path $OutputRoot 'secure-messaging-helper'
    $FinalManifest = Join-Path $FinalBundle 'build-manifest.json'
    $FinalManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $FinalManifest).Hash.ToLowerInvariant()

    [ordered]@{
        result = 'PASS'
        source_commit = $SourceCommit
        source_dirty = $SourceDirty
        bundle = $FinalBundle
        helper = Join-Path $FinalBundle 'secure-messaging-helper.exe'
        manifest = $FinalManifest
        manifest_sha256 = $FinalManifestHash
        protocol = 'stdio-v1'
        target = 'win-x64'
    } | ConvertTo-Json -Depth 4
}
finally {
    Pop-Location
}
