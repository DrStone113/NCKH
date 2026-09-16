<#
Removes only regenerable local development artifacts.

Flutter build caches, dependency directories, environment files, Docker data,
and validation evidence are intentionally preserved.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Start", "Stop")]
    [string]$Phase = "Stop"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectPrefix = $projectRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

$generatedDirectoryNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
@(
    ".playwright",
    ".playwright-cli",
    ".kiro",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__"
) | ForEach-Object { [void]$generatedDirectoryNames.Add($_) }

$generatedFileNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
@(
    ".flutter-plugins",
    ".flutter-plugins-dependencies",
    ".packages",
    "firebase-debug.log",
    "firestore-debug.log",
    "ui-debug.log"
) | ForEach-Object { [void]$generatedFileNames.Add($_) }

function Test-SkippedDirectoryName {
    param([Parameter(Mandatory = $true)][string]$Name)

    return (
        $Name -eq ".git" -or
        $Name -eq ".fvm" -or
        $Name -eq ".dart_tool" -or
        $Name -eq "node_modules" -or
        $Name -eq "build" -or
        $Name -eq "venv" -or
        $Name -like ".venv*"
    )
}

function Assert-SafeProjectPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path)
    if (
        $fullPath -eq $projectRoot -or
        -not $fullPath.StartsWith($projectPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing cleanup target outside the project: $fullPath"
    }

    return $fullPath
}

$directoriesToRemove = [Collections.Generic.List[string]]::new()
$filesToRemove = [Collections.Generic.List[string]]::new()
$pendingDirectories = [Collections.Generic.Stack[IO.DirectoryInfo]]::new()
$pendingDirectories.Push((Get-Item -LiteralPath $projectRoot))

while ($pendingDirectories.Count -gt 0) {
    $current = $pendingDirectories.Pop()
    $children = @(Get-ChildItem -LiteralPath $current.FullName -Force -ErrorAction SilentlyContinue)

    foreach ($child in $children) {
        if ($child.PSIsContainer) {
            if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                continue
            }
            if ($generatedDirectoryNames.Contains($child.Name)) {
                $directoriesToRemove.Add((Assert-SafeProjectPath -Path $child.FullName))
                continue
            }
            if (Test-SkippedDirectoryName -Name $child.Name) {
                continue
            }
            $pendingDirectories.Push($child)
            continue
        }

        if ($generatedFileNames.Contains($child.Name)) {
            $filesToRemove.Add((Assert-SafeProjectPath -Path $child.FullName))
        }
    }
}

$removedDirectories = 0
$removedFiles = 0
$failures = 0

foreach ($path in @($directoriesToRemove | Sort-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }
    if (-not $PSCmdlet.ShouldProcess($path, "Remove generated directory")) {
        continue
    }
    try {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
        $removedDirectories++
    }
    catch {
        $failures++
        Write-Warning "Could not remove generated directory '$path': $($_.Exception.Message)"
    }
}

foreach ($path in @($filesToRemove | Sort-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $path)) {
        continue
    }
    if (-not $PSCmdlet.ShouldProcess($path, "Remove generated file")) {
        continue
    }
    try {
        Remove-Item -LiteralPath $path -Force -ErrorAction Stop
        $removedFiles++
    }
    catch {
        $failures++
        Write-Warning "Could not remove generated file '$path': $($_.Exception.Message)"
    }
}

Write-Output (
    "[cleanup:{0}] removed_directories={1}; removed_files={2}; failures={3}" -f
    $Phase,
    $removedDirectories,
    $removedFiles,
    $failures
)

if ($failures -gt 0) {
    exit 1
}
