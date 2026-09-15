[CmdletBinding()]
param(
    [string]$ProjectId = 'healthcare-191d8',
    [string]$AndroidPackage = 'com.example.app',
    [switch]$ApplyCloud,
    [switch]$CreateMissingAndroidApp,
    [switch]$RegisterSha,
    [switch]$DownloadGoogleServices,
    [switch]$ConfigureFlutterFire,
    [switch]$CreateFirestore,
    [switch]$DeployFirestore,
    [switch]$DeployAuth,
    [string]$SupportEmail,
    [string]$FirestoreLocation = 'asia-southeast1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$env:DEBUG = ''

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$mobileRoot = Join-Path $repoRoot 'apps\mobile'
$androidRoot = Join-Path $mobileRoot 'android'
$firebaseConfig = Join-Path $repoRoot 'firebase.json'
$authTemplate = Join-Path $repoRoot 'firebase\auth.providers.template.json'
$generatedDir = Join-Path $repoRoot 'firebase\.generated'
$googleServices = Join-Path $mobileRoot 'android\app\google-services.json'
$pinnedDart = Join-Path $mobileRoot '.fvm\flutter_sdk\bin\dart.bat'

function Find-AndroidJdk {
    $candidates = @(
        $env:JAVA_HOME,
        'C:\Program Files\Android\Android Studio\jbr'
    )
    $microsoftJdkRoot = Join-Path $env:LOCALAPPDATA 'Programs\Microsoft\jdk-17-bundle'
    if (Test-Path -LiteralPath $microsoftJdkRoot) {
        $candidates += Get-ChildItem -LiteralPath $microsoftJdkRoot -Directory |
            Sort-Object Name -Descending |
            Select-Object -ExpandProperty FullName
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'bin\java.exe'))) {
            return $candidate
        }
    }
    return $null
}

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found."
    }
    return $command
}

function Invoke-FirebaseJson([string[]]$Arguments) {
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = (& $script:FirebaseCommand @Arguments --json 2>$null | Out-String)
        $firebaseExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($firebaseExitCode -ne 0) {
        try {
            $parsedError = $output | ConvertFrom-Json
            throw "Firebase CLI failed: $($parsedError.error)"
        } catch {
            throw "Firebase CLI failed: $output"
        }
    }
    return $output | ConvertFrom-Json
}

function Require-CloudApproval([string]$Operation) {
    if (-not $ApplyCloud) {
        throw "$Operation changes cloud state and requires -ApplyCloud."
    }
}

function App-PackageName($App) {
    foreach ($property in @('packageName', 'namespace', 'androidPackageName')) {
        if ($App.PSObject.Properties.Name -contains $property) {
            return [string]$App.$property
        }
    }
    return ''
}

$firebaseExecutable = Get-Command 'firebase.cmd' -ErrorAction SilentlyContinue
if (-not $firebaseExecutable) {
    $firebaseExecutable = Require-Command 'firebase'
}
$script:FirebaseCommand = $firebaseExecutable.Source
if (-not (Test-Path $pinnedDart)) {
    throw "Pinned Dart SDK is missing at $pinnedDart"
}

Write-Host "Firebase CLI: $(& $script:FirebaseCommand --version 2>$null)"
Write-Host "Pinned SDK: $(& $pinnedDart --version 2>&1)"
Write-Host "Mode: $(if ($ApplyCloud) { 'APPLY_CLOUD' } else { 'AUDIT_ONLY' })"

$projectResponse = Invoke-FirebaseJson @('projects:list')
$project = @($projectResponse.result) |
    Where-Object { $_.projectId -eq $ProjectId } |
    Select-Object -First 1
if (-not $project) {
    throw "Firebase project '$ProjectId' is not accessible. Run 'firebase login' with an authorized account."
}
Write-Host "Verified project: $($project.projectId) / $($project.projectNumber)"

$appsResponse = Invoke-FirebaseJson @('apps:list', 'ANDROID', '--project', $ProjectId)
$androidApp = @($appsResponse.result) |
    Where-Object { (App-PackageName $_) -eq $AndroidPackage } |
    Select-Object -First 1

if (-not $androidApp -and $CreateMissingAndroidApp) {
    Require-CloudApproval 'Creating the Android Firebase app'
    $created = Invoke-FirebaseJson @(
        'apps:create', 'ANDROID', 'Health App Android',
        '--package-name', $AndroidPackage,
        '--project', $ProjectId
    )
    $androidApp = $created.result
}

if (-not $androidApp) {
    Write-Warning "No Android Firebase app matches package '$AndroidPackage'."
} else {
    Write-Host "Android Firebase app: $($androidApp.appId) ($AndroidPackage)"
}

$gradleWrapper = Join-Path $androidRoot 'gradlew.bat'
if (-not (Test-Path $gradleWrapper)) {
    throw "Gradle wrapper is missing at $gradleWrapper"
}
$androidJdk = Find-AndroidJdk
if (-not $androidJdk) {
    throw 'A JDK 17 installation is required to run the Android signing report.'
}
$previousJavaHome = $env:JAVA_HOME
$env:JAVA_HOME = $androidJdk
Push-Location $androidRoot
try {
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $signingReport = (& $gradleWrapper -q signingReport 2>&1 | Out-String)
        $gradleExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($gradleExitCode -ne 0) {
        throw "Gradle signingReport failed: $signingReport"
    }
} finally {
    Pop-Location
    $env:JAVA_HOME = $previousJavaHome
}

