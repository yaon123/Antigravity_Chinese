# Claude Code Style PowerShell Prompt & CLI Environment
# 为 PowerShell 与 Antigravity CLI 提供 Claude Code 风格终端体验

# 强制 UTF-8 编码，防止中文及制表符乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function prompt {
    # 颜色定义 (ANSI 转义码)
    $esc = [char]27
    $cTerracotta = "$esc[38;2;217;119;87m" # #D97757 标志陶土橙
    $cCream      = "$esc[38;2;237;234;229m" # #EDEAE5 暖沙白
    $cMuted      = "$esc[38;2;130;123;112m" # #827B70 弱灰
    $cReset      = "$esc[0m"

    # 获取当前工作目录（简短显示）
    $cwd = (Get-Location).Path
    if ($cwd.StartsWith($HOME)) {
        $cwd = "~" + $cwd.Substring($HOME.Length)
    }

    # 简易 Git 分支检测
    $gitBranch = ""
    try {
        $branch = git branch --show-current 2>$null
        if ($branch) {
            $gitBranch = " $cMuted($branch)$cReset"
        }
    } catch {}

    # Claude Code 标志性简约提示符行
    Write-Host ""
    Write-Host "$cCream$cwd$cReset$gitBranch"
    return "$cTerracotta❯$cReset "
}

Write-Host " Claude Code 终端主题环境已加载 (`#D97757 陶土橙 / UTF-8 汉化支持)" -ForegroundColor DarkYellow
