from __future__ import annotations

import argparse
from pathlib import Path


VERIFIER_PS1 = "VERIFY_DELIVERY_INTEGRITY.ps1"
VERIFIER_README_CN = "VERIFY_DELIVERY_INTEGRITY_README_CN.md"
OPEN_PACKAGE_PS1 = "OPEN_PROJECT1_REVIEW_PACKAGE.ps1"
PACKAGE_SELF_TEST_PS1 = "PROJECT1_PACKAGE_SELF_TEST.ps1"
PACKAGE_SELF_TEST_README_CN = "PROJECT1_PACKAGE_SELF_TEST_README_CN.md"
ISSUE_REPORT_TEMPLATE_CSV = "REVIEW_ISSUE_REPORT_TEMPLATE.csv"
ISSUE_REPORT_GUIDE_CN = "REVIEW_ISSUE_REPORT_GUIDE_CN.md"


RECIPIENT_VERIFIER_PS1 = r'''param(
    [string]$PackageDir = "",
    [string]$ManifestJson = "",
    [string]$OutJson = "DELIVERY_INTEGRITY_RECIPIENT_REPORT.json"
)

$ErrorActionPreference = "Stop"

if ($PackageDir -eq "") {
    if ($PSScriptRoot -ne "") {
        $PackageDir = $PSScriptRoot
    } else {
        $PackageDir = (Get-Location).Path
    }
}

if ($ManifestJson -eq "") {
    $ManifestJson = Join-Path $PackageDir "DELIVERY_FILE_MANIFEST.json"
}

if (-not (Test-Path -LiteralPath $PackageDir -PathType Container)) {
    throw "Package directory not found: $PackageDir"
}
if (-not (Test-Path -LiteralPath $ManifestJson -PathType Leaf)) {
    throw "Manifest file not found: $ManifestJson"
}

$manifest = Get-Content -LiteralPath $ManifestJson -Raw -Encoding UTF8 | ConvertFrom-Json
$excludedNames = @(
    "DELIVERY_FILE_MANIFEST.json",
    "DELIVERY_FILE_MANIFEST.sha256",
    "DELIVERY_INTEGRITY_REPORT.json",
    "DELIVERY_INTEGRITY_REPORT.md",
    "DELIVERY_INTEGRITY_RECIPIENT_REPORT.json",
    "DELIVERY_INTEGRITY_RECIPIENT_REPORT.md",
    "PACKAGE_SELF_TEST_REPORT.json",
    "PACKAGE_SELF_TEST_REPORT.md"
)

$expected = @{}
$missing = New-Object System.Collections.Generic.List[string]
$changed = New-Object System.Collections.Generic.List[string]
$checked = 0

foreach ($item in $manifest.files) {
    $rel = [string]$item.path
    $expected[$rel] = $true
    $localRel = $rel.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
    $path = Join-Path $PackageDir $localRel
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $missing.Add($rel)
        continue
    }
    $checked += 1
    $fileInfo = Get-Item -LiteralPath $path
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($fileInfo.Length -ne [int64]$item.size_bytes -or $hash -ne ([string]$item.sha256).ToLowerInvariant()) {
        $changed.Add($rel)
    }
}

$root = (Resolve-Path -LiteralPath $PackageDir).Path
$rootPrefixLength = $root.Length
$extra = New-Object System.Collections.Generic.List[string]
Get-ChildItem -LiteralPath $PackageDir -Recurse -File | ForEach-Object {
    if ($excludedNames -contains $_.Name) {
        return
    }
    $rel = $_.FullName.Substring($rootPrefixLength).TrimStart("\", "/").Replace("\", "/")
    if (-not $expected.ContainsKey($rel)) {
        $extra.Add($rel)
    }
}

$allPass = ($missing.Count -eq 0 -and $changed.Count -eq 0 -and $extra.Count -eq 0 -and $checked -eq $expected.Count)
$report = [PSCustomObject]@{
    all_pass = $allPass
    status = $(if ($allPass) { "pass" } else { "failed" })
    package = $PackageDir
    manifest = $ManifestJson
    expected_file_count = $expected.Count
    checked_file_count = $checked
    missing_files = @($missing)
    changed_files = @($changed)
    extra_files = @($extra)
}

$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutJson -Encoding UTF8

if ($allPass) {
    Write-Host "Project1 delivery integrity PASS"
    Write-Host "Checked files: $checked / $($expected.Count)"
    Write-Host "Report: $OutJson"
    exit 0
}

Write-Host "Project1 delivery integrity FAILED"
Write-Host "Missing files: $($missing.Count)"
Write-Host "Changed files: $($changed.Count)"
Write-Host "Extra files: $($extra.Count)"
Write-Host "Report: $OutJson"
exit 1
'''


