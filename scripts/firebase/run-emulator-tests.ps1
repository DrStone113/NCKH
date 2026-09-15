[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$env:DEBUG = ''

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$firebaseDir = Join-Path $repoRoot 'firebase'
$firebaseConfig = Join-Path $repoRoot 'firebase.json'

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found."
    }
    return $command
}

Require-Command 'node' | Out-Null
Require-Command 'npm' | Out-Null
$firebaseExecutable = Get-Command 'firebase.cmd' -ErrorAction SilentlyContinue
if (-not $firebaseExecutable) {
    $firebaseExecutable = Require-Command 'firebase'
}
$firebaseCommand = $firebaseExecutable.Source

$firebaseJavaHome = [Environment]::GetEnvironmentVariable(
    'FIREBASE_JAVA_HOME',
    'User'
)
if ($firebaseJavaHome -and (Test-Path (Join-Path $firebaseJavaHome 'bin\java.exe'))) {
    $env:JAVA_HOME = $firebaseJavaHome
    $env:Path = "$(Join-Path $firebaseJavaHome 'bin');$env:Path"
} elseif (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    $userJavaHome = [Environment]::GetEnvironmentVariable('JAVA_HOME', 'User')
    if ($userJavaHome -and (Test-Path (Join-Path $userJavaHome 'bin\java.exe'))) {
        $env:JAVA_HOME = $userJavaHome
        $env:Path = "$(Join-Path $userJavaHome 'bin');$env:Path"
    }
}
Require-Command 'java' | Out-Null

$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -notin @(20, 22, 24)) {
    Write-Warning "Firebase Emulator tooling supports Node 20, 22 or 24; current major is $nodeMajor."
}

if (-not (Test-Path (Join-Path $firebaseDir 'node_modules'))) {
    & npm ci --prefix $firebaseDir
    if ($LASTEXITCODE -ne 0) {
        throw 'npm ci failed for Firebase rule tests.'
    }
}

Push-Location $repoRoot
try {
    & $firebaseCommand emulators:exec `
        --only firestore `
        --project demo-healthcare-f1 `
        --config $firebaseConfig `
        'npm --prefix firebase run test:rules'
    if ($LASTEXITCODE -ne 0) {
        throw 'Firestore emulator rule tests failed.'
    }
} finally {
    Pop-Location
}
