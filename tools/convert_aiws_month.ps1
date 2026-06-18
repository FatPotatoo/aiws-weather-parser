param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$DestRoot,
    [Parameter(Mandatory=$true)][string]$MonthName
)

$ErrorActionPreference = 'Stop'
$soffice = 'C:\Program Files\LibreOffice\program\soffice.com'

function Quote-Arg([string]$s) {
    '"' + ($s -replace '"','\"') + '"'
}

function Convert-WithLibreOffice([string]$docPath, [string]$profile, [int]$timeoutMs) {
    $outDir = Split-Path -Parent $docPath
    $expected = [IO.Path]::ChangeExtension($docPath, '.docx')
    New-Item -ItemType Directory -Path $profile -Force | Out-Null

    $args = @(
        '--headless',
        '--invisible',
        '--nodefault',
        '--nofirststartwizard',
        '--norestore',
        "-env:UserInstallation=file:///$($profile.Replace('\','/'))",
        '--convert-to',
        'docx',
        '--outdir',
        (Quote-Arg $outDir),
        (Quote-Arg $docPath)
    )

    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $soffice
    $psi.Arguments = ($args -join ' ')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $p = [Diagnostics.Process]::Start($psi)
    if (-not $p.WaitForExit($timeoutMs)) {
        $profileSlash = $profile.Replace('\','/')
        $targets = @(Get-CimInstance Win32_Process -Filter "name='soffice.exe' or name='soffice.bin' or name='soffice.com'" |
            Where-Object { $_.CommandLine -like "*$profileSlash*" -or $_.CommandLine -like "*$profile*" })
        foreach ($target in $targets) {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        }
        return @{ Ok = (Test-Path -LiteralPath $expected); Message = 'timeout' }
    }

    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    return @{ Ok = (Test-Path -LiteralPath $expected); Message = "exit=$($p.ExitCode) $stdout $stderr" }
}

function Convert-WithWord([string[]]$files) {
    $results = @{}
    if ($files.Count -eq 0) { return $results }

    $before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $word = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        foreach ($file in $files) {
            $out = [IO.Path]::ChangeExtension($file, '.docx')
            $doc = $null
            try {
                $doc = $word.Documents.Open($file, $false, $true, $false)
                $doc.SaveAs2($out, 16)
                $doc.Close($false)
                $results[$file] = (Test-Path -LiteralPath $out)
            } catch {
                if ($doc -ne $null) {
                    try { $doc.Close($false) } catch {}
                }
                $results[$file] = $false
            }
        }
    } finally {
        if ($word -ne $null) {
            try { $word.Quit() } catch {}
        }
        $after = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
        foreach ($pidValue in @($after | Where-Object { $before -notcontains $_ })) {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        }
    }
    return $results
}

$srcMonth = Join-Path $SourceRoot $MonthName
$dstMonth = Join-Path $DestRoot $MonthName
if (-not (Test-Path -LiteralPath $srcMonth)) {
    throw "Month source not found: $srcMonth"
}

New-Item -ItemType Directory -Path $dstMonth -Force | Out-Null
Get-ChildItem -LiteralPath $srcMonth -Recurse -Directory | ForEach-Object {
    $rel = $_.FullName.Substring($SourceRoot.Length).TrimStart('\')
    New-Item -ItemType Directory -Path (Join-Path $DestRoot $rel) -Force | Out-Null
}

$sourceDocs = @(Get-ChildItem -LiteralPath $srcMonth -Recurse -File |
    Where-Object { $_.Extension -ieq '.doc' -and $_.Name -notlike '~$*' } |
    Sort-Object FullName)

foreach ($source in $sourceDocs) {
    $rel = $source.FullName.Substring($SourceRoot.Length).TrimStart('\')
    $dest = Join-Path $DestRoot $rel
    New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
    if (-not (Test-Path -LiteralPath $dest)) {
        Copy-Item -LiteralPath $source.FullName -Destination $dest
    }
}

$destDocs = @(Get-ChildItem -LiteralPath $dstMonth -Recurse -File |
    Where-Object { $_.Extension -ieq '.doc' -and $_.Name -notlike '~$*' } |
    Sort-Object FullName)

$newDocx = 0
$existingDocx = 0
$fallback = @()
$failures = @()

foreach ($doc in $destDocs) {
    $expected = [IO.Path]::ChangeExtension($doc.FullName, '.docx')
    if (Test-Path -LiteralPath $expected) {
        $existingDocx++
        continue
    }

    $safeMonth = $MonthName -replace '[^0-9A-Za-z]', ''
    $safeFile = [IO.Path]::GetFileNameWithoutExtension($doc.Name) -replace '[^0-9A-Za-z]', ''
    $profile = Join-Path $env:TEMP "lo-aiws-2020-$safeMonth-$safeFile"
    $result = Convert-WithLibreOffice $doc.FullName $profile 90000
    if ($result.Ok) {
        $newDocx++
    } else {
        $fallback += $doc.FullName
        $failures += "$($doc.FullName) :: $($result.Message)"
    }
}

$wordResults = Convert-WithWord $fallback
foreach ($file in $fallback) {
    if (Test-Path -LiteralPath ([IO.Path]::ChangeExtension($file, '.docx'))) {
        $newDocx++
    }
}

$missing = @($destDocs | Where-Object {
    -not (Test-Path -LiteralPath ([IO.Path]::ChangeExtension($_.FullName, '.docx')))
})
if ($missing.Count -gt 0) {
    $log = Join-Path $dstMonth 'conversion_failures.txt'
    @('LIBREOFFICE_FAILURES:', $failures, '', 'MISSING:', ($missing | ForEach-Object FullName)) |
        Set-Content -LiteralPath $log -Encoding UTF8
    throw "Conversion incomplete for $MonthName missing=$($missing.Count) log=$log"
}

$allDoc = @(Get-ChildItem -LiteralPath $dstMonth -Recurse -File |
    Where-Object { $_.Extension -ieq '.doc' })
foreach ($doc in $allDoc) {
    Remove-Item -LiteralPath $doc.FullName -Force
}

$remainingDoc = @(Get-ChildItem -LiteralPath $dstMonth -Recurse -File |
    Where-Object { $_.Extension -ieq '.doc' }).Count
$docxCount = @(Get-ChildItem -LiteralPath $dstMonth -Recurse -File |
    Where-Object { $_.Extension -ieq '.docx' }).Count

"MONTH=$MonthName SOURCE_DOC=$($sourceDocs.Count) NEW_DOCX=$newDocx EXISTING_DOCX=$existingDocx FALLBACK_WORD=$($fallback.Count) DELETED_DOC=$($allDoc.Count) REMAINING_DOC=$remainingDoc DOCX=$docxCount"