RECIPIENT_README_CN = """# Project1 交付包完整性自检

本交付包内置了一个不依赖 Python 的 PowerShell 自检脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\\VERIFY_DELIVERY_INTEGRITY.ps1
```

它会读取 `DELIVERY_FILE_MANIFEST.json`，逐个检查包内文件的大小和 SHA256 哈希值，并报告：

- 是否缺文件
- 是否有文件被修改
- 是否多出清单外文件
- 实际检查了多少文件

正常结果应显示：

```text
Project1 delivery integrity PASS
```

并生成：

```text
DELIVERY_INTEGRITY_RECIPIENT_REPORT.json
```

如果结果不是 PASS，请不要继续使用该包进行专家评分或客户演示，应联系项目负责人重新发送完整交付包。
"""


PACKAGE_SELF_TEST_PS1_TEXT = r'''param(
    [string]$PackageDir = "",
    [string]$OutJson = "PACKAGE_SELF_TEST_REPORT.json",
    [switch]$SkipIntegrity
)

$ErrorActionPreference = "Stop"

function Add-Issue([System.Collections.Generic.List[string]]$Issues, [string]$Message) {
    $Issues.Add($Message) | Out-Null
}

if ($PackageDir -eq "") {
    if ($PSScriptRoot -ne "") {
        $PackageDir = $PSScriptRoot
    } else {
        $PackageDir = (Get-Location).Path
    }
}

if (-not (Test-Path -LiteralPath $PackageDir -PathType Container)) {
    throw "Package directory not found: $PackageDir"
}

$issues = New-Object System.Collections.Generic.List[string]
$requiredFiles = @(
    "START_HERE_CN.html",
    "score_audio_player.html",
    "DELIVERY_README_CN.md",
    "COMMERCIAL_PLAYBACK_README_CN.md",
    "README_FOR_EXPERTS.md",
    "SCORING_RUBRIC.md",
    "REVIEW_ISSUE_REPORT_TEMPLATE.csv",
    "REVIEW_ISSUE_REPORT_GUIDE_CN.md",
    "forms/project1_expert_rating_forms_CN.xlsx",
    "audio_pro/pro_playback_manifest.csv",
    "audio_pro/commercial_qc_summary.json",
    "VERIFY_DELIVERY_INTEGRITY.ps1",
    "OPEN_PROJECT1_REVIEW_PACKAGE.ps1"
)

foreach ($rel in $requiredFiles) {
    $path = Join-Path $PackageDir ($rel.Replace("/", [System.IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Add-Issue $issues "missing required file: $rel"
    }
}

$manifestPath = Join-Path $PackageDir "audio_pro/pro_playback_manifest.csv"
$rows = @()
$missingRefs = New-Object System.Collections.Generic.List[string]
$variantCounts = @{}
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    $rows = @(Import-Csv -LiteralPath $manifestPath -Encoding UTF8)
    foreach ($row in $rows) {
        $variant = [string]$row.variant
        if (-not $variantCounts.ContainsKey($variant)) {
            $variantCounts[$variant] = 0
        }
        $variantCounts[$variant] += 1
        foreach ($field in @("source_musicxml", "render_musicxml", "midi", "mp3")) {
            $rel = [string]$row.$field
            if ($rel -eq "") {
                Add-Issue $issues "empty manifest field ${field} for score $($row.score_id) variant $($row.variant)"
                continue
            }
            $localRel = $rel.Replace("/", [System.IO.Path]::DirectorySeparatorChar).Replace("\", [System.IO.Path]::DirectorySeparatorChar)
            $path = Join-Path $PackageDir $localRel
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                $missingRefs.Add("$field=$rel")
            }
        }
    }
    if ($rows.Count -lt 240) {
        Add-Issue $issues "manifest has $($rows.Count) rows; expected at least 240"
    }
    foreach ($variant in @("full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass")) {
        if (-not $variantCounts.ContainsKey($variant) -or $variantCounts[$variant] -lt 40) {
            Add-Issue $issues "manifest variant $variant has insufficient rows"
        }
    }
} else {
    Add-Issue $issues "missing playback manifest: audio_pro/pro_playback_manifest.csv"
}

$integrityStatus = "skipped"
$integrityReport = Join-Path $PackageDir "DELIVERY_INTEGRITY_RECIPIENT_REPORT.json"
if (-not $SkipIntegrity) {
    $verifier = Join-Path $PackageDir "VERIFY_DELIVERY_INTEGRITY.ps1"
    if (Test-Path -LiteralPath $verifier -PathType Leaf) {
        & powershell -ExecutionPolicy Bypass -File $verifier -PackageDir $PackageDir -OutJson $integrityReport
        if ($LASTEXITCODE -eq 0) {
            $integrityStatus = "pass"
        } else {
            $integrityStatus = "failed"
            Add-Issue $issues "delivery integrity verifier failed; see DELIVERY_INTEGRITY_RECIPIENT_REPORT.json"
        }
    } else {
        $integrityStatus = "missing"
        Add-Issue $issues "integrity verifier script missing"
    }
}

$mp3Count = @(Get-ChildItem -LiteralPath $PackageDir -Recurse -File -Filter "*.mp3").Count
$midiCount = @(Get-ChildItem -LiteralPath $PackageDir -Recurse -File | Where-Object { $_.Extension -in @(".mid", ".midi") }).Count
$musicxmlCount = @(Get-ChildItem -LiteralPath $PackageDir -Recurse -File | Where-Object { $_.Extension -in @(".musicxml", ".xml") }).Count
$pdfCount = @(Get-ChildItem -LiteralPath $PackageDir -Recurse -File -Filter "*.pdf").Count

if ($mp3Count -lt 240) { Add-Issue $issues "MP3 count is $mp3Count; expected at least 240" }
if ($midiCount -lt 240) { Add-Issue $issues "MIDI count is $midiCount; expected at least 240" }
if ($musicxmlCount -lt 40) { Add-Issue $issues "MusicXML/XML count is $musicxmlCount; expected at least 40" }
if ($pdfCount -lt 20) { Add-Issue $issues "PDF count is $pdfCount; expected review score PDFs" }

$allPass = ($issues.Count -eq 0 -and $missingRefs.Count -eq 0)
$report = [PSCustomObject]@{
    schema = "project1_recipient_package_self_test_v1"
    all_pass = $allPass
    status = $(if ($allPass) { "pass" } else { "failed" })
    package = $PackageDir
    integrity_status = $integrityStatus
    manifest_rows = $rows.Count
    variant_counts = $variantCounts
    mp3_count = $mp3Count
    midi_count = $midiCount
    musicxml_count = $musicxmlCount
    pdf_count = $pdfCount
    missing_manifest_references = @($missingRefs)
    issues = @($issues)
    next_action = $(if ($allPass) { "Open START_HERE_CN.html or score_audio_player.html for review." } else { "Do not use this package for expert review or customer demonstration until the issues are fixed." })
}

$outPath = Join-Path $PackageDir $OutJson
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outPath -Encoding UTF8

if ($allPass) {
    Write-Host "Project1 package self-test PASS"
    Write-Host "Manifest rows: $($rows.Count)"
    Write-Host "MP3/MIDI: $mp3Count / $midiCount"
    Write-Host "Report: $outPath"
    exit 0
}

Write-Host "Project1 package self-test FAILED"
Write-Host "Issues: $($issues.Count)"
Write-Host "Missing manifest references: $($missingRefs.Count)"
Write-Host "Report: $outPath"
exit 1
'''


