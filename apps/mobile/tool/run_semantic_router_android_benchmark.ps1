param(
    [Parameter(Mandatory = $true)]
    [string]$ModelPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ModelSha256,
    [ValidateSet('Q4_K_M', 'Q8_0')]
    [string]$ModelQuantization = 'Q8_0',
    [string]$PackageId = 'com.example.app',
    [string]$AdbPath = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
    [string]$DeviceId = 'emulator-5554',
    [switch]$Arm64Only
)

$ErrorActionPreference = 'Stop'
$mobileRoot = Split-Path -Parent $PSScriptRoot
$flutter = Join-Path $mobileRoot '.fvm\flutter_sdk\bin\flutter.bat'
$model = (Resolve-Path -LiteralPath $ModelPath).Path
if (-not (Test-Path -LiteralPath $flutter)) { throw 'Pinned Flutter SDK not found.' }
if (-not (Test-Path -LiteralPath $AdbPath)) { throw 'ADB not found.' }
$actualHash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $ModelSha256.ToLowerInvariant()) { throw 'Model checksum mismatch.' }

$sdk = $env:ANDROID_SDK_ROOT
if (-not $sdk) { $sdk = $env:ANDROID_HOME }
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable('ANDROID_SDK_ROOT', 'User') }
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable('ANDROID_HOME', 'User') }
if (-not $sdk -or -not (Test-Path -LiteralPath $sdk)) {
    throw 'Android SDK is required. Configure ANDROID_SDK_ROOT before running.'
}
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_HOME = $sdk
if (-not $env:JAVA_HOME) {
    $env:JAVA_HOME = [Environment]::GetEnvironmentVariable('JAVA_HOME', 'User')
}

$modelFileName = "qwen3-0.6b-$($ModelQuantization.ToLowerInvariant()).gguf"
$deviceModelPath = "/data/user/0/$PackageId/files/semantic_router/$modelFileName"
Push-Location $mobileRoot
try {
    $buildArguments = @(
        'build', 'apk', '--debug',
        '--target', 'lib/semantic_router_benchmark_main.dart',
        '--dart-define', 'SEMANTIC_ROUTER_MODE=shadow',
        '--dart-define', "SEMANTIC_ROUTER_MODEL_PATH=$deviceModelPath",
        '--dart-define', "SEMANTIC_ROUTER_MODEL_SHA256=$actualHash",
        '--dart-define', 'SEMANTIC_ROUTER_MODEL_ID=Qwen/Qwen3-0.6B-GGUF',
        '--dart-define', "SEMANTIC_ROUTER_MODEL_QUANTIZATION=$ModelQuantization"
    )
    if ($Arm64Only) {
        $buildArguments += @('--target-platform', 'android-arm64')
    }
    & $flutter @buildArguments
    if ($LASTEXITCODE -ne 0) { throw 'Flutter APK build failed.' }

    $apk = Join-Path $mobileRoot 'build\app\outputs\flutter-apk\app-debug.apk'
    & $AdbPath -s $DeviceId install -r $apk
    if ($LASTEXITCODE -ne 0) { throw 'APK install failed.' }
    $temporaryDevicePath = "/data/local/tmp/$modelFileName"
    & $AdbPath -s $DeviceId push $model $temporaryDevicePath
    & $AdbPath -s $DeviceId shell chmod 644 $temporaryDevicePath
    & $AdbPath -s $DeviceId shell run-as $PackageId mkdir -p files/semantic_router
    & $AdbPath -s $DeviceId shell run-as $PackageId cp $temporaryDevicePath "files/semantic_router/$modelFileName"
    & $AdbPath -s $DeviceId shell rm $temporaryDevicePath
    & $AdbPath -s $DeviceId logcat -c
    & $AdbPath -s $DeviceId shell am force-stop $PackageId
    & $AdbPath -s $DeviceId shell monkey -p $PackageId 1

    $deadline = (Get-Date).AddMinutes(8)
    do {
        $logs = & $AdbPath -s $DeviceId logcat -d -v brief
        $result = $logs | Select-String -Pattern 'SEMANTIC_ROUTER_BENCHMARK=' | Select-Object -Last 1
        if ($result) {
            $result.Line
            exit 0
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Benchmark timed out without a result marker.'
} finally {
    Pop-Location
}
