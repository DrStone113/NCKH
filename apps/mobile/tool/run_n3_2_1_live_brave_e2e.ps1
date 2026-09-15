<#
.SYNOPSIS
Runs the one-shot N3.2.1 development/shadow Brave feedback E2E.

.DESCRIPTION
This is a product-development harness, not an acceptance runner. It generates
short-lived owner and foreign JWTs in process, builds an isolated Flutter web
bundle with all required defines, starts only a temporary static web server,
and delegates browser behavior to n3_2_1_live_brave_e2e.cjs. The JSON evidence
never contains either token. It never touches Plan evidence, research data, or
canonical recipe data.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$mobileRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $mobileRoot '..\..')).Path
$backendRoot = Join-Path $projectRoot 'apps\backend'
$python = Join-Path $projectRoot '.venv-e4-py310\Scripts\python.exe'
$flutter = Join-Path $mobileRoot '.fvm\flutter_sdk\bin\flutter.bat'
$browserScript = Join-Path $PSScriptRoot 'n3_2_1_live_brave_e2e.cjs'
$playwrightNodePath = Join-Path $env:APPDATA 'npm\node_modules\@playwright\cli\node_modules'
$apiBaseUrl = 'http://127.0.0.1:8093'
$webBaseUrl = 'http://127.0.0.1:4174'
$webPort = 4174
$evidencePath = Join-Path $backendRoot 'validation\n3_2_1\n3-2-1-live-brave-e2e-v1.json'
$braveCandidates = @(
    'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
    'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
    (Join-Path $env:LOCALAPPDATA 'BraveSoftware\Brave-Browser\Application\brave.exe')
)
$environmentNames = @(
    'NODE_PATH',
    'N3_2_1_E2E_WEB',
    'N3_2_1_E2E_API',
    'N3_2_1_E2E_TOKEN',
    'N3_2_1_E2E_FOREIGN_TOKEN',
    'N3_2_1_BRAVE_EXECUTABLE',
    'N3_2_1_BRAVE_PRODUCT_VERSION',
    'N3_2_1_E2E_EVIDENCE',
    'N3_2_1_POSTGRESQL_HEALTHY',
    'N3_2_1_BUILD_API_CONFIGURED',
    'N3_2_1_BUILD_TEST_AUTH_CONFIGURED',
    'N3_2_1_BUILD_E2E_DEMO_ENABLED',
    'N3_2_1_BUILD_MARKER_EMBEDDED'
)

