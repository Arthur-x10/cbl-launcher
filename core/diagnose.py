"""崩溃 / 日志诊断规则库（纯函数，无 Qt、无网络、不读配置）。

用法：
    from core import diagnose

    findings = diagnose.analyze_file(log_path)      # 或者 analyze(text)
    for f in findings:
        print(f.severity, f.title)
        print(f.detail)      # 命中的原始行，最多 5 行
        print(f.hint)        # 具体到点哪里 / 改什么值
    print(diagnose.summary(findings))

设计原则：宁可少报，也不要误报。Minecraft 的正常日志里塞满了看起来像报错却没意义的行，
例如 mixin 的
    [mixin/]: Error loading class: xaero/common/patreon/Patreon (java.lang.ClassNotFoundException: ...)
每次启动都有几百条；1.7.10 的 Forge 还会在正常启动时打印一份
    ---- Minecraft Crash Report ---- / THIS IS NOT A ERROR
所以规则锚定完整措辞，不用裸关键词；有歧义的规则配 skip 排除良性上下文。
"""

from __future__ import annotations

import gzip
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

# 单次最多扫这么多行（取日志尾部）——debug.log 动辄几十万行，全量正则太慢。
MAX_LINES = 60000
# detail 里最多留几行证据、每行截多长。
DETAIL_MAX_LINES = 5
DETAIL_LINE_CHARS = 300


@dataclass
class Finding:
    """一条诊断结论。severity: fatal / error / warn / info。"""

    severity: str
    title: str
    detail: str
    hint: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "hint": self.hint,
        }


SEVERITY_ORDER = {"fatal": 0, "error": 1, "warn": 2, "info": 3}
SEVERITY_LABEL = {"fatal": "致命", "error": "错误", "warn": "警告", "info": "提示"}


# ────────────────────────── 规则定义 ──────────────────────────


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    severity: str
    pattern: re.Pattern
    title: str = ""
    hint: str = ""
    skip: tuple = ()                       # 命中这些正则的行直接忽略（良性上下文）
    prev_skip: tuple = ()                  # 上一两行命中这些正则时也忽略（栈顶是良性上下文）
    item_re: tuple = ()                    # 从命中行/后续行里抓关键项（mod id、jar 名）
    context_span: int = 0                  # 命中后往下看多少行找证据
    max_hits: int = 1                      # 同一规则最多收几条命中行
    title_fn: Optional[Callable] = None
    hint_fn: Optional[Callable] = None


_CLASS_VERSION_RE = re.compile(
    r"UnsupportedClassVersionError"
    r"|has been compiled by a more recent version of the Java Runtime"
    r"|class file version\s+(\d+)",
    re.IGNORECASE,
)

_JAVA_FOR_MAJOR = {
    45: 1, 46: 2, 47: 3, 48: 4, 49: 5, 50: 6, 51: 7, 52: 8,
    53: 9, 54: 10, 55: 11, 56: 12, 57: 13, 58: 14, 59: 15, 60: 16,
    61: 17, 62: 18, 63: 19, 64: 20, 65: 21, 66: 22, 67: 23, 68: 24,
    69: 25, 70: 26,
}


def _java_required(hits: Sequence) -> int:
    for _idx, line in hits:
        for match in _CLASS_VERSION_RE.finditer(line):
            raw = match.group(1)
            if not raw:
                continue
            try:
                major = int(raw)
            except ValueError:
                continue
            if major in _JAVA_FOR_MAJOR:
                return _JAVA_FOR_MAJOR[major]
            if major >= 45:
                return max(major - 44, 1)
    return 0


def _class_version_title(hits, items) -> str:
    java = _java_required(hits)
    if java:
        return "Java 版本过低（日志里的类要求 Java " + str(java) + "）"
    return "Java 版本过低（日志里的类编译自更高的 Java）"


def _class_version_hint(hits, items) -> str:
    java = _java_required(hits)
    target = ("Java " + str(java)) if java else "日志里那个 class file 版本对应的 Java"
    return ("把该实例的 Java 换成 " + target + "：设置 → 实例 → Java 路径"
            "（没装就去「Java 管理」下载 x64 版，换完直接启动，不用重装游戏）。"
            "对照：class file version 52 = Java 8，61 = Java 17，65 = Java 21。")


