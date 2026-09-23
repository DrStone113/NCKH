param(
    [Parameter(Mandatory = $true)][string]$WorkingDocx
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$docx = Get-ChildItem -LiteralPath $root -Filter '*THS2025-78_FINAL.docx' | Select-Object -First 1 -ExpandProperty FullName
if (-not $docx) { throw 'Existing final report not found' }
if (-not (Test-Path -LiteralPath $WorkingDocx)) { throw 'Working document not found' }
$pdf = [IO.Path]::ChangeExtension($docx, '.pdf')
$temporaryPdf = Join-Path $env:TEMP 'ths2025-78-rendered.pdf'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open((Resolve-Path -LiteralPath $WorkingDocx).Path, $false, $false)
    foreach ($toc in $document.TablesOfContents) { $toc.UpdatePageNumbers() }
    foreach ($list in $document.TablesOfFigures) { $list.UpdatePageNumbers() }
    $document.Repaginate()
    $pages = $document.ComputeStatistics(2)
    $mainStart = $null
    $referencesStart = $null
    # PowerShell 5.1 decodes script literals through the active ANSI code page.
    $openingHeading = -join @([char]77, [char]7902, [char]32, [char]272, [char]7846, [char]85)
    $referencesHeading = -join @([char]84, [char]192, [char]73, [char]32, [char]76, [char]73, [char]7878, [char]85, [char]32, [char]84, [char]72, [char]65, [char]77, [char]32, [char]75, [char]72, [char]7842, [char]79)
    foreach ($paragraph in $document.Paragraphs) {
        $heading = $paragraph.Range.Text.Trim().Trim([char]13, [char]7, [char]32)
        if ($heading -eq $openingHeading) { $mainStart = $paragraph.Range.Information(3) }
        if ($heading -eq $referencesHeading) { $referencesStart = $paragraph.Range.Information(3); break }
    }
    if ($null -eq $mainStart -or $null -eq $referencesStart) {
        throw 'Cannot identify main-content pagination boundaries'
    }
    $mainPages = $referencesStart - $mainStart
    if ($mainPages -lt 50) {
        throw "Main scientific content has $mainPages pages; required minimum is 50"
    }
    $document.ExportAsFixedFormat($temporaryPdf, 17)
    if (-not (Test-Path -LiteralPath $temporaryPdf)) { throw 'PDF export failed' }
    $document.Close($false)
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    $document = $null
    Copy-Item -LiteralPath $WorkingDocx -Destination $docx -Force
    Copy-Item -LiteralPath $temporaryPdf -Destination $pdf -Force
    "docx=$docx"
    "pdf=$pdf"
    "pages=$pages"
    "main_pages=$mainPages"
}
finally {
    if ($null -ne $document) {
        $document.Close($false)
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
    if ($null -ne $word) {
        $word.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