$startedAt = (Get-Date).ToUniversalTime().ToString('o')
$failureStage = 'preflight'
$failureClass = $null
$failureMessage = $null
$webProcess = $null
$ownerToken = $null
$foreignToken = $null
$browserResult = $null
$environmentBackup = @{}
foreach ($name in $environmentNames) {
    $environmentBackup[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Require-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Test-ListeningPort {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1)
}

function Wait-ForHttpOk {
    param([string]$Url, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            # A health endpoint is polled rather than relying on a fixed sleep.
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "SERVICE_BOOTSTRAP:HTTP_HEALTH_TIMEOUT:$Url"
}

function Get-FailureClass {
    param([string]$Stage, [string]$Message)
    if ($Message -match '^DATABASE_(PERSISTENCE|TRANSACTION)|POSTGRESQL') { return 'DATABASE_PERSISTENCE' }
    if ($Message -match '^BUILD_CONFIGURATION') { return 'BUILD_CONFIGURATION' }
    if ($Message -match '^AUTHENTICATION') { return 'AUTHENTICATION' }
    if ($Message -match '^SERVICE_BOOTSTRAP') { return 'SERVICE_BOOTSTRAP' }
    if ($Message -match '^BROWSER_BOOTSTRAP|PREFLIGHT_BRAVE') { return 'BROWSER_BOOTSTRAP' }
    if ($Message -match '^PLAYWRIGHT_HARNESS') { return 'PLAYWRIGHT_HARNESS' }
    if ($Stage -match 'playwright|locator') { return 'PLAYWRIGHT_HARNESS' }
    return 'BROWSER_BOOTSTRAP'
}

function Write-HarnessFailureEvidence {
    $artifact = [ordered]@{
        artifact_version = 'N3_2_1_LIVE_BRAVE_E2E_V1'
        status = 'FAIL'
        browser_name = 'Brave'
        browser_executable_path = $script:brave
        browser_version = $script:braveVersion
        service_health = [ordered]@{ backend_api = $false; postgresql = $false; static_web = $false }
        build_configuration = [ordered]@{
            api_base_url_configured = $false
            test_auth_configured = $false
            e2e_demo_enabled = $false
            bundle_marker_embedded = $false
        }
        failure_stage = $script:failureStage
        failure_class = $script:failureClass
        error = $script:failureMessage
        timestamps = [ordered]@{ started_at_utc = $script:startedAt; completed_at_utc = (Get-Date).ToUniversalTime().ToString('o') }
        token_recorded = $false
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidencePath) | Out-Null
    $artifact | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidencePath -Encoding utf8
}

try {
    $failureStage = 'preflight-dependencies'
    Require-Condition (Test-Path -LiteralPath $python) "PREFLIGHT_PYTHON_MISSING:$python"
    Require-Condition (Test-Path -LiteralPath $flutter) "PREFLIGHT_FLUTTER_MISSING:$flutter"
    Require-Condition (Test-Path -LiteralPath $browserScript) "PREFLIGHT_PLAYWRIGHT_SCRIPT_MISSING:$browserScript"
    Require-Condition (Test-Path -LiteralPath $playwrightNodePath) "PREFLIGHT_PLAYWRIGHT_RUNTIME_MISSING:$playwrightNodePath"
    $brave = $braveCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Require-Condition (-not [string]::IsNullOrWhiteSpace($brave)) 'PREFLIGHT_BRAVE_MISSING'
    $braveVersion = (Get-Item -LiteralPath $brave).VersionInfo.ProductVersion
    $pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
    Require-Condition ($pythonVersion -match '^Python 3\.10\.21') "PREFLIGHT_PYTHON_VERSION:$pythonVersion"
    $flutterVersion = (& $flutter --version 2>&1 | Out-String).Trim()
    Require-Condition ($flutterVersion -match 'Flutter 3\.44\.8') 'PREFLIGHT_FLUTTER_VERSION_MISMATCH'
    Require-Condition ($flutterVersion -match 'Dart 3\.12\.2') 'PREFLIGHT_DART_VERSION_MISMATCH'
    $savedNodePath = $env:NODE_PATH
    try {
        $env:NODE_PATH = $playwrightNodePath
        $playwrightResolution = (& node -e "process.stdout.write(require.resolve('playwright'))" 2>&1 | Out-String).Trim()
    } finally {
        $env:NODE_PATH = $savedNodePath
    }
    Require-Condition (-not [string]::IsNullOrWhiteSpace($playwrightResolution)) 'PREFLIGHT_PLAYWRIGHT_RESOLUTION_FAILED'

    $failureStage = 'preflight-services'
    Require-Condition (-not (Test-ListeningPort $webPort)) "SERVICE_BOOTSTRAP:WEB_PORT_IN_USE:$webPort"
    $postgresHealthy = Test-NetConnection -ComputerName '127.0.0.1' -Port 5432 -InformationLevel Quiet
    Require-Condition $postgresHealthy 'DATABASE_PERSISTENCE:POSTGRESQL_UNAVAILABLE'
    Wait-ForHttpOk -Url "$apiBaseUrl/docs" -TimeoutSeconds 5

    $failureStage = 'token-generation'
    Push-Location $backendRoot
    try {
        $ownerToken = ((& $python -c "from datetime import datetime, timedelta, timezone; import jwt; from config import settings; print(jwt.encode({'sub':'n3_2_1_brave_owner','exp':datetime.now(timezone.utc)+timedelta(minutes=25)},settings.jwt_secret,algorithm='HS256'))") | Select-Object -Last 1).Trim()
        $foreignToken = ((& $python -c "from datetime import datetime, timedelta, timezone; import jwt; from config import settings; print(jwt.encode({'sub':'n3_2_1_brave_foreign','exp':datetime.now(timezone.utc)+timedelta(minutes=25)},settings.jwt_secret,algorithm='HS256'))") | Select-Object -Last 1).Trim()
    } finally {
        Pop-Location
    }
    Require-Condition ($ownerToken -match '^[^.]+\.[^.]+\.[^.]+$') 'AUTHENTICATION:OWNER_TOKEN_GENERATION_FAILED'
    Require-Condition ($foreignToken -match '^[^.]+\.[^.]+\.[^.]+$') 'AUTHENTICATION:FOREIGN_TOKEN_GENERATION_FAILED'

    $failureStage = 'build-web'
    $buildArgs = @(
        'build', 'web', '--release', '--no-tree-shake-icons',
        "--dart-define=API_BASE_URL=$apiBaseUrl",
        "--dart-define=N3_2_1_TEST_TOKEN=$ownerToken",
        '--dart-define=N3_2_1_E2E_CONFIGURATION_MARKER=N3_2_1_E2E_CONFIGURED_V1',
        '--dart-define=PLAN_V2_E2E_DEMO=true',
        '--dart-define=PLAN_V2_E2E_CONFIGURATION_MARKER=PLAN_V2_E2E_CONFIGURED_V1'
    )
    Push-Location $mobileRoot
    try {
        & $flutter @buildArgs
        Require-Condition ($LASTEXITCODE -eq 0) "BUILD_CONFIGURATION:FLUTTER_WEB_FAILED:$LASTEXITCODE"
    } finally {
        Pop-Location
    }

    $failureStage = 'build-configuration-assertion'
    $bundle = Join-Path $mobileRoot 'build\web\main.dart.js'
    Require-Condition (Test-Path -LiteralPath $bundle) "BUILD_CONFIGURATION:BUNDLE_MISSING:$bundle"
    $apiConfigured = Select-String -LiteralPath $bundle -SimpleMatch $apiBaseUrl -Quiet
    # Dart correctly constant-folds raw marker values away in optimized Web
    # output. Assert the referenced, non-secret semantic contracts instead;
    # the live authenticated feedback call below proves the token itself.
    $testAuthConfigured = Select-String -LiteralPath $bundle -SimpleMatch 'n3-e2e-runtime-configured' -Quiet
    $demoConfigured = Select-String -LiteralPath $bundle -SimpleMatch 'Plan V2 E2E configuration active' -Quiet
    Require-Condition ($apiConfigured -and $testAuthConfigured -and $demoConfigured) 'BUILD_CONFIGURATION:DART_DEFINES_NOT_EMBEDDED'

    $failureStage = 'static-web'
    $webLog = Join-Path $env:TEMP 'n3-2-1-live-brave-web.log'
    $webErrorLog = Join-Path $env:TEMP 'n3-2-1-live-brave-web.err'
    $webProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'http.server', "$webPort", '--bind', '127.0.0.1') -WorkingDirectory (Join-Path $mobileRoot 'build\web') -WindowStyle Hidden -RedirectStandardOutput $webLog -RedirectStandardError $webErrorLog -PassThru
    Wait-ForHttpOk -Url "$webBaseUrl/" -TimeoutSeconds 30

    $failureStage = 'playwright-brave'
    $env:NODE_PATH = $playwrightNodePath
    $env:N3_2_1_E2E_WEB = $webBaseUrl
    $env:N3_2_1_E2E_API = $apiBaseUrl
    $env:N3_2_1_E2E_TOKEN = $ownerToken
    $env:N3_2_1_E2E_FOREIGN_TOKEN = $foreignToken
    $env:N3_2_1_BRAVE_EXECUTABLE = $brave
    $env:N3_2_1_BRAVE_PRODUCT_VERSION = $braveVersion
    $env:N3_2_1_E2E_EVIDENCE = $evidencePath
    $env:N3_2_1_POSTGRESQL_HEALTHY = $postgresHealthy.ToString().ToLowerInvariant()
    $env:N3_2_1_BUILD_API_CONFIGURED = $apiConfigured.ToString().ToLowerInvariant()
    $env:N3_2_1_BUILD_TEST_AUTH_CONFIGURED = $testAuthConfigured.ToString().ToLowerInvariant()
    $env:N3_2_1_BUILD_E2E_DEMO_ENABLED = $demoConfigured.ToString().ToLowerInvariant()
    $env:N3_2_1_BUILD_MARKER_EMBEDDED = $demoConfigured.ToString().ToLowerInvariant()
    & node $browserScript
    $browserExitCode = $LASTEXITCODE
    Require-Condition (Test-Path -LiteralPath $evidencePath) 'PLAYWRIGHT_HARNESS:EVIDENCE_MISSING'
    $browserResult = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
    if ($browserExitCode -ne 0 -or $browserResult.status -ne 'PASS') {
        $failureStage = if ($browserResult.failure_stage) { $browserResult.failure_stage } else { 'playwright-brave' }
        $failureClass = if ($browserResult.failure_class) { $browserResult.failure_class } else { 'PLAYWRIGHT_HARNESS' }
        $failureMessage = $browserResult.error
        throw "PLAYWRIGHT_HARNESS:LIVE_RUN_FAILED:$failureClass"
    }
} catch {
    if ([string]::IsNullOrWhiteSpace($failureMessage)) { $failureMessage = $_.Exception.Message }
    if ([string]::IsNullOrWhiteSpace($failureClass)) { $failureClass = Get-FailureClass -Stage $failureStage -Message $failureMessage }
    if (-not (Test-Path -LiteralPath $evidencePath) -or $failureStage -notmatch 'playwright') {
        Write-HarnessFailureEvidence
    }
    Write-Error "$failureClass at ${failureStage}: $failureMessage"
    exit 1
} finally {
    if ($null -ne $webProcess -and -not $webProcess.HasExited) { Stop-Process -Id $webProcess.Id -Force }
    foreach ($name in $environmentNames) {
        if ($null -eq $environmentBackup[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $environmentBackup[$name], 'Process')
        }
    }
    $ownerToken = $null
    $foreignToken = $null
}