def _missing_deps_title(hits, items) -> str:
    if items:
        return "缺少前置 mod：" + _items_text(items)
    return "缺少前置 mod（日志没写出具体 modId）"


def _duplicate_title(hits, items) -> str:
    ids = [i for i in items if not i.lower().endswith(".jar")]
    jars = [i for i in items if i.lower().endswith(".jar")]
    if ids:
        return "同一个 mod 装了多个版本：" + _items_text(ids)
    if jars:
        return "同一个 mod 装了多个版本：" + _items_text(jars)
    return "同一个 mod 装了多个版本（Duplicate mods）"


_MOD_ID_PATTERNS = (
    re.compile(r"(?:Mod ID|modId|ModId)\s*[:=]\s*'([^']+)'", re.IGNORECASE),
    re.compile(r"of mod '([^']+)'", re.IGNORECASE),
    re.compile(r"\(([a-z0-9_.\-]+)\), which is missing", re.IGNORECASE),
    re.compile(r'The mod "([^"]+)" is missing', re.IGNORECASE),
)

_DUP_ITEM_PATTERNS = (
    re.compile(r"(?:mod\s*id|modid)\s*[:=]\s*'?([\w.\-]+)'?", re.IGNORECASE),
    re.compile(r"([\w.+\-\[\]() ]+\.jar)", re.IGNORECASE),
)

