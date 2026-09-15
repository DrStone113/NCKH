<#!
.SYNOPSIS
Runs the isolated authenticated Plan V2 Edge E2E flow with no caller-supplied
token, Dart define, server, or cleanup steps.

.DESCRIPTION
This is a development/product-QA harness, not an acceptance runner. It never
rewrites P2.1/V3 evidence and only owns the API and static-web processes it
starts itself. The final JSON deliberately records configuration booleans, not
the short-lived test bearer token.
#>

[CmdletBinding()]
param(
    [switch]$SemanticsProbeOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$mobileRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $mobileRoot '..\..')).Path
$backendRoot = Join-Path $projectRoot 'apps\backend'
$python = Join-Path $projectRoot '.venv-e4-py310\Scripts\python.exe'
$flutter = Join-Path $mobileRoot '.fvm\flutter_sdk\bin\flutter.bat'
$browserScript = Join-Path $mobileRoot 'tool\plan_v2_authenticated_edge_e2e.cjs'
$semanticsProbeScript = Join-Path $mobileRoot 'tool\plan_v2_semantics_probe.cjs'
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$playwrightNodePath = Join-Path $env:APPDATA 'npm\node_modules\@playwright\cli\node_modules'
$apiBaseUrl = 'http://127.0.0.1:8091'
$webBaseUrl = 'http://127.0.0.1:4173'
$apiPort = 8091
$webPort = 4173
$e2eMarker = 'PLAN_V2_E2E_CONFIGURED_V1'
$e2eRuntimeLabel = 'Plan V2 E2E configuration active'
$evidenceDirectory = Join-Path $backendRoot 'validation\plan_tool_v2_p2'
$finalEvidencePath = Join-Path $evidenceDirectory 'plan-v2-live-e2e-final.json'
$semanticsProbeEvidencePath = Join-Path $projectRoot 'docs\reports\plan_v2_playwright_semantics_probe-v1.json'
$runId = [Guid]::NewGuid().ToString('N')
$temporaryBrowserEvidence = Join-Path $env:TEMP "plan-v2-live-e2e-browser-$runId.json"
$apiLog = Join-Path $env:TEMP "plan-v2-live-e2e-api-$runId.log"
$apiErrorLog = Join-Path $env:TEMP "plan-v2-live-e2e-api-$runId.err"
$webLog = Join-Path $env:TEMP "plan-v2-live-e2e-web-$runId.log"
$webErrorLog = Join-Path $env:TEMP "plan-v2-live-e2e-web-$runId.err"

