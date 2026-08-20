[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path.TrimEnd('\', '/')
$files = New-Object 'System.Collections.Generic.List[System.IO.FileInfo]'

foreach ($relativeDirectory in @('lib', 'web', 'assets')) {
    $directory = Join-Path $projectRoot $relativeDirectory
    if (Test-Path -LiteralPath $directory -PathType Container) {
        Get-ChildItem -LiteralPath $directory -Recurse -File | ForEach-Object {
            $files.Add($_)
        }
    }
}

foreach ($relativeFile in @('pubspec.yaml', 'pubspec.lock')) {
    $file = Join-Path $projectRoot $relativeFile
    if (Test-Path -LiteralPath $file -PathType Leaf) {
        $files.Add((Get-Item -LiteralPath $file))
    }
}

# Changes to the fingerprint rules must invalidate the previous build too.
$files.Add((Get-Item -LiteralPath $PSCommandPath))

$manifest = New-Object System.Text.StringBuilder
[void]$manifest.AppendLine('flutter-build-web|release|no-tree-shake-icons|v1')

foreach ($file in ($files | Sort-Object -Property FullName -Unique)) {
    $relativePath = $file.FullName.Substring($projectRoot.Length) -replace '^[\\/]+', ''
    $relativePath = $relativePath.Replace('\', '/')
    $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    [void]$manifest.AppendLine("$relativePath|$fileHash")
}

$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $payload = [System.Text.Encoding]::UTF8.GetBytes($manifest.ToString())
    $fingerprint = [System.BitConverter]::ToString($sha256.ComputeHash($payload))
    $fingerprint.Replace('-', '').ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}
