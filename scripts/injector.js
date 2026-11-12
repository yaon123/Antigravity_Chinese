/**
 * Claude Theme for Antigravity —— 渲染进程界面汉化引擎
 * ---------------------------------------------------------------
 * 由主进程钩子在 dom-ready / did-finish-load 时执行注入。
 * 纯 IIFE，无外部依赖，不产生 import/export。
 *
 * 设计要点（相对旧版修复）：
 *  1. 幂等守卫：window.__CLAUDE_I18N_ACTIVE__，重复注入直接返回，避免 4 个 Observer。
 *  2. INPUT/TEXTAREA 不再整体跳过：跳过其内部文本遍历，但照常翻译
 *     placeholder / data-placeholder / title / aria-label / alt 等属性。
 *  3. 用 TreeWalker 遍历文本节点；characterData 变化只处理该文本节点，不整树重走。
 *  4. 聊天正文保护：
 *       - 硬保护（完全不碰）：pre/code/kbd、.markdown、whitespace-pre-wrap、
 *         select-text、hljs、monaco、xterm、CodeMirror、终端、diff/代码 testid 等。
 *       - 软保护（整段精确匹配 + 锚定 patterns 可翻，禁用 partial 子串替换）：
 *         [data-message-id]、[data-testid*="message"]、对话/转写容器等。
 *  5. 新增 patterns 支持：{"patterns":[{"re":"^Worked for (.+)$","to":"已工作 $1"}]}。
 *  6. 覆盖 document.title、placeholder、title、aria-label、aria-description、alt。
 *  7. 纯数据串（时间 9d/1mo、版本号 2.29.0、模型名、邮箱、URL、纯数字/标点、
 *     单字符快捷键）永不翻译，避免误伤。
 */
