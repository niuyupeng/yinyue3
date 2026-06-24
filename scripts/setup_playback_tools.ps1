param(
    [string]$Version = "2.5.5",
    [string]$ToolsDir = "external_tools",
    [switch]$DownloadMuseScoreGeneral,
    [switch]$SkipFfmpegInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$tools = Join-Path $root $ToolsDir
$downloads = Join-Path $tools "downloads"
$fluidsynthRoot = Join-Path $tools "fluidsynth"
$soundfontRoot = Join-Path $tools "soundfonts"
New-Item -ItemType Directory -Force -Path $downloads, $fluidsynthRoot, $soundfontRoot | Out-Null

function Test-CommandAvailable {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

$zipName = "fluidsynth-v$Version-win10-x64-cpp11.zip"
$zipPath = Join-Path $downloads $zipName
$url = "https://github.com/FluidSynth/fluidsynth/releases/download/v$Version/$zipName"

if (-not (Test-Path $zipPath)) {
    Write-Host "Downloading FluidSynth $Version from GitHub release assets..."
    Invoke-WebRequest -Uri $url -OutFile $zipPath
} else {
    Write-Host "FluidSynth archive already exists: $zipPath"
}

$extractDir = Join-Path $fluidsynthRoot "v$Version"
if (-not (Test-Path $extractDir)) {
    Write-Host "Extracting FluidSynth..."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
}

$fluidExe = Get-ChildItem -LiteralPath $extractDir -Recurse -Filter fluidsynth.exe | Select-Object -First 1
if (-not $fluidExe) {
    throw "fluidsynth.exe was not found after extraction."
}

$museScoreBasic = "C:\Program Files\MuseScore 4\sound\MS Basic.sf3"
$soundfont = $null
if (Test-Path $museScoreBasic) {
    $soundfont = Get-Item -LiteralPath $museScoreBasic
    Write-Host "Using MuseScore installed SoundFont: $($soundfont.FullName)"
}

if ($DownloadMuseScoreGeneral) {
    $sf3 = Join-Path $soundfontRoot "MuseScore_General.sf3"
    $license = Join-Path $soundfontRoot "MuseScore_General_License.md"
    $readme = Join-Path $soundfontRoot "MuseScore_General_Readme.md"
    if (-not (Test-Path $sf3)) {
        Write-Host "Downloading MuseScore_General.sf3..."
        Invoke-WebRequest -Uri "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3" -OutFile $sf3
    }
    if (-not (Test-Path $license)) {
        Invoke-WebRequest -Uri "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General_License.md" -OutFile $license
    }
    if (-not (Test-Path $readme)) {
        Invoke-WebRequest -Uri "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General_Readme.md" -OutFile $readme
    }
    $soundfont = Get-Item -LiteralPath $sf3
    Write-Host "Using downloaded MuseScore General SoundFont: $($soundfont.FullName)"
}

if (-not $soundfont) {
    throw "No SoundFont found. Install MuseScore 4 or rerun with -DownloadMuseScoreGeneral."
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
if ((-not $ffmpeg -or -not $ffprobe) -and -not $SkipFfmpegInstall) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "FFmpeg/ffprobe missing. Installing Gyan.FFmpeg with winget..."
        winget install --id Gyan.FFmpeg --source winget --accept-source-agreements --accept-package-agreements
        $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
        $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    } else {
        Write-Warning "FFmpeg is missing and winget is not available. MP3 conversion will fail until FFmpeg is installed."
    }
}

if (-not $ffmpeg -or -not $ffprobe) {
    $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $wingetPackages) {
        if (-not $ffmpeg) {
            $ffmpeg = Get-ChildItem -LiteralPath $wingetPackages -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue |
                Select-Object -First 1
        }
        if (-not $ffprobe) {
            $ffprobe = Get-ChildItem -LiteralPath $wingetPackages -Recurse -Filter ffprobe.exe -ErrorAction SilentlyContinue |
                Select-Object -First 1
        }
    }
}

$ffmpegPath = ""
if ($ffmpeg) {
    if ($ffmpeg.Source) {
        $ffmpegPath = $ffmpeg.Source
    } elseif ($ffmpeg.FullName) {
        $ffmpegPath = $ffmpeg.FullName
    }
}
$ffprobePath = ""
if ($ffprobe) {
    if ($ffprobe.Source) {
        $ffprobePath = $ffprobe.Source
    } elseif ($ffprobe.FullName) {
        $ffprobePath = $ffprobe.FullName
    }
}

$ffmpegLocalBin = Join-Path $tools "ffmpeg\bin"
if ($ffmpegPath -and $ffprobePath) {
    New-Item -ItemType Directory -Force -Path $ffmpegLocalBin | Out-Null
    Copy-Item -LiteralPath $ffmpegPath -Destination (Join-Path $ffmpegLocalBin "ffmpeg.exe") -Force
    Copy-Item -LiteralPath $ffprobePath -Destination (Join-Path $ffmpegLocalBin "ffprobe.exe") -Force
    $sourceBin = Split-Path -Parent $ffmpegPath
    Get-ChildItem -LiteralPath $sourceBin -Filter *.dll -ErrorAction SilentlyContinue |
        Copy-Item -Destination $ffmpegLocalBin -Force
    $ffmpegPath = Join-Path $ffmpegLocalBin "ffmpeg.exe"
    $ffprobePath = Join-Path $ffmpegLocalBin "ffprobe.exe"
}

$envFile = Join-Path $tools "playback_env.ps1"
@"
`$env:CHORALE_FLUIDSYNTH_EXE = '$($fluidExe.FullName)'
`$env:CHORALE_SOUNDFONT = '$($soundfont.FullName)'
`$env:CHORALE_FFMPEG_EXE = '$ffmpegPath'
`$env:CHORALE_FFPROBE_EXE = '$ffprobePath'
"@ | Set-Content -LiteralPath $envFile -Encoding UTF8

Write-Host ""
Write-Host "Playback tool setup complete."
Write-Host "FluidSynth: $($fluidExe.FullName)"
Write-Host "SoundFont:  $($soundfont.FullName)"
if ($ffmpeg) {
    Write-Host "FFmpeg:     $ffmpegPath"
}
if ($ffprobe) {
    Write-Host "FFprobe:    $ffprobePath"
}
Write-Host "Env file:   $envFile"
Write-Host ""
Write-Host "For this PowerShell session, run:"
Write-Host ". '$envFile'"

& $fluidExe.FullName --version
