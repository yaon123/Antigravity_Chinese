# Antigravity 仿 Claude Code 主题与汉化 · 一键安装
# 编码: UTF-8
# 用法:
#   .\install.ps1
#   .\install.ps1 -Resources "D:\Antigravity\resources"
#   .\install.ps1 -SkipCli          # 只装界面主题，不碰 CLI 配置

[CmdletBinding()]
param(
    [string]$Resources,
    [switch]$SkipCli
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

Write-Host '==========================================================' -ForegroundColor DarkYellow
Write-Host ' Antigravity 仿 Claude Code 主题与汉化 · 部署程序' -ForegroundColor Cyan
Write-Host '==========================================================' -ForegroundColor DarkYellow
Write-Host ''

function Resolve-Python {
    foreach ($name in @('python', 'python3', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

# ---- 前置检查 -------------------------------------------------------------
$python = Resolve-Python
if (-not $python) {
    Write-Host '[ERROR] 没有找到 Python。请先安装 Python 3.8+ 并加入 PATH。' -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $patchScript)) {
    Write-Host "[ERROR] 找不到补丁脚本: $patchScript" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    Write-Host '[WARN] 没有找到 npx（Node.js）。打包 asar 需要它，请先安装 Node.js。' -ForegroundColor Yellow
}

# ---- 1. 部署 CLI 配置 -----------------------------------------------------
if (-not $SkipCli) {
    $src = Join-Path $root 'cli\settings.json'
    $cliDir = Join-Path $HOME '.gemini\antigravity-cli'
    $dst = Join-Path $cliDir 'settings.json'
    if (Test-Path $src) {
        if (-not (Test-Path $cliDir)) {
            New-Item -ItemType Directory -Path $cliDir -Force | Out-Null
        }
        if (Test-Path $dst) {
            # 已有配置先备份，避免覆盖用户真实设置
            $bak = "$dst.bak-theme"
            Copy-Item $dst $bak -Force
            Write-Host "[√] 已备份原有 CLI 配置 -> $bak" -ForegroundColor DarkGray
        }
        Copy-Item $src $dst -Force
        Write-Host "[√] CLI 配置已安装: $dst" -ForegroundColor Green
    } else {
        Write-Host "[!] 跳过 CLI 配置（找不到 $src）" -ForegroundColor Yellow
    }
}

# ---- 2. 注入主进程钩子 ----------------------------------------------------
Write-Host ''
Write-Host '[*] 正在注入桌面客户端补丁...' -ForegroundColor Yellow
$args = @($patchScript, 'install')
if ($Resources) { $args += @('--resources', $Resources) }

& $python @args
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Host '[SUCCESS] 部署完成！' -ForegroundColor Green
    Write-Host '请完全退出（含托盘图标）并重新打开 Antigravity 客户端。' -ForegroundColor Cyan
    Write-Host '之后改 CSS / 词典 / 注入脚本 都不用重装，窗口内按 Ctrl+R 即热更新。' -ForegroundColor DarkGray
} else {
    Write-Host '[ERROR] 部署失败，安装目录未被改动。请查看上方错误信息。' -ForegroundColor Red
    Write-Host '如果提示客户端正在运行，请先完全退出 Antigravity 再重试。' -ForegroundColor Yellow
}
exit $code