(function () {
  'use strict';

  var LOG_PREFIX = '[ClaudeTheme]';

  // ------------------------------------------------------------------
  // 0. 幂等守卫（主进程会注入多次：dom-ready + did-finish-load）
  // ------------------------------------------------------------------
  if (window.__CLAUDE_I18N_ACTIVE__) {
    console.log(LOG_PREFIX + ' i18n 引擎已激活，跳过重复注入。');
    return;
  }
  window.__CLAUDE_I18N_ACTIVE__ = true;

  var STATS = { text: 0, attr: 0, title: 0, dictExact: 0, dictPartial: 0, dictPatterns: 0 };
  window.__CLAUDE_I18N_STATS__ = STATS;

  // ------------------------------------------------------------------
  // 1. 读取注入的字典
  // ------------------------------------------------------------------
  var rawDict = window.__CLAUDE_TRANSLATIONS__;
  var dict = (rawDict && typeof rawDict === 'object') ? rawDict : {};
  var exact = (dict.exact && typeof dict.exact === 'object') ? dict.exact : {};
  var exactLower = {};
  for (var ek in exact) {
    if (Object.prototype.hasOwnProperty.call(exact, ek)) {
      exactLower[ek.toLowerCase()] = exact[ek];
    }
  }

  var partialList = [];
  if (Object.prototype.toString.call(dict.partial) === '[object Array]') {
    partialList = dict.partial.filter(function (item) {
      return item && typeof item.from === 'string' && item.from.length > 0 && typeof item.to === 'string';
    });
  }

  var patterns = [];
  if (Object.prototype.toString.call(dict.patterns) === '[object Array]') {
    dict.patterns.forEach(function (item) {
      if (!item || typeof item.re !== 'string' || typeof item.to !== 'string') return;
      try {
        var flags = (typeof item.flags === 'string' ? item.flags : '').replace(/[gy]/g, '');
        patterns.push({ re: new RegExp(item.re, flags), to: item.to });
      } catch (err) {
        console.warn(LOG_PREFIX + ' 非法 pattern:', item.re, err);
      }
    });
  }

  STATS.dictExact = Object.keys(exact).length;
  STATS.dictPartial = partialList.length;
  STATS.dictPatterns = patterns.length;

  var hasOwn = Object.prototype.hasOwnProperty;

  // ------------------------------------------------------------------
  // 2. 规则常量
  // ------------------------------------------------------------------

  // 含中文/日文/韩文 => 认为已是目标语言，直接跳过（天然幂等，防止二次替换）
  var CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]/;

  // 拆出前导/尾部空白，保留排版
  var WS_SPLIT_RE = /^(\s*)([\s\S]*?)(\s*)$/;

  // 这些标签内部不遍历文本（INPUT/TEXTAREA 的属性仍会被翻译）
  var IGNORE_TAGS = {
    SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TITLE: 1, TEMPLATE: 1, HEAD: 1,
    META: 1, LINK: 1, SVG: 1, PATH: 1, CANVAS: 1, VIDEO: 1, AUDIO: 1,
    IFRAME: 1, OBJECT: 1, EMBED: 1, TEXTAREA: 1, INPUT: 1
  };

  // 硬保护：仅针对纯代码文本行、终端行与编辑器画布 —— 文本节点一律不动
  // 注意：不再把整个 diff 或 code 卡片容器作为硬保护，避免其头部的复制、执行等按钮被误杀
  var HARD_SELECTOR = [
    'pre', 'code', 'kbd', 'samp',
    '[class*="hljs"]',
    '.monaco-editor .view-lines',
    '.xterm-rows',
    '[class*="CodeMirror-lines"]',
    '[data-claude-i18n-ignore]'
  ].join(',');

  // 只在「非弹窗/设置界面/非外围导航」里才当作正文保护的通用类
  var SOFT_TEXT_ONLY_SELECTOR = '[class*="whitespace-pre-wrap"], [class*="select-text"]';

  // 弹窗 / 设置面板 / 侧栏 / 菜单内部的文字属于界面骨架，必须翻译
  var DIALOG_SELECTOR = [
    '.settings-modal-container', '.agy-dialog', '[data-testid="settings-sidebar"]',
    '[data-testid*="settings"]', '[role="dialog"]', '[role="menu"]', '[role="listbox"]',
    '[role="combobox"]', '.agy-menu', '.agy-overlay', '[class*="popover"]', '[class*="dropdown"]',
    '[class*="sidebar"]', '[class*="toolbar"]', '[class*="header"]', '[class*="footer"]',
    'nav', 'aside', 'header', 'footer', 'button', '[role="button"]'
  ].join(',');

  function isHardProtected(el) {
    if (matches(el, HARD_SELECTOR)) return true;
    // 通用 pre-wrap / select-text 类：仅在没有处于弹窗/设置面板内时保护
    if (matches(el, SOFT_TEXT_ONLY_SELECTOR) && !matches(el, DIALOG_SELECTOR)) return true;
    return false;
  }

  // 软保护：对话 / 消息容器 —— 允许「整段精确匹配」与锚定 patterns，
  // 但禁止 partial 子串替换，避免把 Agent 输出 / 用户消息改花。
  var SOFT_SELECTOR = [
    '[data-message-id]',
    '[data-testid*="message"]',
    '[data-testid*="conversation"]',
    '[data-testid*="transcript"]',
    '[role="log"]'
  ].join(',');

  // 属性翻译时跳过代码/正文区域（避免翻译 markdown 链接 title、代码块 aria-label）
  var ATTR_SKIP_SELECTOR = [
    'pre', 'code', '.markdown', '[class*="markdown"]',
    '[class*="whitespace-pre-wrap"]', '[class*="select-text"]',
    '[class*="monaco"]', '[class*="xterm"]', '[class*="hljs"]',
    '[data-testid*="diff"]', '[data-testid*="code"]'
  ].join(',');

  // 需要翻译的属性（含 contenteditable 占位符 data-placeholder）
  var ATTR_NAMES = ['placeholder', 'data-placeholder', 'title', 'aria-label', 'aria-description', 'aria-placeholder', 'alt'];
  var ATTR_SELECTOR = [
    '[placeholder]', '[data-placeholder]', '[title]', '[aria-label]',
    '[aria-description]', '[aria-placeholder]', '[alt]',
    'input[type="button"]', 'input[type="submit"]', 'input[type="reset"]'
  ].join(',');

  var OBSERVED_ATTRIBUTES = ['placeholder', 'data-placeholder', 'title', 'aria-label', 'aria-description', 'aria-placeholder', 'alt', 'value'];

  // 「看起来是数据」的字符串：永不翻译（精确匹配命中字典时除外，见顺序）
  var DATA_RES = [
    // 纯数字 / 标点 / 符号（含 + - % , . ( ) 等）
    /^[\s\d.,;:+\-–—%/\\()\[\]{}<>|*#@!?~^&="'`·•、。，；：（）【】]+$/,
    // 相对时间 / 版本号：9d、1mo、2.29.0、3d、1.4%
    /^\d+(?:\.\d+)*(?:\s*(?:s|m|h|d|mo|y|sec|min|hr|hour|day|week|month|year))?$/i,
    // 9m ago / 2 days ago
    /^\d+(?:\.\d+)?\s*(?:s|m|h|d|mo|y|sec|min|hr|hour|day|week|month|year)s?\s+ago$/i,
    /^(?:just\s+now|a\s+moment\s+ago)$/i,
    // URL / 邮箱
    /^(?:https?:\/\/|mailto:|www\.)/i,
    /^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$/,
    // 模型 / 品牌名（Gemini、Flash、Turbo、Antigravity、Google…）不翻译
    /^(?:gemini|gpt|claude|opus|sonnet|flash|turbo|ultra|nano|veo|imagen|antigravity|google|mendel)\b/i,
    // 路径 / 插件 id / kebab-case 标识符
    /^[\w.-]+\/[\w./-]+$/,
    /^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$/
  ];

  function looksLikeData(core) {
    for (var i = 0; i < DATA_RES.length; i++) {
      if (DATA_RES[i].test(core)) return true;
    }
    return false;
  }

  // partial 子串替换的安全阈值：只对短标签生效，长句交给 exact / patterns
  function canApplyPartial(core) {
    if (core.length > 60) return false;
    if (core.indexOf('\n') !== -1 || core.indexOf('\r') !== -1) return false;
    if (core.split(/\s+/).length > 8) return false;
    return true;
  }

  // 对话/消息容器（软保护）里 patterns 的闸门：
  // 放行步骤摘要与状态文案（如 "Worked for 5m"、"Thought for: 12s"、"3 files changed" 等），
  // 仅拦截多行换行长文，不再根据小数点/冒号/括号一票否决
  function canApplyPatternsInSoft(core) {
    if (core.length > 80) return false;
    if (core.indexOf('\n') !== -1 || core.indexOf('\r') !== -1) return false;
    return true;
  }

  function matches(el, selector) {
    if (!el || el.nodeType !== 1) return false;
    try {
      if (typeof el.closest === 'function') return !!el.closest(selector);
      if (typeof el.matches === 'function') return el.matches(selector);
    } catch (err) { /* ignore invalid selector in odd contexts */ }
    return false;
  }

  // ------------------------------------------------------------------
  // 3. 核心翻译：exact -> patterns -> partial
  // ------------------------------------------------------------------
  function translateString(input, opts) {
    if (typeof input !== 'string' || input === '') return input;

    var m = WS_SPLIT_RE.exec(input);
    if (!m) return input;
    var lead = m[1];
    var core = m[2];
    var trail = m[3];
    if (!core) return input;

    // 3.1 整段精确匹配（最高优先级）
    if (hasOwn.call(exact, core)) {
      var hit = exact[core];
      if (typeof hit === 'string' && hit !== core) return lead + hit + trail;
    }

    // 3.1b 大小写模糊精确匹配 (如 "New conversation" -> "新建对话")
    var lowerCore = core.toLowerCase();
    if (hasOwn.call(exactLower, lowerCore)) {
      var hitLower = exactLower[lowerCore];
      if (typeof hitLower === 'string' && hitLower !== core) return lead + hitLower + trail;
    }

    // 3.1c 尾部冒号自动匹配 (如 "Model:" -> "模型：")
    if (core.endsWith(':') || core.endsWith('：')) {
      var withoutColon = core.slice(0, -1).trim();
      if (hasOwn.call(exact, withoutColon)) {
        return lead + exact[withoutColon] + '：' + trail;
      }
      var lowerWithout = withoutColon.toLowerCase();
      if (hasOwn.call(exactLower, lowerWithout)) {
        return lead + exactLower[lowerWithout] + '：' + trail;
      }
    }

    // 3.2 已含中文 => 跳过（幂等）
    if (CJK_RE.test(core)) return input;

    // 3.3 单字符（键盘快捷键提示 K/P/N/U/A/J/F/R/0/[ 等）与纯数据不翻译
    if (core.length <= 1) return input;
    if (looksLikeData(core)) return input;

    var allowPatterns = !opts || opts.allowPatterns !== false;
    var allowPartial = !opts || opts.allowPartial !== false;
    var soft = !!(opts && opts.soft);
    var out = core;

    // 3.4 动态文案 patterns（正则 + 捕获组）
    //     软保护（对话容器）内只放行极短步骤摘要，防止 Agent 长句被改写
    if (allowPatterns &&
        core.length <= 120 &&
        core.indexOf('\n') === -1 &&
        core.indexOf('\r') === -1 &&
        (!soft || canApplyPatternsInSoft(core))) {
      for (var i = 0; i < patterns.length; i++) {
        var p = patterns[i];
        if (p.re.test(out)) {
          var next = out.replace(p.re, p.to);
          if (next !== out) out = next;
        }
      }
    }

    // 3.5 partial 子串替换（仅短标签 + 非对话正文）
    if (out === core && allowPartial && canApplyPartial(core)) {
      for (var j = 0; j < partialList.length; j++) {
        var item = partialList[j];
        if (out.indexOf(item.from) !== -1) {
          out = out.split(item.from).join(item.to);
        }
      }
    }

    if (out === core) return input;
    return lead + out + trail;
  }

  // ------------------------------------------------------------------
  // 4. 文本节点翻译
  // ------------------------------------------------------------------
  // 记录「我们写入过的值」，配合 MutationObserver 防止自触发死循环
  var written = (typeof WeakMap === 'function') ? new WeakMap() : null;

  function translateTextNode(node) {
    if (!node || node.nodeType !== 3) return;
    var current = node.nodeValue;
    if (!current || !/\S/.test(current)) return;

    var parent = node.parentNode;
    if (!parent) return;
    var el = parent.nodeType === 1 ? parent : parent.parentElement;
    if (!el) return;

    if (IGNORE_TAGS[String(el.nodeName).toUpperCase()]) return;
    if (el.isContentEditable) return;
    if (isHardProtected(el)) return;

    if (written && written.get(node) === current) return;

    var soft = matches(el, SOFT_SELECTOR);
    var translated = translateString(current, {
      allowPartial: !soft,
      allowPatterns: true,
      soft: soft
    });

    if (translated !== current) {
      if (written) written.set(node, translated);
      node.nodeValue = translated;
      STATS.text++;
    }
  }

  // TreeWalker 过滤：返回 REJECT 可直接剪掉整棵子树
  function treeFilter(node) {
    if (node.nodeType === 3) {
      return /\S/.test(node.nodeValue || '') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
    if (node.nodeType !== 1) return NodeFilter.FILTER_REJECT;
    if (IGNORE_TAGS[String(node.nodeName).toUpperCase()]) return NodeFilter.FILTER_REJECT;
    if (node.isContentEditable) return NodeFilter.FILTER_REJECT;
    if (isHardProtected(node)) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }

  function translateTextIn(root) {
    if (!root) return;
    if (root.nodeType === 3) { translateTextNode(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9) return;

    var walker;
    try {
      walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, treeFilter, false);
    } catch (err) {
      return;
    }
    var node = walker.nextNode();
    while (node) {
      if (node.nodeType === 3) translateTextNode(node);
      node = walker.nextNode();
    }
  }

  // ------------------------------------------------------------------
  // 5. 属性翻译（placeholder / title / aria-label / alt ...）
  // ------------------------------------------------------------------
  function translateAttr(el, name) {
    var value;
    try { value = el.getAttribute(name); } catch (err) { return; }
    if (!value || typeof value !== 'string' || !/\S/.test(value)) return;
    if (CJK_RE.test(value)) return; // 幂等：已是中文 / 含中文

    var translated = translateString(value, { allowPartial: true, allowPatterns: true });
    if (translated !== value) {
      try {
        el.setAttribute(name, translated);
        STATS.attr++;
      } catch (err) { /* read-only attr in rare cases */ }
    }
  }

  function translateElementAttrs(el) {
    if (!el || el.nodeType !== 1) return;
    if (matches(el, ATTR_SKIP_SELECTOR)) return;

    for (var i = 0; i < ATTR_NAMES.length; i++) translateAttr(el, ATTR_NAMES[i]);

    // <input type=button|submit|reset> 的 value 是可见文案
    if (String(el.nodeName).toUpperCase() === 'INPUT') {
      var type = String(el.getAttribute('type') || '').toLowerCase();
      if (type === 'button' || type === 'submit' || type === 'reset') translateAttr(el, 'value');
    }
  }

  function translateAttrsIn(root) {
    if (!root) return;
    if (root.nodeType === 1) translateElementAttrs(root);
    if (!root.querySelectorAll) return;

    var list;
    try { list = root.querySelectorAll(ATTR_SELECTOR); } catch (err) { return; }
    for (var i = 0; i < list.length; i++) translateElementAttrs(list[i]);
  }

  // ------------------------------------------------------------------
  // 6. document.title
  // ------------------------------------------------------------------
  function translateDocumentTitle() {
    var title = document.title;
    if (!title) return;
    var translated = translateString(title, { allowPartial: true, allowPatterns: true });
    if (translated !== title) {
      document.title = translated;
      STATS.title++;
    }
  }

  // ------------------------------------------------------------------
  // 7. 入口：整棵树扫描
  // ------------------------------------------------------------------
  function processElement(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.isConnected === false) return;
    translateElementAttrs(el);
    translateAttrsIn(el);
    translateTextIn(el);
  }

  function translateWholeRoot(root) {
    if (!root) return;
    translateAttrsIn(root);
    translateTextIn(root);
    translateDocumentTitle();
  }

  // ------------------------------------------------------------------
  // 8. MutationObserver：批量 + 只处理变化部分
  // ------------------------------------------------------------------
  var pending = [];
  var scheduled = false;

  function schedule(node) {
    if (!node) return;
    pending.push(node);
    // 极端情况下（一次插入上千节点）退化为整树重扫，防止内存膨胀
    if (pending.length > 3000) {
      pending = [document.body || document.documentElement];
    }
    if (scheduled) return;
    scheduled = true;
    window.setTimeout(flush, 20);
  }

  function flush() {
    scheduled = false;
    var batch = pending;
    pending = [];

    // title 可能随路由变化，每次刷新都顺带检查（开销极小）
    try { translateDocumentTitle(); } catch (err) { /* ignore */ }

    for (var i = 0; i < batch.length; i++) {
      var node = batch[i];
      if (!node) continue;
      try {
        if (node.nodeType === 3) {
          translateTextNode(node);
        } else if (node.nodeType === 1) {
          processElement(node);
        }
      } catch (err) {
        // 单个节点失败不影响其它节点
      }
    }
  }

  function handleMutations(mutations) {
    for (var i = 0; i < mutations.length; i++) {
      var mutation = mutations[i];
      if (mutation.type === 'childList') {
        var added = mutation.addedNodes;
        if (added && added.length) {
          for (var j = 0; j < added.length; j++) schedule(added[j]);
        }
      } else if (mutation.type === 'characterData') {
        var target = mutation.target;
        if (!target) continue;
        if (written && written.get(target) === target.nodeValue) continue;
        schedule(target); // 只处理这个文本节点，不整树重走
      } else if (mutation.type === 'attributes') {
        if (mutation.target) {
          try { translateElementAttrs(mutation.target); } catch (err) { /* ignore */ }
        }
      }
    }
  }

  var observer = new MutationObserver(handleMutations);
  var observerStarted = false;

  function startObserver() {
    if (observerStarted) return;
    var root = document.documentElement;
    if (!root) return;
    observerStarted = true;
    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: OBSERVED_ATTRIBUTES
    });
  }

  // ------------------------------------------------------------------
  // 9. 启动
  // ------------------------------------------------------------------
  function boot() {
    var root = document.body || document.documentElement;
    if (!root) {
      window.setTimeout(boot, 60);
      return;
    }
    translateWholeRoot(root);
    startObserver();
    console.log(
      LOG_PREFIX + ' i18n 引擎已启动：exact=' + STATS.dictExact +
      '，partial=' + STATS.dictPartial +
      '，patterns=' + STATS.dictPatterns
    );
  }

  try {
    if (document.documentElement) {
      boot();
    } else {
      document.addEventListener('DOMContentLoaded', boot);
    }
    // 页面 load 后补一次全量扫描（兜底懒加载 UI）
    window.addEventListener('load', function () {
      var root = document.body || document.documentElement;
      if (root) schedule(root);
    });
  } catch (err) {
    // 初始化失败时释放守卫，让主进程下一次注入可以重试
    window.__CLAUDE_I18N_ACTIVE__ = false;
    console.warn(LOG_PREFIX + ' i18n 初始化失败:', err);
  }

  // ------------------------------------------------------------------
  // 10. 调试接口（Lead 可在 DevTools 里调用）
  // ------------------------------------------------------------------
  window.__CLAUDE_I18N__ = {
    active: true,
    stats: STATS,
    exactCount: STATS.dictExact,
    patternCount: STATS.dictPatterns,
    partialCount: STATS.dictPartial,
    translate: function (text) { return translateString(text, {}); },
    rescan: function () { schedule(document.body || document.documentElement); }
  };
})();