PACKAGE_SELF_TEST_README_CN_TEXT = """# Project1 客户侧自检

本脚本用于专家或客户在解压交付包后快速确认包是否可用于审阅。它不依赖 Python，会检查：

- 入口页面、播放器、评分表和说明文件是否存在。
- `audio_pro/pro_playback_manifest.csv` 是否包含完整的 6 类试听版本。
- Manifest 中的 MusicXML、渲染 MusicXML、MIDI、MP3 路径是否能在本地找到。
- MP3、MIDI、MusicXML/PDF 数量是否达到交付要求。
- 可选地调用完整性校验脚本检查 SHA256。

推荐运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\\PROJECT1_PACKAGE_SELF_TEST.ps1
```

正常结果应显示：

```text
Project1 package self-test PASS
```

并生成：

```text
PACKAGE_SELF_TEST_REPORT.json
```

如果结果不是 PASS，请不要继续给专家评分或客户演示，先把报告发给项目负责人定位问题。
"""


OPEN_PACKAGE_PS1_TEXT = r'''param(
    [string]$PackageDir = "",
    [switch]$SkipIntegrity,
    [switch]$NoOpen,
    [string]$OutJson = "OPEN_PACKAGE_REPORT.json"
)

$ErrorActionPreference = "Stop"

if ($PackageDir -eq "") {
    if ($PSScriptRoot -ne "") {
        $PackageDir = $PSScriptRoot
    } else {
        $PackageDir = (Get-Location).Path
    }
}

if (-not (Test-Path -LiteralPath $PackageDir -PathType Container)) {
    throw "Package directory not found: $PackageDir"
}

$integrityStatus = "skipped"
$integrityExitCode = 0
$integrityReport = Join-Path $PackageDir "DELIVERY_INTEGRITY_RECIPIENT_REPORT.json"
$verifier = Join-Path $PackageDir "VERIFY_DELIVERY_INTEGRITY.ps1"
$selfTest = Join-Path $PackageDir "PROJECT1_PACKAGE_SELF_TEST.ps1"

if (-not $SkipIntegrity) {
    if (Test-Path -LiteralPath $selfTest -PathType Leaf) {
        & powershell -ExecutionPolicy Bypass -File $selfTest -PackageDir $PackageDir
        $integrityExitCode = $LASTEXITCODE
        $integrityStatus = $(if ($integrityExitCode -eq 0) { "pass" } else { "failed" })
        if ($integrityExitCode -ne 0) {
            throw "Package self-test failed. See PACKAGE_SELF_TEST_REPORT.json"
        }
    } elseif (-not (Test-Path -LiteralPath $verifier -PathType Leaf)) {
        throw "Integrity verifier not found: $verifier"
    } else {
        & powershell -ExecutionPolicy Bypass -File $verifier -PackageDir $PackageDir -OutJson $integrityReport
        $integrityExitCode = $LASTEXITCODE
        $integrityStatus = $(if ($integrityExitCode -eq 0) { "pass" } else { "failed" })
        if ($integrityExitCode -ne 0) {
            throw "Delivery integrity check failed. See $integrityReport"
        }
    }
}

$startPage = Join-Path $PackageDir "START_HERE_CN.html"
$playerPage = Join-Path $PackageDir "score_audio_player.html"
$openTarget = ""
if (Test-Path -LiteralPath $startPage -PathType Leaf) {
    $openTarget = $startPage
} elseif (Test-Path -LiteralPath $playerPage -PathType Leaf) {
    $openTarget = $playerPage
} else {
    throw "No START_HERE_CN.html or score_audio_player.html found in package."
}

$opened = $false
if (-not $NoOpen) {
    Start-Process -FilePath $openTarget
    $opened = $true
}

$report = [PSCustomObject]@{
    status = "pass"
    package = $PackageDir
    integrity_status = $integrityStatus
    integrity_report = $integrityReport
    opened = $opened
    open_target = $openTarget
    note = "Use score_audio_player.html for score-review navigation. Audio is a score-derived listening aid."
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PackageDir $OutJson) -Encoding UTF8

Write-Host "Project1 review package is ready."
Write-Host "Integrity: $integrityStatus"
Write-Host "Open target: $openTarget"
Write-Host "Report: $(Join-Path $PackageDir $OutJson)"
'''


