param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [ValidateSet('date','header','both','page')][string]$Case='page',
    [double]$GpuGiB=4.0
)
$ErrorActionPreference='Stop'
$trial=$PSScriptRoot
$python=Join-Path $trial '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ImagePath -PathType Leaf)) {
    throw "Khong tim thay anh: $ImagePath"
}
$output=Join-Path $trial ('results\manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $python (Join-Path $trial 'run_deepseek_trial.py') --image $ImagePath --model (Join-Path $trial 'model') --out $output --case $Case --gpu-gib $GpuGiB
exit $LASTEXITCODE
