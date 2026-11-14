param(
    [Parameter(Mandatory=$true)][string]$NarrationFile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$document = Get-Content -LiteralPath $NarrationFile -Raw -Encoding UTF8 | ConvertFrom-Json
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Maria Desktop')
    $speaker.Rate = 0
    foreach ($scene in $document.scenes) {
        $audioPath = Join-Path $OutputDirectory ($scene.id + '.wav')
        $speaker.SetOutputToWaveFile($audioPath)
        $speaker.Speak([string]$scene.narration)
        $speaker.SetOutputToNull()
    }
} finally {
    $speaker.Dispose()
}