ISSUE_REPORT_TEMPLATE_CSV_TEXT = """问题编号,谱例编号(score_id),材料类型(absolute/paired),音频版本,问题时间点(秒),问题类别,严重程度(1-5),具体描述,是否影响评分,反馈人,备注
EXAMPLE,P1S01,absolute,stem_alto,12.5,音频与谱面疑似不一致,4,例如第12.5秒女低声部听起来与谱面音高不符,是,Rater01,请尽量同时写小节号/拍号或附截图
P1S??,,,,,,,,,,
"""


ISSUE_REPORT_GUIDE_CN_TEXT = """# Project1 问题反馈与定位模板

如果审阅人认为某个谱例或试听音频存在问题，请填写 `REVIEW_ISSUE_REPORT_TEMPLATE.csv` 并和评分表一起返回。这个表不是评分表本身，而是用于工程定位。

## 怎么填

- `谱例编号(score_id)`：播放器左侧或文件名中的编号，例如 `P1S01`、`P1P03_A`。
- `材料类型`：逐首评分材料填 `absolute`，A/B 配对材料填 `paired`；不确定可填 `unknown`。
- `音频版本`：从播放器中的六个版本选择：`full_choir`、`piano_reference`、`stem_soprano`、`stem_alto`、`stem_tenor`、`stem_bass`。
- `问题时间点(秒)`：大约时间即可，例如 `12.5`；如果是谱面问题，也可以写小节号/拍号到备注。
- `问题类别`：建议使用 `音频与谱面疑似不一致`、`音频无声`、`音频断裂`、`谱面显示问题`、`声部音域/进行问题`、`其他`。
- `严重程度(1-5)`：1 表示轻微疑问，5 表示影响该谱例能否用于评审。
- `具体描述`：请写清楚听到或看到的问题，例如“第 8 小节男低声部听起来与谱面不同”。

## 我们如何处理

项目维护者会用谱例编号和音频版本定位到同一条 `MusicXML -> MIDI -> MP3` 记录，并检查：

1. 源 MusicXML 是否存在且可解析。
2. 渲染 MusicXML 是否与该试听版本对应。
3. MIDI 音高签名是否与渲染谱面一致。
4. MP3 是否可解析、非静音、时长与 manifest 一致。
5. 如果是单声部 stem，是否只保留目标声部。

该包中的 MP3 是由乐谱派生的辅助试听材料，不是真人合唱录音，也不是神经音频生成模型输出。正式音乐质量评分仍应以 SATB 乐谱、和声、对位、声部进行、终止式和可唱性为准。
"""


