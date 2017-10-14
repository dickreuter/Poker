;NSIS Modern User Interface
;Basic Example Script

;--------------------------------
;Include Modern UI

  !include "MUI2.nsh"
  !define MUI_PRODUCT "DeepMind Pokerbot"
  !define MUI_FILE "main"
  !define MUI_VERSION ""
  !define MUI_BRANDINGTEXT "DeepMind Pokerbot"
  !define MUI_ICON "C:\Users\Nicolas\Dropbox\PythonProjects\Poker\poker\icon.ico"
  !define MUI_UNICON "C:\Users\Nicolas\Dropbox\PythonProjects\Poker\poker\icon.ico"
  CRCCheck On
  
  ;--------------------------------
;Language	
  !insertmacro MUI_LANGUAGE "English"
  !include LogicLib.nsh

;--------------------------------


;Folder selection page
 
  InstallDir "$APPDATA\${MUI_PRODUCT}"
 
 
;--------------------------------
;Modern UI Configuration
 
Page components
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles
 
 

 
 
;-------------------------------- 
;General

  ;Name and file
  Name "DeepMindPokerbot"
  OutFile "..\DeepMindPokerbot_winstaller.exe"

  

  
  ;Get installation folder from registry if available
  InstallDirRegKey HKCU "Software\DeepMindPokerbot" ""

  ;Request application privileges for Windows Vista
  RequestExecutionLevel admin ;Require admin rights on NT6+ (When UAC is turned on)


;--------------------------------
;Installer Sections

Section "DeepMind Pokerbot" 
SectionIn RO

   SetOutPath "$INSTDIR"
   File /r "C:\Program Files (x86)\Tesseract-OCR\*"
   File /r "C:\Users\Nicolas\Dropbox\PythonProjects\Poker\poker\dist\main\*"

  
  ;Store installation folder
  WriteRegStr HKCU "Software\DeepMindPokerbot" "" $INSTDIR
  
  ;create desktop shortcut
  CreateShortCut "$DESKTOP\${MUI_PRODUCT}.lnk" "$INSTDIR\${MUI_FILE}" "" "$INSTDIR\icon.ico"
  
 ;create start-menu items
  CreateDirectory "$SMPROGRAMS\${MUI_PRODUCT}"
  CreateShortCut "$SMPROGRAMS\${MUI_PRODUCT}\Uninstall.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0
  CreateShortCut "$SMPROGRAMS\${MUI_PRODUCT}\${MUI_PRODUCT}.lnk" "$INSTDIR\${MUI_FILE}.exe" "$INSTDIR\icon.ico" "$INSTDIR\${MUI_FILE}.exe" 0
 
 ;write uninstall information to the registry
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${MUI_PRODUCT}" "DisplayName" "${MUI_PRODUCT} (remove only)"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${MUI_PRODUCT}" "UninstallString" "$INSTDIR\Uninstall.exe"

  ;Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  Call LaunchLink
SectionEnd


;--------------------------------

;Uninstaller Section  
Section "Uninstall"
 
;Delete Files 
  RMDir /r "$INSTDIR\*.*"    
 
;Remove the installation directory
  RMDir "$INSTDIR"
 
;Delete Start Menu Shortcuts
  Delete "$DESKTOP\${MUI_PRODUCT}.lnk"
  Delete "$SMPROGRAMS\${MUI_PRODUCT}\*.*"
  RmDir  "$SMPROGRAMS\${MUI_PRODUCT}"
  
 ;Delete Desktop Shortcuts
  Delete "$DESKTOP\${MUI_PRODUCT}.lnk"
 
;Delete Uninstaller And Unistall Registry Entries
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\${MUI_PRODUCT}"
  DeleteRegKey HKEY_LOCAL_MACHINE "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\${MUI_PRODUCT}"  
 
SectionEnd


;--------------------------------    
;MessageBox Section
 
 

 
Function un.onUninstSuccess
  MessageBox MB_OK "You have successfully uninstalled ${MUI_PRODUCT}."
FunctionEnd

 Function LaunchLink
	 MessageBox MB_YESNO "Start the Pokerbot now?" IDYES true IDNO false
	true:
		ExecShell "" "$DESKTOP\${MUI_PRODUCT}.lnk"
	false:
		
FunctionEnd


Function .onInit
UserInfo::GetAccountType
pop $0
${If} $0 != "admin" ;Require admin rights on NT4+
    MessageBox mb_iconstop "Administrator rights required!"
    SetErrorLevel 740 ;ERROR_ELEVATION_REQUIRED
    Quit
${EndIf}
FunctionEnd
 
;eof