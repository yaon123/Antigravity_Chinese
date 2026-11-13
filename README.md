# Antigravity 仿 Claude Code 主题 · 全深度汉化套件

给 **Antigravity**（Google 的 Agentic 桌面客户端，Electron 应用）套上 Claude Code 的暖暗色外观，
并把界面汉化成中文。

- 客户端实测版本：**Antigravity 2.31.2**（Electron + React + Tailwind v4）
- 皮肤走 **设计令牌优先**（CSS 变量）+ 少量真实组件钩子，应用小版本更新一般不会失效
- 汉化是**运行时注入**：改词典、改样式都不用重新打包，窗口内 `Ctrl+R` 即热更新

---

## 〇、这次修了什么（相对上一版）

| 问题 | 上一版表现 | 现在 |
| --- | --- | --- |
| asar 重打包丢 `unpacked` 标记 | app.asar 从 4.79MB 膨胀到 **18MB**，347 个本该留在 `app.asar.unpacked` 的文件被塞进归档 | 自动按原版布局还原 `--unpack-dir`，产物 4.58MB；**1092 个文件里只有 `dist/main.js` 变了，其余逐字节一致** |
| 失败也返回 0 | 安装失败时仍打印「部署完成」 | 任一环节失败即非零退出并给出原因 |
| 不检查客户端是否在运行 | 运行中替换文件会装出半成品 | 先探测 `app.asar` 占用，运行中直接拒绝并提示 |
| 路径硬编码 `C:\Users\andy_\...` 和 `e:\lyh\theme` | 换机器/换盘就废 | 自动定位安装目录，项目路径按脚本位置推导，可用 `--resources` 覆盖 |
| 无产物校验 | 打坏了才发现 | 校验条目数、unpacked 数、钩子标记、`node --check`，不通过则不替换 |
| 钩子注入所有 webContents | 内置浏览器网页、开发者工具也被改样式/被汉化 | 只处理界面窗口，跳过 webview / devtools 等 |
| 钩子 `dom-ready` + `did-finish-load` 各注入一次 | 一次加载注入 4 遍、4 个 MutationObserver | 只在 `dom-ready` 注入，重复注入有幂等守卫，重载会先移除旧 CSS |
| 皮肤选择器大面积空转 | `[data-role=user]`、`[class*=toolCard]`、`textarea`、`[role=dialog]` 等真实命中数为 **0**，只有配色变量生效 | 改为覆盖应用真实消费的 ~110 个设计令牌 + 真实 `agy-*` / `data-testid` 钩子；补齐 `--onyx-*` 图层令牌（作曲区、选中行） |
| 汉化引擎漏翻 placeholder | `INPUT/TEXTAREA` 被整体跳过，placeholder 翻译分支是死代码 | 属性照常翻译，内部文本不碰 |
| 汉化会污染对话正文 | 任意文本节点都会被替换 | 代码块 / 对话正文硬保护，只翻界面骨架；动态文案用 `patterns` 正则 |
| 设置页描述漏翻 | `whitespace-pre-wrap` 被当正文保护，设置页说明整段不翻 | 弹窗/设置面板内不再误保护，实测漏翻从 12 处降到 **0** |
| 词典覆盖不足 | 73 条 exact | **443 条 exact + 9 条 partial + 48 条 patterns** |

> 说明：`scripts/_*.py`、`scripts/_*.mjs` 和 `.diag/` 是这次排查用的取证/自检工具与截图证据，不影响运行，可以整个删掉。

---

## 一、先看清楚这套东西是怎么生效的

Antigravity 的界面不是本地静态页面，而是由本地语言服务通过 `https://127.0.0.1:<随机端口>/` 提供的
Web UI。所以主题/汉化只能靠下面这条链路：

```
resources/app.asar 里的 dist/main.js
        └─ 安装时追加一段钩子：app.on('web-contents-created')
              └─ 每个界面窗口 dom-ready 时
                    ├─ contents.insertCSS()  ← 注入 theme/claude-theme.css
                    └─ contents.executeJavaScript()  ← 注入 scripts/injector.js + locales/zh-CN.json
```

关键点：**钩子每次加载都会重新读这三个文件**。所以：

- 改 `theme/claude-theme.css` → `Ctrl+R` 立刻看到效果
- 改 `locales/zh-CN.json` / `scripts/injector.js` → `Ctrl+R` 立刻生效
- 只有**第一次注入钩子**、或者 **Antigravity 自动更新覆盖了 app.asar** 之后，才需要重跑安装

---

## 二、目录结构

