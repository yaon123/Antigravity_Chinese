# 升级桌面快捷方式为「自动自愈启动器」
$ErrorActionPreference = 'Stop'

$wsh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Antigravity.lnk'
$origBackup = Join-Path $desktop 'Antigravity (原版直通).lnk'
$appExe = Join-Path $env:LOCALAPPDATA 'Programs\antigravity\Antigravity.exe'
$vbsPath = 'E:\lyh\theme\scripts\launch.vbs'

if (Test-Path $lnkPath) {
    if (-not (Test-Path $origBackup)) {
        Copy-Item $lnkPath $origBackup -Force
        Write-Host "已备份原快捷方式 -> $origBackup" -ForegroundColor DarkGray
    }
}

$shortcut = $wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = 'wscript.exe'
$shortcut.Arguments = "`"$vbsPath`""
$shortcut.WorkingDirectory = 'E:\lyh\theme'
$shortcut.IconLocation = "$appExe,0"
$shortcut.Description = 'Antigravity (自动保持汉化与 Claude Code 皮肤)'
$shortcut.Save()

Write-Host '[SUCCESS] 桌面快捷方式已成功升级为永久自愈启动器！' -ForegroundColor Green
Write-Host "以后每次双击桌面 Antigravity 图标，都将自动检查更新并在需要时秒级静默修复。" -ForegroundColor Cyan
