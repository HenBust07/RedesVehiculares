param(
    [string]$PythonPath = 'python',
    [switch]$Demo,
    [switch]$Diagnostico,
    [switch]$PruebaInterfaz
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command $PythonPath -ErrorAction SilentlyContinue)) {
    throw 'Indique -PythonPath con un Python existente que tenga Tkinter, PySerial y Matplotlib.'
}
foreach ($p5Drive in @([System.IO.Path]::GetPathRoot($PSScriptRoot),'C:\','D:\') | Select-Object -Unique) {
    $p5DriveInfo = [System.IO.DriveInfo]::new($p5Drive)
    if ($p5DriveInfo.IsReady -and $p5DriveInfo.AvailableFreeSpace -lt 1000000000) {
        throw "Margen inferior a 1 GB en $p5Drive"
    }
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PIP_NO_CACHE_DIR = '1'
$env:CCACHE_DISABLE = '1'
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot 'results\lab_v1\mplconfig'
$p5Arguments = @('-B','-X','utf8','-m','captura.p5_lab')
if ($Demo) { $p5Arguments += '--demo' }
if ($Diagnostico) { $p5Arguments += '--check' }
if ($PruebaInterfaz) { $p5Arguments += '--smoke-test' }
Push-Location $PSScriptRoot
try {
    & $PythonPath @p5Arguments
    if ($LASTEXITCODE -ne 0) { throw "El laboratorio termino con codigo $LASTEXITCODE" }
} finally { Pop-Location }