$sha1 = [regex]::Matches($signingReport, '(?m)^SHA1:\s*([A-F0-9:]+)\s*$') |
    ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique -First 1
$sha256 = [regex]::Matches($signingReport, '(?m)^SHA-256:\s*([A-F0-9:]+)\s*$') |
    ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique -First 1
if (-not $sha1 -or -not $sha256) {
    throw 'Could not parse SHA-1/SHA-256 from the actual Gradle signingReport.'
}
Write-Host "Local SHA-1: $sha1"
Write-Host "Local SHA-256: $sha256"

if ($androidApp) {
    $remoteShaResponse = Invoke-FirebaseJson @(
        'apps:android:sha:list', $androidApp.appId, '--project', $ProjectId
    )
    $remoteHashes = @($remoteShaResponse.result) | ForEach-Object {
        if ($_ -is [string]) {
            $_
        } elseif ($_.PSObject.Properties.Name -contains 'shaHash') {
            $_.shaHash
        } elseif ($_.PSObject.Properties.Name -contains 'certHash') {
            $_.certHash
        }
    }
    foreach ($hash in @($sha1, $sha256)) {
        if ($remoteHashes -contains $hash) {
            Write-Host "Registered SHA: $hash"
        } elseif ($RegisterSha) {
            Require-CloudApproval "Registering SHA $hash"
            Invoke-FirebaseJson @(
                'apps:android:sha:create', $androidApp.appId, $hash,
                '--project', $ProjectId
            ) | Out-Null
            Write-Host "Registered missing SHA: $hash"
        } else {
            Write-Warning "Missing Firebase SHA: $hash"
        }
    }
}

$databasesResponse = Invoke-FirebaseJson @(
    'firestore:databases:list', '--project', $ProjectId
)
$defaultDatabase = @($databasesResponse.result) | Where-Object {
    $_.name -match '/databases/\(default\)$' -or $_.databaseId -eq '(default)'
} | Select-Object -First 1
if (-not $defaultDatabase -and $CreateFirestore) {
    Require-CloudApproval 'Creating the default Firestore database'
    Invoke-FirebaseJson @(
        'firestore:databases:create', '(default)',
        '--location', $FirestoreLocation,
        '--delete-protection', 'ENABLED',
        '--project', $ProjectId
    ) | Out-Null
    Write-Host "Created protected Firestore database in $FirestoreLocation"
} elseif ($defaultDatabase) {
    Write-Host "Default Firestore database exists: $($defaultDatabase.locationId)"
} else {
    Write-Warning 'The default Firestore database does not exist.'
}

if ($DownloadGoogleServices) {
    Require-CloudApproval 'Downloading google-services.json'
    if (-not $androidApp) { throw 'Android Firebase app is required.' }
    & $script:FirebaseCommand apps:sdkconfig ANDROID $androidApp.appId `
        --project $ProjectId --out $googleServices
    if ($LASTEXITCODE -ne 0) { throw 'Failed to download google-services.json.' }
    Write-Host "Downloaded official Android config to $googleServices"
}

if ($ConfigureFlutterFire) {
    Require-CloudApproval 'Running FlutterFire configure'
    Push-Location $mobileRoot
    try {
        & $pinnedDart pub global run flutterfire_cli:flutterfire configure `
            --project $ProjectId `
            --platforms android,web `
            --android-package-name $AndroidPackage `
            --android-out android/app/google-services.json `
            --out lib/firebase_options.dart `
            --overwrite-firebase-options `
            --yes
        if ($LASTEXITCODE -ne 0) { throw 'FlutterFire configure failed.' }
    } finally {
        Pop-Location
    }
}

if ($DeployFirestore) {
    Require-CloudApproval 'Deploying Firestore rules and indexes'
    & (Join-Path $PSScriptRoot 'run-emulator-tests.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Rule tests did not pass; deployment stopped.' }
    & $script:FirebaseCommand deploy --only firestore --project $ProjectId --config $firebaseConfig
    if ($LASTEXITCODE -ne 0) { throw 'Firestore deployment failed.' }
}

if ($DeployAuth) {
    Require-CloudApproval 'Deploying Firebase Authentication providers'
    if (-not $SupportEmail -or $SupportEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
        throw '-DeployAuth requires a valid human-owned -SupportEmail.'
    }
    $baseConfig = Get-Content -Raw -Encoding utf8 $firebaseConfig | ConvertFrom-Json
    $authConfig = Get-Content -Raw -Encoding utf8 $authTemplate | ConvertFrom-Json
    $authConfig.auth.providers.googleSignIn.supportEmail = $SupportEmail
    $baseConfig | Add-Member -NotePropertyName auth -NotePropertyValue $authConfig.auth
    New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
    $generatedConfig = Join-Path $generatedDir 'firebase.auth.json'
    $baseConfig | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $generatedConfig
    & $script:FirebaseCommand deploy --only auth --project $ProjectId --config $generatedConfig
    if ($LASTEXITCODE -ne 0) { throw 'Authentication provider deployment failed.' }
}

Write-Host 'Firebase bootstrap completed without destructive operations.'
