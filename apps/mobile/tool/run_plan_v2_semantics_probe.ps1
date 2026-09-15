[CmdletBinding()]
param(
  [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$mobileRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot = (Resolve-Path (Join-Path $mobileRoot '..\..')).Path
$pythonExe = Join-Path $projectRoot '.venv-e4-py310\Scripts\python.exe'
$bundleDirectory = Join-Path $mobileRoot 'build\web'
$probeScript = Join-Path $PSScriptRoot 'plan_v2_semantics_probe.cjs'
if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
  $EvidencePath = Join-Path $projectRoot 'docs\reports\plan_v2_playwright_semantics_probe-v1.json'
}
$edgeExecutable = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$playwrightNodePath = Join-Path $env:APPDATA 'npm\node_modules\@playwright\cli\node_modules'
$webPort = 4173
$staticServer = $null
$originalNodePath = $env:NODE_PATH
$scriptExitCode = 1

function Wait-HttpOk([string]$Uri) {
  $deadline = (Get-Date).AddSeconds(15)
  do {
    try {
      if ((Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2).StatusCode -eq 200) {
        return
      }
    } catch {
      # The server is still starting.
    }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $deadline)
  throw "Static Flutter bundle did not become healthy at $Uri."
}

if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Project Python is missing: $pythonExe" }
if (-not (Test-Path -LiteralPath (Join-Path $bundleDirectory 'index.html'))) { throw "Existing Flutter web bundle is missing: $bundleDirectory" }
if (-not (Test-Path -LiteralPath $probeScript)) { throw "Semantics probe is missing: $probeScript" }
if (-not (Test-Path -LiteralPath $edgeExecutable)) { throw "Microsoft Edge is missing: $edgeExecutable" }
if (-not (Test-Path -LiteralPath $playwrightNodePath)) { throw "Playwright runtime is missing: $playwrightNodePath" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is required for the Playwright semantics probe.' }

try {
  $staticServer = Start-Process -FilePath $pythonExe -ArgumentList @(
    '-m', 'http.server', $webPort, '--bind', '127.0.0.1', '--directory', $bundleDirectory
  ) -WorkingDirectory $mobileRoot -WindowStyle Hidden -PassThru
  Wait-HttpOk -Uri "http://127.0.0.1:$webPort/"

  $env:PLAN_V2_SEMANTICS_WEB = "http://127.0.0.1:$webPort"
  $env:PLAN_V2_SEMANTICS_EVIDENCE = $EvidencePath
  $env:EDGE_EXECUTABLE = $edgeExecutable
  $env:NODE_PATH = $playwrightNodePath
  & node $probeScript
  $scriptExitCode = $LASTEXITCODE
} finally {
  Remove-Item Env:PLAN_V2_SEMANTICS_WEB -ErrorAction SilentlyContinue
  Remove-Item Env:PLAN_V2_SEMANTICS_EVIDENCE -ErrorAction SilentlyContinue
  Remove-Item Env:EDGE_EXECUTABLE -ErrorAction SilentlyContinue
  $env:NODE_PATH = $originalNodePath
  if ($staticServer -and -not $staticServer.HasExited) {
    Stop-Process -Id $staticServer.Id -Force
  }
}

exit $scriptExitCode