_RULES = (
    _Rule(
        rule_id="oom_heap",
        severity="fatal",
        title="内存不足（Java 堆耗尽）",
        hint=("把这个实例的内存上限调大：设置 → 实例 → 内存，把「最大内存」改成 4096–8192 MB"
              "（1.12.2 整合包 4G 起，1.20 大包 6–8G）；再确认「设置 → Java 运行时」里是 64 位 Java"
              "（x64）—— 32 位 Java 最多只能用到 1.5G，参数调多大都没用。"),
        pattern=re.compile(
            r"java\.lang\.OutOfMemoryError(?::\s*Java heap space)?"
            r"|OutOfMemoryError:\s*GC overhead limit exceeded",
            re.IGNORECASE),
        skip=(re.compile(
            r"Metaspace|PermGen|unable to create new native thread|Direct buffer memory",
            re.IGNORECASE),),
    ),
    _Rule(
        rule_id="oom_metaspace",
        severity="error",
        title="元空间 / PermGen 不足",
        hint=("JVM 参数里加一行 -XX:MaxMetaspaceSize=512m（设置 → 实例 → JVM 参数）；"
              "1.16 以前的老 Forge 包用的是 PermGen，要加的是 -XX:MaxPermSize=512m。"
              "改完还报就减少常驻 mod 数量（元空间是按加载的类算的，mod 越多越吃）。"),
        pattern=re.compile(
            r"OutOfMemoryError:\s*Metaspace|OutOfMemoryError:\s*PermGen space",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="class_version",
        severity="error",
        pattern=_CLASS_VERSION_RE,
        title_fn=_class_version_title,
        hint_fn=_class_version_hint,
    ),
    _Rule(
        rule_id="mixin_tweaker",
        severity="fatal",
        title="mods 目录里有版本不匹配的 mod（MixinTweaker 缺失）",
        hint=("打开 设置 → 实例 → 打开游戏目录 → mods，把不属于本实例版本/加载器的 jar 全部移走"
              "（典型：1.12.2 的 mod 丢进 1.20.1、1.20 的 mod 丢进 1.7.10，或 Fabric mod 混进 Forge）；"
              "然后改成「一个版本一个实例」的独立目录，别把 mods 放进共用的 .minecraft。"
              "清理后先只放必需 mod 启动一次，确认能进主菜单再逐批加回。"),
        pattern=re.compile(
            r"(?:ClassNotFoundException|NoClassDefFoundError|Could not find or load main class)"
            r"[^\n]*org\.spongepowered\.asm\.launch\.MixinTweaker",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="missing_deps",
        severity="fatal",
        title="缺少前置 mod",
        hint=("把上面列出的前置 mod 装进 mods 目录：CurseForge / Modrinth 页面的 Dependencies"
              "（依赖）区能直接下到对应版本；版本区间按日志里的 Expected range 选，"
              "例如 [5.2.0,) 只接受 5.2.0 及以上。装完重启，还缺就继续按新日志补。"),
        pattern=re.compile(
            r"Missing or unsupported mandatory dependencies"
            r"|Missing or unsupported mandatory dependency"
            r"|which is missing!"
            r"|Missing mods:",
            re.IGNORECASE),
        item_re=_MOD_ID_PATTERNS,
        context_span=40,
        title_fn=_missing_deps_title,
    ),
    _Rule(
        rule_id="duplicate_mods",
        severity="error",
        pattern=re.compile(
            r"Found duplicate mods"
            r"|Duplicate mods?\s*(?:found|detected)"
            r"|Found multiple versions of"
            r"|duplicate modid",
            re.IGNORECASE),
        title_fn=_duplicate_title,
        hint=("打开 设置 → 实例 → mods 目录，同一个 mod 只留一个 jar：按文件名里的版本号留较新的那个。"
              "CurseForge 重复下载会生成 xxx.jar 和 xxx (1).jar，删掉带 (1) 的；"
              "整合包解压覆盖也会留两份，先按文件名排序再删。"),
        item_re=_DUP_ITEM_PATTERNS,
        context_span=20,
    ),
    _Rule(
        rule_id="incompatible_class",
        severity="error",
        title="mod 与游戏/加载器版本不兼容",
        hint=("证据里那个类属于哪个 mod，就把那个 mod 换成对应 MC 版本 + 加载器的构建"
              "（1.20.1 的 mod 不能进 1.21，Fabric 的不能进 Forge）；"
              "排查顺序：先清空 mods 确认原版能起，再每 5 个一批放回去，崩的那批就是嫌疑。"),
        pattern=re.compile(
            r"java\.lang\.(?:NoSuchMethodError|NoClassDefFoundError|NoSuchFieldError"
            r"|AbstractMethodError|VerifyError|IllegalAccessError)"
            r"|net\.minecraftforge\.fml\.loading\.(?:ModLoadingException|LoadingFailedException)",
            re.IGNORECASE),
        skip=(re.compile(r"Error loading class", re.IGNORECASE),),
        # 可选联动插件加载失败（Jade / JEI / TOP 的 plugin 常这样）：游戏照常进，
        # 不该报成「mod 与游戏不兼容」，否则每次正常启动都刷一条。
        prev_skip=(
            re.compile(r"Error loading (?:plugin|class) at", re.IGNORECASE),
            re.compile(r"Caught an error from mod plugin", re.IGNORECASE),
        ),
    ),
    _Rule(
        rule_id="glfw",
        severity="error",
        title="显卡驱动 / OpenGL 初始化失败",
        hint=("更新显卡驱动（NVIDIA / AMD / Intel 官网下最新版，别用 Windows Update 推的旧版）；"
              "笔记本双显卡在 Windows「图形设置」里把 java.exe 指定为高性能；"
              "远程桌面 / 虚拟机 / 无头环境跑不出 OpenGL，请在物理显示器上启动；"
              "OptiFine 与 Sodium/Embeddium 不能同时装，先只留一个再试。"),
        pattern=re.compile(
            r"GLFW error\s*\d+"
            r"|Pixel format not accelerated"
            r"|does not appear to support OpenGL"
            r"|Failed to create (?:the )?(?:window|GL context|OpenGL context|context)\b"
            r"|Failed to (?:create|initialize) (?:GLFW|the window system)"
            r"|GLFW initialization failed"
            r"|Could not initialize (?:GL|OpenGL)\b"
            r"|OpenGL\s+\d+(?:\.\d+)*\s+is\s+not\s+supported"
            r"|WGL: (?:Failed|The driver)",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="heap_reserve",
        severity="fatal",
        title="内存参数超出 JVM 能分配的上限",
        hint=("八成是 32 位 Java：设置 → Java 运行时 换成 x64（「Java 管理」里能下），"
              "32 位最多只能分配约 1.5G，-Xmx4G 一定启动失败；"
              "如果内存够但页面文件太小（比如设了 -Xmx12G 而物理内存 16G），"
              "把实例最大内存降到物理内存一半以内，或在 Windows「高级系统设置 → 性能 → 虚拟内存」调大页面文件。"),
        pattern=re.compile(
            r"Could not reserve enough space for .*object heap"
            r"|Invalid maximum heap size"
            r"|The specified size exceeds the maximum representable size",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="vm_option",
        severity="error",
        title="JVM 参数里有当前 Java 不认识的选项",
        hint=("打开 设置 → 实例 → JVM 参数，把证据里那条 -XX: 选项删掉："
              "老 Java（8）不认 -XX:+UseZGC / -XX:+UseShenandoahGC 这类新参数，"
              "新 Java（21）也不再接受 -XX:MaxPermSize。要么删参数，要么换 Java 版本。"),
        pattern=re.compile(
            r"Unrecognized VM option|Unrecognized option:|Improperly specified VM option",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="exit_trapped",
        severity="warn",
        title="Forge 拦下了 System.exit（这不是根因）",
        hint=("这行只是 Forge 的 SecurityManager 把退出拦住了，真正的崩溃在它上面几十行："
              "往上找第一条 Caused by: / Exception in thread \"main\" / A fatal error has been detected，"
              "或者把整份 logs/latest.log 交给「诊断」——启动器扫的是完整文件，能定位更早的那条。"),
        pattern=re.compile(r"FMLSecurityManager\$ExitTrappedException", re.IGNORECASE),
    ),
    _Rule(
        rule_id="jarfile",
        severity="error",
        title="版本 jar 缺失（Unable to access jarfile）",
        hint=("回「版本」页对当前版本点「重新安装/修复」，它会重新校验并补下"
              " versions/<版本>/<版本>.jar；如果 versions 目录被你手动改过（删过 jar、改过 json），"
              "把整个 versions/<版本> 目录删掉重装最干净。"),
        pattern=re.compile(r"Unable to access jarfile", re.IGNORECASE),
    ),
    _Rule(
        rule_id="network",
        severity="warn",
        title="下载 / 联网失败",
        hint=("启动器侧：设置 → 下载 → 把源换成镜像（BMCLAPI / MCBBS），或关掉系统代理再试；"
              "公司网 / 校园网常拦 piston-data.mojang.com 和 api.minecraftservices.com，"
              "换手机热点能验证是不是网络问题；游戏内微软登录要能连 login.live.com，"
              "皮肤要 textures.minecraft.net，被墙就挂代理。"),
        pattern=re.compile(
            r"Failed to download"
            r"|Unable to download"
            r"|UnknownHostException"
            r"|Connection reset"
            r"|Connection refused"
            r"|java\.net\.ConnectException"
            r"|SocketTimeoutException"
            r"|SSLHandshakeException"
            r"|NoRouteToHostException",
            re.IGNORECASE),
        max_hits=3,
    ),
    _Rule(
        rule_id="eula",
        severity="fatal",
        title="服务端还没同意 EULA（eula.txt）",
        hint=("打开实例目录下的 server/eula.txt（实例 → 打开目录），把 eula=false 改成 eula=true "
              "保存后再启动；文件不存在就用记事本新建一个，只写一行 eula=true。"
              "这是 Mojang 的法律协议，启动器不会替你勾选。"),
        pattern=re.compile(
            r"You need to agree to the EULA"
            r"|You must agree to the EULA"
            r"|agree to the Minecraft EULA",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="jvm_native_crash",
        severity="fatal",
        title="Java 进程被本地代码打崩（不是普通异常）",
        hint=("打开游戏目录里最新的 hs_err_pid*.log，看 Problematic frame："
              "指向 nvoglv64.dll / atio6axx.dll / igd*.dll 就是显卡驱动（换一版驱动，或关掉光影/OptiFine）；"
              "指向某个 mod 的 .dll 就把那个 mod 删掉；"
              "把 crash-reports 里的报告连同 hs_err 一起发给 mod 作者。"),
        pattern=re.compile(
            r"A fatal error has been detected by the Java Runtime Environment"
            r"|EXCEPTION_ACCESS_VIOLATION"
            r"|EXCEPTION_STACK_OVERFLOW"
            r"|SIGSEGV",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="class_major_too_new",
        severity="error",
        title="Java 版本过高（mod / 加载器跟不上）",
        hint=("把实例 Java 换到加载器要求的版本：1.12.2 Forge 用 Java 8、1.16.5 用 8/11、"
              "1.18–1.20.4 用 17、1.20.5+ 用 21。日志里的 61 = Java 17、65 = Java 21；"
              "老 mod 的 Mixin/ASM 不认识新 class 文件版本，就会报这个。"),
        pattern=re.compile(
            r"Unsupported class file major version|Unsupported class file version",
            re.IGNORECASE),
    ),
    _Rule(
        rule_id="tick_crash",
        severity="error",
        title="世界 tick 时崩溃（某个方块 / 实体导致）",
        hint=("看 crash-reports 里那份报告最上面的 Description: 和紧跟的 Caused by:，里面有 mod id 和类名；"
              "确认是哪个 mod 的方块/实体后，先禁用该 mod 再进世界，或用 Amulet/MCEdit 把那个方块从存档里删掉；"
              "单人也可以新建一个世界测试，区分是存档坏了还是 mod 冲突。"),
        pattern=re.compile(
            r"Exception in server tick loop"
            r"|Description: Ticking (?:entity|block entity|player|screen)"
            r"|Encountered an unexpected exception",
            re.IGNORECASE),
        max_hits=2,
    ),
    _Rule(
        rule_id="mixin_apply",
        severity="error",
        title="Mixin 注入失败（两个 mod 改了同一处）",
        hint=("按证据里的 mixin 配置名（形如 mixins.xxx.json）找到对应 mod，先单独禁用其中一个；"
              "常见冲突：两个优化 mod（OptiFine+Sodium、Starlight+Phosphor）、两个同类内容 mod；"
              "Forge 与 Fabric 的 mixin 版本混装也会报这个。"),
        pattern=re.compile(
            r"Mixin apply failed"
            r"|MixinApplyError"
            r"|InvalidInjectionException"
            r"|Critical injection failure"
            r"|MixinTransformerError",
            re.IGNORECASE),
    ),
)


# ────────────────────────── 引擎 ──────────────────────────


def _items_text(items: Sequence[str]) -> str:
    if not items:
        return ""
    if len(items) <= 4:
        return "、".join(items)
    return "、".join(items[:4]) + " 等 " + str(len(items)) + " 个"


def _render(template: str, values: dict) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def _clean(line: str) -> str:
    return str(line).rstrip()[:DETAIL_LINE_CHARS]


def _collect_context(lines: Sequence[str], index: int, rule: "_Rule") -> list:
    """命中行之后收 actionable 的上下文行（只留匹配 item_re 的行，连续 6 行不匹配就停）。"""
    if rule.context_span <= 0 or not rule.item_re:
        return []
    out = []
    misses = 0
    end = min(len(lines), index + 1 + rule.context_span)
    for pos in range(index + 1, end):
        line = lines[pos]
        if not line.strip():
            continue
        if any(pattern.search(line) for pattern in rule.item_re):
            out.append(line)
            misses = 0
        else:
            misses += 1
            if misses >= 6:
                break
        if len(out) >= 12:
            break
    return out


def _extract_items(rule: "_Rule", source_lines: Sequence[str]) -> list:
    if not rule.item_re:
        return []
    found = []
    for line in source_lines:
        for pattern in rule.item_re:
            for match in pattern.finditer(line):
                value = ""
                for group in match.groups():
                    if group:
                        value = group
                        break
                value = (value or "").strip()
                if value and value not in found:
                    found.append(value)
    return found[:8]


def _build_detail(hits: Sequence, context: Sequence[str]) -> str:
    rows = []
    for _index, line in hits[:3]:
        rows.append(_clean(line))
    for line in context:
        if len(rows) >= DETAIL_MAX_LINES:
            break
        rows.append(_clean(line))
    out = []
    seen = set()
    for row in rows:
        key = row.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= DETAIL_MAX_LINES:
            break
    return "\n".join(out)


def analyze(text: str) -> list:
    """扫一段日志文本，返回按严重程度排好序的 Finding 列表。"""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8", "replace")
    if not isinstance(text, str) or not text.strip():
        return []
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]
    findings = []
    used_titles = set()
    for rule in _RULES:
        hits = []
        context = []
        for index, line in enumerate(lines):
            if rule.skip and any(pattern.search(line) for pattern in rule.skip):
                continue
            if rule.prev_skip:
                prev = lines[index - 1] if index >= 1 else ""
                prev2 = lines[index - 2] if index >= 2 else ""
                if any(p.search(prev) or p.search(prev2) for p in rule.prev_skip):
                    continue
            if not rule.pattern.search(line):
                continue
            hits.append((index, line))
            if rule.context_span:
                context.extend(_collect_context(lines, index, rule))
            if len(hits) >= rule.max_hits:
                break
        if not hits:
            continue
        source_lines = [line for _index, line in hits] + context
        items = _extract_items(rule, source_lines)
        values = {"items": _items_text(items), "count": len(hits)}
        title = rule.title_fn(hits, items) if rule.title_fn else _render(rule.title, values)
        hint = rule.hint_fn(hits, items) if rule.hint_fn else _render(rule.hint, values)
        if not title or title in used_titles:
            continue
        used_titles.add(title)
        findings.append(Finding(
            severity=rule.severity,
            title=title,
            detail=_build_detail(hits, context),
            hint=hint,
        ))
    findings.sort(key=lambda item: SEVERITY_ORDER.get(item.severity, 9))
    return findings


def analyze_file(path: str, max_bytes: int = 2 * 1024 * 1024) -> list:
    """读日志文件（支持 .gz）尾部 max_bytes 后诊断；文件不存在或读不了返回空列表。"""
    if not path:
        return []
    target = str(path)
    if not os.path.isfile(target):
        return []
    try:
        limit = max(4096, int(max_bytes or 0))
    except (TypeError, ValueError):
        limit = 2 * 1024 * 1024
    try:
        if target.lower().endswith((".gz", ".gzip")):
            data = _read_gzip_tail(target, limit)
        else:
            data = _read_tail(target, limit)
    except (OSError, EOFError):
        return []
    if not data:
        return []
    text = data.decode("utf-8", "replace")
    if len(data) >= limit:
        cut = text.find("\n")
        if 0 <= cut < 4096:          # 丢掉被截半的首行
            text = text[cut + 1:]
    return analyze(text)


def _read_tail(path: str, limit: int) -> bytes:
    with open(path, "rb") as fh:
        try:
            size = os.fstat(fh.fileno()).st_size
        except OSError:
            size = 0
        if size > limit:
            fh.seek(size - limit)
        return fh.read(limit)


def _read_gzip_tail(path: str, limit: int) -> bytes:
    buffer = b""
    with gzip.open(path, "rb") as fh:
        while True:
            chunk = fh.read(256 * 1024)
            if not chunk:
                break
            buffer = (buffer + chunk)[-limit:]
    return buffer


def summary(findings: list) -> str:
    """一句话结论，给 UI 的标题栏 / 状态栏用。"""
    if not findings:
        return "没有命中已知的崩溃特征：日志里看不到内存不足、Java 版本、缺前置、显卡或网络问题。"
    counts = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    parts = []
    for severity in ("fatal", "error", "warn", "info"):
        count = counts.get(severity, 0)
        if count:
            parts.append(SEVERITY_LABEL.get(severity, severity) + " " + str(count) + " 条")
    first = None
    for finding in findings:
        if finding.severity in ("fatal", "error"):
            first = finding
            break
    if first is None:
        first = findings[0]
        tail = "可以先看「" + first.title + "」"
    else:
        tail = "先处理「" + first.title + "」"
    return "共 " + str(len(findings)) + " 条诊断（" + "、".join(parts) + "），" + tail + "。"


def rule_ids() -> list:
    """规则清单（给自检 / 文档用）。"""
    return [rule.rule_id for rule in _RULES]
