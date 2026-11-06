# Antigravity 官方原版 · 一键还原
# 编码: UTF-8
# 用法:
#   .\restore.ps1
#   .\restore.ps1 -Resources "D:\Antigravity\resources"

[CmdletBinding()]
param(
    [string]$Resources
)

$ErrorActionPreference = 'Stop'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$root = $PSScriptRoot
$patchScript = Join-Path $root 'scripts\patch_asar.py'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host '==========================================================' -ForegroundColor Red
Write-Host ' Antigravity 官方原版还原程序' -ForegroundColor Yellow
Write-Host '==========================================================' -ForegroundColor Red
Write-Host ''

$python = $null
foreach ($name in @('python', 'python3', 'py')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) {
    Write-Host '[ERROR] 没有找到 Python，无法还原。' -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $patchScript)) {
    Write-Host "[ERROR] 找不到补丁脚本: $patchScript" -ForegroundColor Red
    exit 1
}

$args = @($patchScript, 'restore')
if ($Resources) { $args += @('--resources', $Resources) }

& $python @args
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host '[SUCCESS] 已还原为官方原版资源，重启 Antigravity 即可恢复初始状态。' -ForegroundColor Green
} else {
    Write-Host '[ERROR] 还原失败，安装目录未被改动。请查看上方错误信息。' -ForegroundColor Red
    Write-Host '若提示客户端正在运行，请先完全退出 Antigravity（含托盘图标）再重试。' -ForegroundColor Yellow
}
exit $code