def write_recipient_verifier(package_dir: str | Path) -> dict[str, str]:
    package = Path(package_dir)
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    script = package / VERIFIER_PS1
    readme = package / VERIFIER_README_CN
    opener = package / OPEN_PACKAGE_PS1
    self_test = package / PACKAGE_SELF_TEST_PS1
    self_test_readme = package / PACKAGE_SELF_TEST_README_CN
    issue_template = package / ISSUE_REPORT_TEMPLATE_CSV
    issue_guide = package / ISSUE_REPORT_GUIDE_CN
    script.write_text(RECIPIENT_VERIFIER_PS1, encoding="utf-8")
    readme.write_text(RECIPIENT_README_CN, encoding="utf-8")
    opener.write_text(OPEN_PACKAGE_PS1_TEXT, encoding="utf-8")
    self_test.write_text(PACKAGE_SELF_TEST_PS1_TEXT, encoding="utf-8")
    self_test_readme.write_text(PACKAGE_SELF_TEST_README_CN_TEXT, encoding="utf-8")
    issue_template.write_text(ISSUE_REPORT_TEMPLATE_CSV_TEXT, encoding="utf-8-sig")
    issue_guide.write_text(ISSUE_REPORT_GUIDE_CN_TEXT, encoding="utf-8")
    return {
        "verifier_ps1": str(script),
        "readme_cn": str(readme),
        "open_package_ps1": str(opener),
        "package_self_test_ps1": str(self_test),
        "package_self_test_readme_cn": str(self_test_readme),
        "issue_report_template_csv": str(issue_template),
        "issue_report_guide_cn": str(issue_guide),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write standalone recipient-side integrity verifier into a delivery package.")
    parser.add_argument("--package-dir", required=True)
    args = parser.parse_args()
    print(write_recipient_verifier(args.package_dir))


if __name__ == "__main__":
    main()
