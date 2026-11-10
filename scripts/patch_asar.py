#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Antigravity 仿 Claude Code 主题 · asar 补丁工具

用法:
    python patch_asar.py install     # 注入钩子
    python patch_asar.py restore     # 还原官方原版
    python patch_asar.py verify      # 只做体检，不改动任何文件

可选参数:
    --resources DIR   直接指定 Antigravity 的 resources 目录
    --project DIR     指定本项目根目录（默认取脚本上一级）

相对旧版修复的问题:
  1. 旧版重新打包时丢掉了原版 asar 的 unpacked 标记，让 347 个本应留在
     app.asar.unpacked 里的文件（13MB）被塞进 app.asar，导致 app.asar 从
     4.79MB 膨胀到 18MB；这里会按原版布局自动还原 --unpack-dir。
  2. 旧版无论成功失败都返回 0，install.ps1 因此永远打印“部署完成”。这里
     任何一步失败都会返回非零退出码。
  3. 旧版不检查客户端是否在运行，运行中替换文件会装出半成品。这里先探测
     app.asar 能否写入，运行中直接拒绝。
  4. 旧版把安装路径硬编码成 C:\\Users\\andy_\\...，换台机器就废。这里自动
     定位，可用 --resources 覆盖。
  5. 新增安装后校验：重新解析 asar、核对条目数/unpacked 布局、确认 main.js
     含钩子并能通过 node 语法检查。
  6. 钩子本身改为只在 dom-ready 注入一次，并跳过 webview / devtools 等
     非界面 webContents，避免把汉化样式注入到内嵌浏览器页面上。
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

# Windows 控制台默认代码页是 GBK，中文容易乱码；尽量把输出切成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

HOOK_START = "// --- ANTIGRAVITY CLAUDE CODE THEME & I18N HOOK START ---"
HOOK_END = "// --- ANTIGRAVITY CLAUDE CODE THEME & I18N HOOK END ---"
HOOK_MARKER = "ANTIGRAVITY CLAUDE CODE THEME & I18N HOOK"
MAIN_ENTRY = "/dist/main.js"
BACKUP_NAME = "app.asar.bak"
ASAR_NAME = "app.asar"
UNPACKED_NAME = "app.asar.unpacked"

