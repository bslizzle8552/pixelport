param([string]$Executable = (Join-Path (Split-Path -Parent $PSScriptRoot) 'dist\onefile\PixelPort.exe'))

$ErrorActionPreference = 'Stop'
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'PixelPort.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $Executable
$shortcut.WorkingDirectory = Split-Path -Parent $Executable
$shortcut.IconLocation = "$Executable,0"
$shortcut.Description = 'PixelPort screenshot capture'
$shortcut.Save()
Write-Output "Installed shortcut: $shortcutPath"
Write-Output "Executable: $Executable"
Write-Output 'To pin: find PixelPort in Start, right-click, and select Pin to taskbar.'