```text
theme\
├── theme\claude-theme.css        # 皮肤：覆盖 Antigravity 真实设计令牌 + 组件微调
├── locales\zh-CN.json            # 汉化词典：exact 精确词条 / partial 子串 / patterns 正则
├── scripts\
│   ├── injector.js               # 渲染进程汉化引擎（幂等、保护对话正文）
│   └── patch_asar.py             # 补丁工具：install / restore / verify
├── cli\                          # 终端侧配色与提示符（可选）
│   ├── claude-code-theme.json    # Windows Terminal 配色方案
│   ├── settings.json             # Antigravity CLI 配置（写入 ~/.gemini/antigravity-cli/）
│   └── prompt.ps1                # PowerShell 仿 Claude Code 提示符
├── install.ps1                   # 一键安装
├── restore.ps1                   # 一键还原
└── README.md
```

---

## 三、安装

**安装前必须完全退出 Antigravity**（包括右下角托盘图标右键退出），否则 `app.asar` 被占用会直接拒绝。

```powershell
cd E:\lyh\theme
.\install.ps1
```

安装脚本会依次：

1. 部署 CLI 配置到 `~\.gemini\antigravity-cli\settings.json`（已有文件会先备份成 `.bak-theme`）
2. 备份官方原版 `app.asar` → `app.asar.bak`
3. 解包 → 往 `dist/main.js` 末尾写入钩子 → 重新打包
4. **校验**：条目数、unpacked 文件数必须与原版一致，`main.js` 要能通过 `node --check`
5. 校验通过才替换安装目录里的 `app.asar`

安装完成后重启 Antigravity 即可。

> 自定义安装位置：`.\install.ps1 -Resources "D:\Antigravity\resources"`
> 只装界面、不碰 CLI：`.\install.ps1 -SkipCli`

### 体检 / 还原

```powershell
.\restore.ps1          # 还原官方原版
python scripts\patch_asar.py verify    # 只检查现状，不改任何文件
```

还原同样要求先退出客户端。还原后的 `app.asar` 与原版**逐字节一致**（已用官方 asar CLI 校验）。

---

## 四、日常调整

| 想改什么 | 改哪个文件 | 怎么生效 |
| --- | --- | --- |
| 颜色 / 圆角 / 字体 / 组件外观 | `theme\claude-theme.css` | `Ctrl+R` |
| 加词条、改译文 | `locales\zh-CN.json` 的 `exact` | `Ctrl+R` |
| 动态文案（带数字/时间的） | `locales\zh-CN.json` 的 `patterns` | `Ctrl+R` |
| 汉化范围、保护区域 | `scripts\injector.js` | `Ctrl+R` |
| 钩子本身（极少改动） | `scripts\patch_asar.py` | 需要重新安装 + 重启 |

### 词典结构

```jsonc
{
  "exact":    { "New Conversation": "新建对话" },          // 整段文本完全相等才替换
  "partial":  [ { "from": "Exit code ", "to": "退出码 " } ], // 子串替换（慎用，容易误伤）
  "patterns": [ { "re": "^Worked for (.+)$", "to": "已工作 $1" } ] // 正则 + 捕获组
}
```

> 汉化引擎会**跳过**对话正文、代码块、输入框和 `contenteditable` 区域，只翻译界面骨架，
> 避免把 Agent 的输出和你自己的消息改掉。

---

## 五、已知限制

- 这是**注入式**方案，不是官方换肤接口。Antigravity 更新后若改了 DOM 结构/令牌名，部分样式或词条可能失效；
  更新也会覆盖 `app.asar`，需要重跑一次 `install.ps1`（`app.asar.bak` 会保留最早的原版）。
- 汉化只覆盖词典里收录的词条。发现英文没翻译，往 `exact` 里加即可，不用重装。
- 内置浏览器（webview）、插件面板、开发者工具**不会**被注入，避免影响网页内容和插件。
- 客户端本身默认开启随机端口的远程调试（`--remote-debugging-port`），这是官方行为，与本套件无关。

---

## 六、故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| 安装报「客户端正在运行」 | 完全退出 Antigravity（含托盘图标）后重试 |
| 安装报 `找不到 dist/main.js` | 客户端大版本改动，需更新 `patch_asar.py` |
| 安装报 `asar 命令执行失败` / 首次很慢 | `npx` 要联网下载 asar 包；可先 `npm install -g @electron/asar` |
| 主题不生效 | 确认已重启客户端；`python scripts\patch_asar.py verify` 看 `钩子=有` |
| 改了样式没反应 | 窗口内按 `Ctrl+R` 重载；仍无反应看主进程日志 `%APPDATA%\antigravity\logs\main.log` 里 `[ClaudeTheme]` 开头的行 |
| 还原后外观仍是主题 | 确认 `app.asar.bak` 是干净原版（`verify` 会提示）；必要时重装客户端 |

主进程日志位置：`C:\Users\<你>\AppData\Roaming\antigravity\logs\main.log`