# ---------------------------------------------------------------------------
# 注入到 main.js 末尾的钩子
# 说明：用 __THEME_ROOT__ 占位，安装时替换成真实项目路径（避免写死盘符）。
#       注入渲染进程的脚本用字符串拼接而不是模板字符串，防止词典里出现
#       反引号或 ${} 时把代码撑破。
# ---------------------------------------------------------------------------
MAIN_HOOK_CODE = r"""
// --- ANTIGRAVITY CLAUDE CODE THEME & I18N HOOK START ---
try {
  const _fs = require('fs');
  const _pathUtil = require('path');
  const _THEME_ROOT = __THEME_ROOT__;
  const _cssPath = _pathUtil.join(_THEME_ROOT, 'theme', 'claude-theme.css');
  const _dictPath = _pathUtil.join(_THEME_ROOT, 'locales', 'zh-CN.json');
  const _jsPath = _pathUtil.join(_THEME_ROOT, 'scripts', 'injector.js');
  // 只处理真实界面窗口；webview（内置浏览器）、devtools 等一律跳过，
  // 否则浏览网页时网页正文会被汉化、网页样式会被改写。
  const _SKIP_TYPES = new Set(['webview', 'devtools', 'backgroundPage', 'offscreen', 'remote']);
  const _insertedCss = new WeakMap();
  const _tag = '[ClaudeTheme]';

  const _readText = (p) => {
    try { return _fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''); } catch (e) { return null; }
  };

  const _apply = async (contents) => {
    try {
      if (!contents || contents.isDestroyed()) return;
      // 1) 样式：先移除上一次插入的那份，避免反复重载叠加
      const oldKey = _insertedCss.get(contents);
      if (oldKey) {
        try { await contents.removeInsertedCSS(oldKey); } catch (e) {}
        _insertedCss.delete(contents);
      }
      const css = _readText(_cssPath);
      if (css) {
        const key = await contents.insertCSS(css);
        _insertedCss.set(contents, key);
      }
      // 2) 汉化引擎 + 词典（每次都重新读文件，改完 Ctrl+R 即生效）
      const script = _readText(_jsPath);
      if (script) {
        const dictRaw = _readText(_dictPath) || '{}';
        let dict;
        try { dict = JSON.parse(dictRaw); } catch (e) { dict = { exact: {}, partial: [] }; console.warn(_tag, '词典 JSON 解析失败，已跳过汉化:', e && e.message); }
        const code = '(function(){try{window.__CLAUDE_TRANSLATIONS__=' + JSON.stringify(dict) + ';\n' + script + '\n}catch(e){console.warn("' + _tag + ' eval:",e);}})();';
        await contents.executeJavaScript(code, true);
      }
    } catch (err) {
      console.warn(_tag, '注入失败:', err && err.message);
    }
  };

  electron_1.app.on('web-contents-created', (_event, _contents) => {
    try {
      if (!_contents || _SKIP_TYPES.has(_contents.getType())) return;
      // 只在 dom-ready 注入一次：此时 body 已就绪，样式不会闪
      _contents.on('dom-ready', () => { void _apply(_contents); });
    } catch (e) {
      console.warn(_tag, '钩子挂载失败:', e && e.message);
    }
  });
  console.log(_tag, '主进程钩子已挂载，主题目录:', _THEME_ROOT);
} catch (e) {
  console.warn('[ClaudeTheme] 主进程钩子初始化失败:', e && e.message);
}
// --- ANTIGRAVITY CLAUDE CODE THEME & I18N HOOK END ---
"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def log(msg=""):
    print(msg, flush=True)


def fail(msg, code=1):
    print("[ERROR] " + msg, file=sys.stderr, flush=True)
    return code


def project_root(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parent.parent


def find_resources(explicit=None):
    """定位 Antigravity 的 resources 目录。"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if (p / ASAR_NAME).exists() else None

    env = os.environ.get("ANTIGRAVITY_RESOURCES")
    candidates = []
    if env:
        candidates.append(Path(env))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    programs = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    for base in (local / "Programs", Path(os.environ.get("PROGRAMFILES", "")), systems_program_files()):
        for name in ("antigravity", "Antigravity"):
            candidates.append(base / name / "resources")
    for c in candidates:
        try:
            if c and (c / ASAR_NAME).exists():
                return c.resolve()
        except OSError:
            continue
    return None


def systems_program_files():
    p = os.environ.get("PROGRAMFILES(X86)")
    return Path(p) if p else Path("C:/Program Files (x86)")


def is_app_running(asar_path):
    """判断客户端是否在运行：最可靠的方式是探测 app.asar 能否独占写入。"""
    try:
        with open(asar_path, "r+b"):
            pass
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def running_hint():
    return (
        "Antigravity 客户端正在运行，app.asar 被占用。\n"
        "        请先完全退出客户端（右下角托盘图标也要右键退出），再重新执行。"
    )