$startedAt = (Get-Date).ToUniversalTime().ToString('o')
$failureStage = 'preflight'
$failureClass = $null
$failureMessage = $null
$status = 'FAIL'
$apiProcess = $null
$webProcess = $null
$testToken = $null
$browserResult = $null
$environmentBackup = @{}
foreach ($name in @(
    'PLAN_V2_E2E_TOKEN',
    'PLAN_V2_E2E_API',
    'PLAN_V2_E2E_WEB',
    'PLAN_V2_E2E_EVIDENCE',
    'EDGE_EXECUTABLE',
    'NODE_PATH',
    'PLAN_V2_SEMANTICS_WEB',
    'PLAN_V2_SEMANTICS_EVIDENCE'
)) {
    $environmentBackup[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$toolchain = [ordered]@{}
$buildConfiguration = [ordered]@{
    api_base_url_configured = $false
    test_auth_configured = $false
    e2e_demo_enabled = $false
    runtime_marker_embedded = $false
}
$serviceHealth = [ordered]@{
    postgresql_tcp = $false
    isolated_plan_api = $false
    static_web = $false
}
$events = @()

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
            # A process-health wait is expected while the owned service starts.
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "SERVICE_HEALTH_TIMEOUT: $Url"
}

function Get-BrowserFailureClass {
    param([string]$Message)
    if ($Message -match 'PRODUCT_UI_AUTHORITATIVE_PLAN_NOT_RENDERED') {
        return 'PRODUCT_BEHAVIOR'
    }
    if ($Message -match 'HTTP_401|AUTHENTICATION|AUTHENTICATED_PRINCIPAL') {
        return 'AUTHENTICATION'
    }
    if ($Message -match 'HTTP_503|ECONNREFUSED|PLAN_PERSISTENCE_TRANSACTION_FAILED') {
        return 'SERVICE_BOOTSTRAP'
    }
    return 'PLAYWRIGHT_HARNESS'
}

function Get-StageFailureClass {
    param([string]$Stage)
    if ($Stage -like 'preflight*' -or $Stage -eq 'token-generation') {
        return 'PREFLIGHT_CONFIGURATION'
    }
    if ($Stage -like 'build*') { return 'BUILD_CONFIGURATION' }
    if ($Stage -like 'service*') { return 'SERVICE_BOOTSTRAP' }
    return 'PLAYWRIGHT_HARNESS'
}

function Get-BrowserField {
    param([string]$Name)
    if ($null -eq $browserResult) { return $null }
    $property = $browserResult.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Write-FinalEvidence {
    $payload = [ordered]@{
        artifact_version = 'PLAN_V2_LIVE_E2E_FINAL_V1'
        status = $status
        failure_stage = if ($status -eq 'PASS') { $null } else { $failureStage }
        failure_class = if ($status -eq 'PASS') { 'PASS' } else { $failureClass }
        failure_message = $failureMessage
        timestamps = [ordered]@{
            started_at_utc = $startedAt
            completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        }
        toolchain = $toolchain
        build_configuration = $buildConfiguration
        service_health = $serviceHealth
        plan_id = Get-BrowserField 'plan_id'
        revision_id = Get-BrowserField 'revision_id'
        authenticated_principal = Get-BrowserField 'authenticated_principal'
        events = $events
        semantics_preflight = Get-BrowserField 'semantics_preflight'
        read_back_statuses = Get-BrowserField 'read_back_statuses'
        cross_user_result = Get-BrowserField 'cross_user_result'
        planned_actual_result = Get-BrowserField 'planned_actual_result'
        browser_failure_stage = Get-BrowserField 'failure_stage'
        token_recorded = $false
    }
    [System.IO.File]::WriteAllText(
        $finalEvidencePath,
        (($payload | ConvertTo-Json -Depth 12) + [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
}

try {
    New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

    $failureStage = 'preflight-toolchain'
    Require-Condition (Test-Path -LiteralPath $python) "PREFLIGHT_MISSING_PYTHON: $python"
    Require-Condition (Test-Path -LiteralPath $flutter) "PREFLIGHT_MISSING_FLUTTER: $flutter"
    Require-Condition (Test-Path -LiteralPath $edge) "PREFLIGHT_MISSING_EDGE: $edge"
    Require-Condition (Test-Path -LiteralPath $browserScript) "PREFLIGHT_MISSING_BROWSER_SCRIPT: $browserScript"
    Require-Condition (Test-Path -LiteralPath $semanticsProbeScript) "PREFLIGHT_MISSING_SEMANTICS_PROBE: $semanticsProbeScript"
    Require-Condition (Test-Path -LiteralPath $playwrightNodePath) "PREFLIGHT_MISSING_PLAYWRIGHT_RUNTIME: $playwrightNodePath"

    $pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
    Require-Condition ($pythonVersion -match '^Python 3\.10\.21') "PREFLIGHT_PYTHON_VERSION: $pythonVersion"
    $flutterVersion = (& $flutter --version 2>&1 | Out-String).Trim()
    Require-Condition ($flutterVersion -match 'Flutter 3\.44\.8') 'PREFLIGHT_FLUTTER_VERSION_MISMATCH'
    Require-Condition ($flutterVersion -match 'Dart 3\.12\.2') 'PREFLIGHT_DART_VERSION_MISMATCH'
    $edgeVersion = (& $edge --version 2>&1 | Out-String).Trim()

    $originalNodePath = $env:NODE_PATH
    $env:NODE_PATH = $playwrightNodePath
    try {
        $playwrightResolution = (& node -e "process.stdout.write(require.resolve('playwright'))" 2>&1 | Out-String).Trim()
    } finally {
        $env:NODE_PATH = $originalNodePath
    }
    Require-Condition (-not [string]::IsNullOrWhiteSpace($playwrightResolution)) 'PREFLIGHT_PLAYWRIGHT_RESOLUTION_FAILED'
    $toolchain.python = $pythonVersion
    $toolchain.flutter = ($flutterVersion -split [Environment]::NewLine | Select-Object -First 1)
    $toolchain.dart = (($flutterVersion -split [Environment]::NewLine | Where-Object { $_ -match 'Dart 3\.12\.2' } | Select-Object -First 1).Trim())
    $toolchain.edge_path = $edge
    $toolchain.edge_version = $edgeVersion
    $toolchain.playwright_runtime = $playwrightResolution

    $failureStage = 'preflight-dependencies'
    Require-Condition (-not (Test-ListeningPort $apiPort)) "PREFLIGHT_API_PORT_IN_USE: $apiPort"
    Require-Condition (-not (Test-ListeningPort $webPort)) "PREFLIGHT_WEB_PORT_IN_USE: $webPort"
    $serviceHealth.postgresql_tcp = Test-NetConnection -ComputerName '127.0.0.1' -Port 5432 -InformationLevel Quiet
    Require-Condition $serviceHealth.postgresql_tcp 'PREFLIGHT_POSTGRESQL_UNAVAILABLE: 127.0.0.1:5432'

    $failureStage = 'service-api'
    $apiProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'scripts.run_p2_2_plan_api') -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput $apiLog -RedirectStandardError $apiErrorLog -PassThru
    Wait-ForHttpOk -Url "$apiBaseUrl/docs" -TimeoutSeconds 30
    $serviceHealth.isolated_plan_api = $true

    $failureStage = 'token-generation'
    Push-Location $backendRoot
    try {
        $tokenOutput = & $python -c "from datetime import datetime, timedelta, timezone; import jwt; from config import settings; print(jwt.encode({'sub':'p2_2_browser_test','exp': datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.jwt_secret, algorithm='HS256'))"
        $testToken = ($tokenOutput | Select-Object -Last 1).Trim()
    } finally {
        Pop-Location
    }
    Require-Condition ($testToken -match '^[^.]+\.[^.]+\.[^.]+$') 'PREFLIGHT_TOKEN_GENERATION_FAILED'
    $buildConfiguration.test_auth_configured = $true
    $buildConfiguration.e2e_demo_enabled = $true

    $failureStage = 'build-e2e-web'
    $buildArgs = @(
        'build', 'web', '--release',
        "--dart-define=API_BASE_URL=$apiBaseUrl",
        "--dart-define=PLAN_V2_TEST_TOKEN=$testToken",
        '--dart-define=PLAN_V2_E2E_DEMO=true',
        "--dart-define=PLAN_V2_E2E_CONFIGURATION_MARKER=$e2eMarker"
    )
    Push-Location $mobileRoot
    try {
        & $flutter @buildArgs
        Require-Condition ($LASTEXITCODE -eq 0) 'BUILD_FLUTTER_WEB_FAILED'
    } finally {
        Pop-Location
    }

    $failureStage = 'build-configuration-assertion'
    $bundle = Join-Path $mobileRoot 'build\web\main.dart.js'
    Require-Condition (Test-Path -LiteralPath $bundle) "BUILD_BUNDLE_MISSING: $bundle"
    $buildConfiguration.api_base_url_configured = [bool](Select-String -Path $bundle -SimpleMatch $apiBaseUrl -Quiet)
    $buildConfiguration.runtime_marker_embedded = [bool](Select-String -Path $bundle -SimpleMatch $e2eRuntimeLabel -Quiet)
    Require-Condition $buildConfiguration.api_base_url_configured 'BUILD_API_BASE_URL_NOT_EMBEDDED'
    Require-Condition $buildConfiguration.test_auth_configured 'BUILD_TEST_AUTH_NOT_CONFIGURED'
    Require-Condition $buildConfiguration.e2e_demo_enabled 'BUILD_E2E_DEMO_NOT_ENABLED'
    Require-Condition $buildConfiguration.runtime_marker_embedded 'BUILD_E2E_RUNTIME_MARKER_NOT_EMBEDDED'

    $failureStage = 'service-static-web'
    $webProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'http.server', "$webPort", '--bind', '127.0.0.1') -WorkingDirectory (Join-Path $mobileRoot 'build\web') -WindowStyle Hidden -RedirectStandardOutput $webLog -RedirectStandardError $webErrorLog -PassThru
    Wait-ForHttpOk -Url "$webBaseUrl/" -TimeoutSeconds 30
    $serviceHealth.static_web = $true

    if ($SemanticsProbeOnly) {
        $failureStage = 'playwright-semantics-probe'
        $env:PLAN_V2_SEMANTICS_WEB = $webBaseUrl
        $env:PLAN_V2_SEMANTICS_EVIDENCE = $semanticsProbeEvidencePath
        $env:EDGE_EXECUTABLE = $edge
        $env:NODE_PATH = $playwrightNodePath
        & node $semanticsProbeScript
        $semanticsProbeExitCode = $LASTEXITCODE
        Require-Condition (Test-Path -LiteralPath $semanticsProbeEvidencePath) 'PLAYWRIGHT_SEMANTICS_PROBE_EVIDENCE_MISSING'
        $semanticsProbeResult = Get-Content -Raw -Encoding utf8 $semanticsProbeEvidencePath | ConvertFrom-Json
        $probeLocatorCount = [int]$semanticsProbeResult.plan_library_locator.count
        if ($semanticsProbeResult.status -ne 'PASS' -or $semanticsProbeExitCode -ne 0 -or
            -not [bool]$semanticsProbeResult.semantics_enabled -or $probeLocatorCount -ne 1) {
            $failureMessage = "PLAYWRIGHT_HARNESS_PREFLIGHT: SEMANTICS_ENABLED=$($semanticsProbeResult.semantics_enabled) PLAN_LIBRARY_LOCATOR_COUNT=$probeLocatorCount"
            $failureClass = 'PLAYWRIGHT_HARNESS'
            throw 'PLAYWRIGHT_SEMANTICS_PROBE_FAILED'
        }
        $events = @('semantics-probe-pass', 'semantics-enabled', 'plan-library-locator-count-1')
        $status = 'PASS'
        $failureClass = 'PASS'
    } else {
        $failureStage = 'playwright-edge'
        $env:PLAN_V2_E2E_TOKEN = $testToken
        $env:PLAN_V2_E2E_API = $apiBaseUrl
        $env:PLAN_V2_E2E_WEB = $webBaseUrl
        $env:PLAN_V2_E2E_EVIDENCE = $temporaryBrowserEvidence
        $env:EDGE_EXECUTABLE = $edge
        $env:NODE_PATH = $playwrightNodePath
        & node $browserScript
        $browserExitCode = $LASTEXITCODE
        Require-Condition (Test-Path -LiteralPath $temporaryBrowserEvidence) 'PLAYWRIGHT_EVIDENCE_MISSING'
        $browserResult = Get-Content -Raw -Encoding utf8 $temporaryBrowserEvidence | ConvertFrom-Json
        if ($browserResult.status -ne 'PASS' -or $browserExitCode -ne 0) {
            $failureStage = if ($browserResult.failure_stage) { $browserResult.failure_stage } else { 'playwright-edge' }
            $failureMessage = $browserResult.error
            $failureClass = Get-BrowserFailureClass $failureMessage
            throw 'PLAYWRIGHT_RUN_FAILED'
        }
        $events = @(Get-BrowserField 'events')
        $status = 'PASS'
        $failureClass = 'PASS'
        $events += 'runner-cleanup-pending'
    }
} catch {
    if ([string]::IsNullOrWhiteSpace($failureMessage)) {
        $failureMessage = $_.Exception.Message
    }
    if ([string]::IsNullOrWhiteSpace($failureClass)) {
        $failureClass = Get-StageFailureClass $failureStage
    }
} finally {
    foreach ($name in $environmentBackup.Keys) {
        [Environment]::SetEnvironmentVariable($name, $environmentBackup[$name], 'Process')
    }
    $testToken = $null
    foreach ($process in @($webProcess, $apiProcess)) {
        if ($null -ne $process -and (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        }
    }
    foreach ($path in @(
        $temporaryBrowserEvidence,
        ($temporaryBrowserEvidence -replace '\.json$', '.png'),
        $apiLog,
        $apiErrorLog,
        $webLog,
        $webErrorLog
    )) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    if (-not $SemanticsProbeOnly) {
        Write-FinalEvidence
    }
}

if ($status -eq 'PASS') {
    if ($SemanticsProbeOnly) {
        Write-Output "PLAN_V2_SEMANTICS_PROBE=PASS evidence=$semanticsProbeEvidencePath"
    } else {
        Write-Output "PLAN_V2_LIVE_E2E=PASS evidence=$finalEvidencePath"
    }
    exit 0
}

if ($SemanticsProbeOnly) {
    Write-Error "PLAN_V2_SEMANTICS_PROBE=FAIL class=$failureClass stage=$failureStage evidence=$semanticsProbeEvidencePath message=$failureMessage"
} else {
    Write-Error "PLAN_V2_LIVE_E2E=FAIL class=$failureClass stage=$failureStage evidence=$finalEvidencePath message=$failureMessage"
}
exit 1
