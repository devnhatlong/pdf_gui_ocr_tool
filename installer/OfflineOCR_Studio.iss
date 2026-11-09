; === OfflineOCR_Studio.iss === Bộ cài Inno Setup (6.4+) — cài hoàn toàn offline.
; Đóng gói: phần mềm (dist\OfflineOCR_Studio), model OCR (models\), WebView2 Runtime bản offline.
;
;   Bản Tiêu chuẩn:  ISCC.exe /DEdition=Standard installer\OfflineOCR_Studio.iss   (không kèm PaddleOCR-VL)
;   Bản Đầy đủ:      ISCC.exe /DEdition=Full     installer\OfflineOCR_Studio.iss   (kèm PaddleOCR-VL 1.6)
; Hoặc chạy build_installer.ps1 để build phần mềm + cả 2 bộ cài.

#ifndef Edition
  #define Edition "Standard"
#endif
#define AppName "OfflineOCR Studio"
#define AppVersion "2.1.0"
#define AppPublisher "Nguyễn Nhật Long - Đội CNTT, Phòng Tham mưu"
#define AppExe "OfflineOCR_Studio.exe"
#define Root ".."
#define Dist Root + "\dist\OfflineOCR_Studio"
#define Models Root + "\models"
#if Edition == "Full"
  #define EditionLabel "Đầy đủ"
  #define ModelExcludes ".cache,func_ret,locks,temp"
#else
  #define EditionLabel "Tiêu chuẩn"
  #define ModelExcludes ".cache,func_ret,locks,temp,\PaddleOCR-VL-1.6"
#endif

[Setup]
AppId={{6C1E8B4A-3F2D-4B7E-9A51-0F8D2C7E4B19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} ({#EditionLabel})
AppPublisher={#AppPublisher}
AppContact=0365 756 687
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Root}\installer_output
OutputBaseFilename=OfflineOCR_Studio_{#AppVersion}_Setup_{#Edition}
SetupIconFile={#Root}\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} ({#EditionLabel})
WizardStyle=modern
Compression=lzma2/normal
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=8
; Một file Setup.exe (Inno Setup 6.4+ hỗ trợ tới gần 4 GB không cần chia file)
DiskSpanning=no
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "vi"; MessagesFile: "languages\Vietnamese.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình Desktop"; GroupDescription: "Biểu tượng:"

[Files]
; Phần mềm (thư viện Python, Paddle, PyTorch, giao diện, Tesseract) — sinh bởi PyInstaller
; (Excludes có "\" ở đầu = chỉ tính từ thư mục gốc; không có "\" sẽ loại nhầm cả chardet\models, ...\data)
Source: "{#Dist}\*"; DestDir: "{app}"; Excludes: "\models,\data,\selftest.txt,\_internal\torch\include,\_internal\paddle\include"; Flags: ignoreversion recursesubdirs createallsubdirs
; Model OCR đi kèm — phần mềm đọc trực tiếp từ {app}\models, không cần tải thêm
Source: "{#Models}\paddlex\official_models\*"; DestDir: "{app}\models\paddlex\official_models"; Excludes: "{#ModelExcludes}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Models}\vietocr\*"; DestDir: "{app}\models\vietocr"; Flags: ignoreversion recursesubdirs createallsubdirs
; WebView2 Runtime bản offline — chỉ cài khi máy chưa có
Source: "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Đang cài Microsoft Edge WebView2 Runtime..."; Check: NeedsWebView2; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "Mở {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; File sinh ra khi chạy trong thư mục cài đặt (dữ liệu người dùng ở %LOCALAPPDATA% được giữ lại)
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
const
  WebView2Guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Version(Root: Integer; Key: String): String;
begin
  if not RegQueryStringValue(Root, Key, 'pv', Result) then
    Result := '';
end;

{ WebView2 đã cài nếu có khóa "pv" khác rỗng và khác 0.0.0.0 (máy hoặc người dùng) }
function NeedsWebView2: Boolean;
var
  V: String;
begin
  V := WebView2Version(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2Guid);
  if (V = '') or (V = '0.0.0.0') then
    V := WebView2Version(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Guid);
  if (V = '') or (V = '0.0.0.0') then
    V := WebView2Version(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2Guid);
  Result := (V = '') or (V = '0.0.0.0');
end;