# ---------------------------------------------------------------------------
# 极简 asar 读取（只用于校验，不依赖 npx）
# ---------------------------------------------------------------------------
def read_asar(path):
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < 16:
        raise ValueError("文件过小，不是合法 asar")
    p0, p1, p2, p3 = struct.unpack("<4I", blob[:16])
    for start, length in ((16, p3), (16, p2), (12, p2), (8, p1)):
        if length <= 0 or start + length > len(blob):
            continue
        try:
            header = json.loads(blob[start:start + length].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(header, dict) and "files" in header:
            base = ((start + length) + 3) // 4 * 4
            return blob, header, base
    raise ValueError("无法解析 asar 头部")


def walk_paths(node, prefix=""):
    for name, child in (node.get("files") or {}).items():
        p = prefix + "/" + name
        if "files" in child:
            yield from walk_paths(child, p)
        else:
            yield p, child


def entry_of(header, name):
    node = header
    for part in name.strip("/").split("/"):
        node = node["files"][part]
    return node


def read_entry(path, header, base, name):
    node = entry_of(header, name)
    if "offset" not in node:
        raise ValueError("条目是 unpacked，不在 asar 内: " + name)
    start = base + int(node["offset"])
    return read_entry_buf(path, start, int(node["size"]))


def read_entry_buf(path, start, size):
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(size)


def asar_summary(path):
    blob, header, base = read_asar(path)
    entries = list(walk_paths(header))
    unpacked = [p for p, e in entries if e.get("unpacked")]
    main = entry_of(header, MAIN_ENTRY)
    main_size = int(main.get("size", 0))
    hook = False
    if "offset" in main:
        data = read_entry_buf(path, base + int(main["offset"]), main_size)
        hook = HOOK_MARKER.encode() in data
    return {
        "path": str(path),
        "size": os.path.getsize(path),
        "entries": len(entries),
        "unpacked": unpacked,
        "main_size": main_size,
        "has_hook": hook,
    }


# ---------------------------------------------------------------------------
# 调用 npx asar
# ---------------------------------------------------------------------------
def find_npx():
    for name in ("npx.cmd", "npx", "npx.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def run_asar(args, cwd=None):
    npx = find_npx()
    if not npx:
        raise RuntimeError(
            "找不到 npx。请先安装 Node.js（https://nodejs.org），"
            "或执行 npm install -g @electron/asar 后重试。"
        )
    cmd = [npx, "--yes", "asar"] + list(args)
    # Windows 下 .cmd 必须经由 cmd.exe 执行
    use_shell = npx.lower().endswith((".cmd", ".bat"))
    completed = subprocess.run(
        subprocess.list2cmdline(cmd) if use_shell else cmd,
        shell=use_shell,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "asar 命令执行失败（exit=%s）:\n%s\n"
            "提示：首次执行需要联网下载 asar 包；若无法联网，"
            "可先 `npm install -g @electron/asar` 再重试。"
            % (completed.returncode, (completed.stdout or "").strip()[-2000:])
        )
    return completed.stdout or ""


def compute_unpack_specs(header):
    """根据原版 asar 的 unpacked 布局，算出 asar pack 需要的 --unpack-dir 参数。

    目标是让重打包后的 app.asar 与原版保持同样的 unpacked 分布，避免把
    node_modules/chrome-devtools-mcp 这 13MB 原生可执行依赖塞回归档。
    """
    all_paths = dict(walk_paths(header))
    unpacked = {p for p, e in all_paths.items() if e.get("unpacked")}
    if not unpacked:
        return []
    specs = []
    remaining = set(unpacked)
    # 从浅到深找“整个目录都该解包”的目录
    candidates = set()
    for p in unpacked:
        parts = p.strip("/").split("/")
        for i in range(1, len(parts)):
            candidates.add("/".join(parts[:i]))
    for d in sorted(candidates, key=lambda x: (x.count("/"), x)):
        prefix = "/" + d + "/"
        under = {p for p in all_paths if p.startswith(prefix)}
        if under and under <= unpacked and (under & remaining):
            specs.append(("--unpack-dir", d))
            remaining -= under
    for p in sorted(remaining):
        specs.append(("--unpack", p.strip("/")))
    return specs


def patch_main_js(original, project_dir):
    """把钩子写进 main.js 文本：已有则替换，没有则追加。"""
    hook = MAIN_HOOK_CODE.replace("__THEME_ROOT__", json.dumps(str(project_dir)))
    if HOOK_START in original and HOOK_END in original:
        start = original.index(HOOK_START)
        end = original.index(HOOK_END) + len(HOOK_END)
        return original[:start] + hook.strip() + original[end:]
    return original.rstrip() + "\n\n" + hook.strip() + "\n"


def node_syntax_check(text, workdir):
    """用 node --check 校验补丁后的 main.js 语法（找不到 node 就跳过）。"""
    node = shutil.which("node")
    if not node:
        log("  [跳过] 未找到 node，跳过语法校验")
        return True
    tmp = Path(workdir) / "main.check.js"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        r = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return False
        return True
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


_WORK_DIR = None


def work_dir(project):
    """项目内的临时工作目录。

    故意不用 tempfile.mkdtemp()：Python 3.13+ 在 Windows 上会给它加一层只有
    创建者可访问的 ACL，子进程（npx asar）常常直接 EPERM。用普通 mkdir 继承
    目录权限最稳，也避免写入 %TEMP% 时的权限问题。
    """
    global _WORK_DIR
    if _WORK_DIR is None:
        root = project / ".build"
        root.mkdir(parents=True, exist_ok=True)
        d = root / ("asar-work-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8]))
        d.mkdir(exist_ok=True)
        _WORK_DIR = d
    return _WORK_DIR


# ---------------------------------------------------------------------------
# 安装 / 还原 / 体检
# ---------------------------------------------------------------------------
def cmd_install(resources, project):
    asar = resources / ASAR_NAME
    backup = resources / BACKUP_NAME
    if not asar.exists():
        return fail("找不到目标文件: %s" % asar)

    if is_app_running(asar):
        return fail(running_hint())

    log("=== 1/6 备份官方原版 ===")
    if not backup.exists():
        shutil.copy2(asar, backup)
        log("  已备份 -> %s" % backup)
    else:
        log("  备份已存在 -> %s" % backup)
    try:
        old = asar_summary(backup)
    except Exception as exc:  # noqa: BLE001
        return fail("备份文件不可解析，已中止：%s" % exc)
    if old["has_hook"]:
        log("  [警告] 备份里已经含有钩子，说明它不是纯净原版；还原功能将不可靠。")
    log("  原版: %.2f MB / %d 个条目 / %d 个 unpacked"
        % (old["size"] / 1048576, old["entries"], len(old["unpacked"])))
    # asar extract 会从同级的 app.asar.unpacked 里读取那些标记为 unpacked 的
    # 文件；目录缺失会导致解包内容不完整，必须先拦住。
    if old["unpacked"] and not (resources / UNPACKED_NAME).exists():
        return fail(
            "缺少 %s 目录，无法完整解包（有 %d 个文件放在里面）。\n"
            "        请重新安装一次 Antigravity 客户端补齐该目录后再试。"
            % (resources / UNPACKED_NAME, len(old["unpacked"]))
        )

    # 工作目录放在项目内的 .build 下：不受 %TEMP% 权限限制，退出时一定会清理。
    tmpdir = work_dir(project)
    try:
        log("=== 2/6 解包 app.asar ===")
        extract_dir = tmpdir / "extract"
        run_asar(["extract", str(asar), str(extract_dir)])
        log("  完成")

        log("=== 3/6 注入 main.js 钩子 ===")
        main_path = extract_dir / "dist" / "main.js"
        if not main_path.exists():
            return fail("解包后找不到 dist/main.js，Antigravity 版本可能已变化。")
        original_js = main_path.read_text(encoding="utf-8", errors="replace")
        patched_js = patch_main_js(original_js, project)
        if HOOK_MARKER not in patched_js:
            return fail("钩子写入失败（产物中没有标记）")
        log("  已%s钩子，main.js: %d -> %d 字节"
            % ("刷新" if HOOK_MARKER in original_js else "写入",
               len(original_js), len(patched_js)))
        if not node_syntax_check(patched_js, tmpdir):
            return fail("打补丁后的 main.js 未通过 node 语法检查，已中止（不会改动安装目录）")
        main_path.write_text(patched_js, encoding="utf-8", newline="\n")

        log("=== 4/6 重新打包（保持原版 unpacked 布局）===")
        specs = compute_unpack_specs(json.loads(json.dumps(read_asar(asar)[1])))
        pack_args = ["pack", str(extract_dir), str(tmpdir / "app.asar")]
        for flag, value in specs:
            pack_args += [flag, value]
            log("  %s %s" % (flag, value))
        run_asar(pack_args)
        new_asar = tmpdir / "app.asar"
        if not new_asar.exists():
            return fail("打包产物不存在")
        log("  新 asar: %.2f MB" % (new_asar.stat().st_size / 1048576))

        log("=== 5/6 校验产物 ===")
        new = asar_summary(new_asar)
        problems = []
        if new["entries"] != old["entries"]:
            problems.append("条目数不一致: 原版 %d / 新版 %d" % (old["entries"], new["entries"]))
        if not new["has_hook"]:
            problems.append("新版 asar 里没有钩子标记")
        if len(new["unpacked"]) != len(old["unpacked"]):
            problems.append("unpacked 文件数不一致: 原版 %d / 新版 %d"
                            % (len(old["unpacked"]), len(new["unpacked"])))
        if problems:
            for p in problems:
                log("  [问题] " + p)
            return fail("产物校验未通过，已中止（安装目录未被改动）")
        log("  条目数 %d、unpacked %d，均与原版一致 ✓"
            % (new["entries"], len(new["unpacked"])))

        log("=== 6/6 替换安装目录中的 app.asar ===")
        staging = resources / (ASAR_NAME + ".new")
        shutil.copy2(new_asar, staging)
        os.replace(staging, asar)
        # 同步 unpacked 目录（只增不删，保证 header 指向的文件都在盘上）
        new_unpacked = tmpdir / "app.asar.unpacked"
        if new_unpacked.exists():
            shutil.copytree(new_unpacked, resources / UNPACKED_NAME, dirs_exist_ok=True)
        log("  完成")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    final = asar_summary(asar)
    log("")
    log("=== 安装成功 ===")
    log("  app.asar : %.2f MB（原版 %.2f MB）" % (final["size"] / 1048576, old["size"] / 1048576))
    log("  钩子状态 : %s" % ("已注入" if final["has_hook"] else "未注入"))
    log("  主题目录 : %s" % project)
    log("")
    log("接下来：完全退出并重新打开 Antigravity 客户端即可生效。")
    log("之后修改 CSS / 词典 / 注入脚本 无需重新安装，窗口内 Ctrl+R 即可热更新。")
    return 0


def cmd_restore(resources):
    asar = resources / ASAR_NAME
    backup = resources / BACKUP_NAME
    if not backup.exists():
        return fail("找不到备份文件 %s，无法还原。\n"
                    "        如已丢失备份，请重新安装一次 Antigravity 客户端。" % backup)
    if not asar.exists():
        return fail("找不到目标文件: %s" % asar)
    if is_app_running(asar):
        return fail(running_hint())
    try:
        bk = asar_summary(backup)
    except Exception as exc:  # noqa: BLE001
        return fail("备份文件损坏，无法还原：%s" % exc)
    if bk["has_hook"]:
        return fail("备份文件里含有主题钩子，它不是官方原版，还原后仍然是打过补丁的状态。\n"
                    "        请重新安装 Antigravity 客户端以获得干净的原版 app.asar。")

    staging = resources / (ASAR_NAME + ".restore")
    shutil.copy2(backup, staging)
    os.replace(staging, asar)
    after = asar_summary(asar)
    if after["has_hook"]:
        return fail("还原后仍检测到钩子，请重新安装客户端。")
    log("已还原官方原版 app.asar（%.2f MB / %d 个条目）" % (after["size"] / 1048576, after["entries"]))
    log("提示：app.asar.unpacked 里可能有主题安装时多出来的文件，它们不会被加载，可忽略。")
    return 0


def cmd_verify(resources):
    asar = resources / ASAR_NAME
    backup = resources / BACKUP_NAME
    ok = True
    log("resources 目录: %s" % resources)
    if not asar.exists():
        return fail("找不到 app.asar")
    if is_app_running(asar):
        log("客户端状态  : 运行中（app.asar 被占用）")
    else:
        log("客户端状态  : 未运行")
    for label, path in (("当前 app.asar", asar), ("备份 app.asar.bak", backup)):
        if not path.exists():
            log("%s : 不存在" % label)
            if label.startswith("备份"):
                ok = False
            continue
        try:
            s = asar_summary(path)
        except Exception as exc:  # noqa: BLE001
            log("%s : 解析失败 %s" % (label, exc))
            ok = False
            continue
        if path == asar and not s["has_hook"]:
            ok = False
        log("%s : %.2f MB / %d 条目 / %d unpacked / 钩子=%s"
            % (label, s["size"] / 1048576, s["entries"], len(s["unpacked"]),
               "有" if s["has_hook"] else "无"))
    if backup.exists() and asar.exists():
        try:
            b = asar_summary(backup)
            a = asar_summary(asar)
            if b["has_hook"] and a["has_hook"]:
                log("警告: 备份与当前文件都含钩子，还原不可靠。")
        except Exception:  # noqa: BLE001
            pass
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(add_help=True, description="Antigravity 主题 asar 补丁工具")
    parser.add_argument("action", nargs="?", default="install",
                        choices=["install", "restore", "verify"])
    parser.add_argument("--resources", default=None)
    parser.add_argument("--project", default=None)
    args = parser.parse_args()

    resources = find_resources(args.resources)
    if not resources:
        return fail(
            "没有找到 Antigravity 安装目录。\n"
            "        常见位置：%LOCALAPPDATA%\\Programs\\antigravity\\resources\n"
            "        也可以用 --resources 手动指定，例如：\n"
            "        python patch_asar.py %s --resources \"D:\\Antigravity\\resources\""
            % args.action
        )
    project = project_root(args.project)

    try:
        if args.action == "install":
            return cmd_install(resources, project)
        if args.action == "restore":
            return cmd_restore(resources)
        return cmd_verify(resources)
    except Exception as exc:  # noqa: BLE001
        return fail("%s 失败：%s" % (args.action, exc))


if __name__ == "__main__":
    sys.exit(main())
