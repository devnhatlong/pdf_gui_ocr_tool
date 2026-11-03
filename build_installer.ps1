# === build_installer.ps1 === Build phần mềm (PyInstaller) rồi tạo bộ cài (Inno Setup).
#   .\build_installer.ps1                     # build phần mềm + bộ cài Tiêu chuẩn và Đầy đủ
#   .\build_installer.ps1 -Edition Standard   # chỉ 1 bản
#   .\build_installer.ps1 -SkipApp            # dùng lại dist\ đã build, chỉ tạo bộ cài
# Cần: .venv đã cài requirements, models\ đã tải (download_models.py), Inno Setup 6.4+.
# Kết quả: installer_output\OfflineOCR_Studio_<phiên bản>_Setup_<bản>.exe

param(
    [ValidateSet("All", "Standard", "Full")] [string]$Edition = "All",
    [switch]$SkipApp
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Chưa cài Inno Setup 6 (https://jrsoftware.org/isdl.php)" }
if (-not (Test-Path "models\paddlex\official_models\PP-OCRv6_medium_det")) { throw "Chưa có models\ — chạy: .venv\Scripts\python.exe download_models.py" }

# Bộ cài WebView2 offline và file ngôn ngữ tiếng Việt (tải 1 lần, sau đó build offline)
$redist = "installer\redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
if (-not (Test-Path $redist)) {
    New-Item -ItemType Directory -Force (Split-Path $redist) | Out-Null
    Invoke-WebRequest "https://go.microsoft.com/fwlink/?linkid=2124701" -OutFile $redist -UseBasicParsing
}
if ((Get-AuthenticodeSignature $redist).Status -ne "Valid") { throw "Chữ ký số của $redist không hợp lệ" }
if (-not (Test-Path "installer\languages\Vietnamese.isl")) {
    New-Item -ItemType Directory -Force "installer\languages" | Out-Null
    Invoke-WebRequest "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/Vietnamese.isl" `
        -OutFile "installer\languages\Vietnamese.isl" -UseBasicParsing
}

if (-not $SkipApp) {
    Write-Host "=== Build phần mềm (PyInstaller) ===" -ForegroundColor Cyan
    & .venv\Scripts\pyinstaller.exe OfflineOCR_Studio.spec --noconfirm
    if ($LASTEXITCODE) { throw "PyInstaller lỗi" }
}

$editions = if ($Edition -eq "All") { @("Standard", "Full") } else { @($Edition) }
foreach ($ed in $editions) {
    Write-Host "=== Tạo bộ cài: $ed ===" -ForegroundColor Cyan
    & $iscc "/DEdition=$ed" "installer\OfflineOCR_Studio.iss"
    if ($LASTEXITCODE) { throw "Inno Setup lỗi ($ed)" }
}
Get-ChildItem installer_output\*.exe | ForEach-Object { "{0}  {1:N0} MB" -f $_.Name, ($_.Length / 1MB) }
