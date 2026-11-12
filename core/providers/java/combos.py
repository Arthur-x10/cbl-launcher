"""Java 版加载器组合的兼容性数据。

这个文件是**数据**，不是策略：UI 只读它来决定槽位能否放入、显示什么颜色。

三种容器层
    primary  主加载器，四选一（Forge / NeoForge / Fabric / Quilt）
    addon    可叠加的附加加载器（LiteLoader，官方文档写明可与 Forge 共存）
    patch    渲染补丁（OptiFine），不参与加载器互斥，但和渲染类 mod 冲突

每条规则都带出处。`verified=True` 表示这条有官方/文档明文；`False` 表示是从
结构（fork 关系）或启动器实践推出来的，UI 应当用金色提示而不是红色断言。

⚠ 一个容易写错的字面坑：**"兼容 mod" ≠ "加载器共存"**。
   Quilt 官网说 "compatible with all your favourite Fabric mods"，Fabric FAQ 说
   Forge 与 Fabric 不能 mix，Sinytra Connector 说能跑对家的 mod —— 这三句都在讲
   **mod 层**。它不意味着"把 Quilt 叠在 Fabric 上"：Quilt 只是 Fabric 的替代品。
"""

from dataclasses import dataclass
from typing import Optional

# ═══════════════════ 加载器定义 ═══════════════════

PRIMARY = "primary"
ADDON = "addon"
PATCH = "patch"


@dataclass(frozen=True)
class Loader:
    id: str
    name: str
    kind: str
    min_mc: str = ""      # 空 = 没有下限
    max_mc: str = ""      # 空 = 没有上限
    note: str = ""
    limit_note: str = ""  # 下限是"本项目依赖库"的限制而非官方限制时，用这句话替换默认文案


LOADERS: list[Loader] = [
    Loader("forge", "Forge", PRIMARY, note="Forge 系主加载器"),
    Loader("neoforge", "NeoForge", PRIMARY, min_mc="1.20.2",
           note="Forge 1.20.1 之后的分叉；本启动器依赖库只做到 1.20.2+",
           limit_note="本启动器的安装库暂时只做到 1.20.2 及以上（NeoForge 官方其实有 1.20.1 的 47.x）"),
    Loader("fabric", "Fabric", PRIMARY, min_mc="1.14",
           note="从 1.14 开始支持；1.13.2 及以前没有 Fabric"),
    Loader("quilt", "Quilt", PRIMARY, min_mc="1.14.4",
           note="Fabric 的替代品；Quilt 官方 meta 里最老的一条是 1.14.4"),
    Loader("liteloader", "LiteLoader", ADDON, max_mc="1.12.2",
           note="已停更，最后支持到 1.12.2；可作为模组装在 Forge 下"),
    Loader("optifine", "OptiFine", PATCH,
           note="渲染补丁，不是加载器；MC百科原文：与 钠 / 锂 / Canvas 渲染器 冲突（Iris 是替代方案，不是冲突项）"),
]

LOADER_BY_ID = {l.id: l for l in LOADERS}


def loaders_of(kind: str) -> list[Loader]:
    return [l for l in LOADERS if l.kind == kind]


# ═══════════════════ 版本比较 ═══════════════════

def version_tuple(v: str) -> tuple:
    """把 "1.21.11" / "26.2" / "1.7.10" 变成可比较的元组。

    Minecraft 2026 年起用年代版本号（26.2），所以不能假设第一个分量是 1。
    """
    parts: list[int] = []
    for chunk in str(v or "").replace("_", ".").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
    return tuple(parts) or (0,)


def _in_range(loader: Loader, mc_version: str) -> tuple[bool, str]:
    cur = version_tuple(mc_version)
    if loader.min_mc and cur < version_tuple(loader.min_mc):
        return False, loader.limit_note or f"需要 Minecraft {loader.min_mc} 及以上"
    if loader.max_mc and cur > version_tuple(loader.max_mc):
        return False, f"只支持到 Minecraft {loader.max_mc}"
    return True, ""


def availability(loader_id: str, mc_version: str) -> tuple[bool, str]:
    """这个加载器在这个 MC 版本上有没有（不看冲突，只看自身支持范围）。"""
    loader = LOADER_BY_ID.get(loader_id)
    if loader is None:
        return False, f"未知的加载器 {loader_id}"
    return _in_range(loader, mc_version)


# ═══════════════════ 组合规则 ═══════════════════

BLOCKED = "blocked"      # 不能放进同一个实例
WARN = "warn"            # 能放，但有前提（需特定版本 / 需第三方 mod）
NOTE = "note"            # 只是提示，不影响操作


@dataclass(frozen=True)
class Rule:
    level: str
    reason: str
    hint: str = ""
    source: str = ""
    verified: bool = False


def _key(a: str, b: str) -> frozenset:
    return frozenset((a, b))


PAIR_RULES: dict[frozenset, Rule] = {
    # ── 官方明文 ──
    _key("forge", "fabric"): Rule(
        BLOCKED,
        "Forge 与 Fabric 只能二选一",
        "想同时跑两边的 mod，装 Sinytra Connector（仍然只有一个加载器）",
        "https://wiki.fabricmc.net/faq:user", True),

    _key("forge", "liteloader"): Rule(
        NOTE,
        "LiteLoader 可作为模组装在 Forge 下",
        "两者官方声明兼容，但 Forge 太新 + LiteLoader 太老会出问题",
        "https://www.mcmod.cn/class/610.html", True),

    _key("optifine", "forge"): Rule(
        WARN,
        "OptiFine 要用 Forge 版（放进 mods/）",
        "optifine.net 每个版本都标注了对应的 Forge 版本号，选之前对一眼",
        "https://optifine.net/downloads", True),

    _key("optifine", "neoforge"): Rule(
        BLOCKED,
        "OptiFine 当前没有 NeoForge 版",
        "改用 Sodium + Iris，或退回 Forge",
        "https://optifine.net/downloads", True),

    _key("optifine", "fabric"): Rule(
        WARN,
        "OptiFine 与 Fabric 共存需要 OptiFabric",
        "Fabric 官方 FAQ 原话是 OptiFabric 这类非官方 mod「可能不与你的 mod 兼容」，能不用就不用",
        "https://wiki.fabricmc.net/faq:user", True),

    _key("optifine", "quilt"): Rule(
        WARN,
        "OptiFine 没有 Quilt 版，只能靠 OptiFabric 转",
        "OptiFabric 是为 Fabric 写的，Quilt 能不能吃没看到官方说法，装之前先备份存档",
        "https://optifine.net/downloads", False),

    _key("fabric", "quilt"): Rule(
        BLOCKED,
        "Quilt 与 Fabric 同源，只能二选一",
        "Quilt 能直接加载 Fabric mod，换过去不用换 mod",
        "https://quiltmc.org/en/", False),

    _key("forge", "neoforge"): Rule(
        BLOCKED,
        "NeoForge 是基于 Forge 的分叉，同一实例只能装一个",
        "",
        "https://github.com/neoforged/NeoForge", False),

    _key("liteloader", "optifine"): Rule(
        NOTE,
        "LiteLoader 能直接加载 OptiFine",
        "1.7.10 时代的经典三件套就是 Forge + LiteLoader + OptiFine，装完不打架",
        "https://www.minecraftforum.net/forums/mapping-and-modding-java-edition/minecraft-mods/1290155-liteloader", True),

    _key("liteloader", "fabric"): Rule(
        BLOCKED,
        "LiteLoader 只支持到 1.12.2，Fabric 从 1.14 才开始",
        "",
        "", False),

    _key("liteloader", "quilt"): Rule(
        BLOCKED,
        "LiteLoader 只支持到 1.12.2，Quilt 从 1.14 才开始",
        "",
        "", False),
}


def rule_between(a: str, b: str) -> Optional[Rule]:
    return PAIR_RULES.get(_key(a, b))


# ═══════════════════ 组合校验 ═══════════════════

@dataclass
class Issue:
    level: str        # blocked / warn / note
    reason: str
    hint: str = ""
    source: str = ""
    verified: bool = False
    involving: tuple = ()   # 涉及哪几个加载器 id


def check_combo(mc_version: str, chosen: dict[str, str]) -> list[Issue]:
    """chosen: {loader_id: loader_version}。返回这条组合上的全部问题。

    分两级：
      1. 加载器级 —— 互斥 / 不可用，blocked 的话不该允许安装
      2. 版本级 —— 能装，但版本对不上（例如 OptiFine 要求的 Forge 版本）
    """
    issues: list[Issue] = []
    ids = [k for k in chosen if k in LOADER_BY_ID]

    # 1) 自身可用性（版本范围）。不知道 MC 版本就不判，免得把"未知"当成"不支持"
    for lid in ids:
        if not str(mc_version or "").strip():
            break
        ok, why = availability(lid, mc_version)
        if not ok:
            issues.append(Issue(BLOCKED, f"{LOADER_BY_ID[lid].name}：{why}",
                                "", "", True, (lid,)))

    # 2) 两两冲突
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            rule = rule_between(a, b)
            if rule is None:
                continue
            issues.append(Issue(rule.level, rule.reason, rule.hint,
                                rule.source, rule.verified, (a, b)))

    # 3) 版本级提示（OptiFine 的 Forge 版本匹配）
    if "optifine" in chosen and "forge" in chosen:
        issues.append(Issue(
            NOTE,
            "装之前对一眼：OptiFine 版本标注的 Forge 版本要和你的 Forge 一致",
            f"当前 Forge {chosen.get('forge')} / OptiFine {chosen.get('optifine')}",
            "https://optifine.net/downloads", True, ("forge", "optifine")))

    return issues


def blocking_issues(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == BLOCKED]


def can_install(issues: list[Issue]) -> bool:
    return not blocking_issues(issues)


def summarize(chosen: dict[str, str]) -> str:
    """"1.7.10 · Forge 47.4.23 · OptiFine HD_U_E7" 这样的成品名。"""
    parts: list[str] = []
    for kind in (PRIMARY, ADDON, PATCH):
        for loader in loaders_of(kind):
            ver = chosen.get(loader.id)
            if ver:
                parts.append(f"{loader.name} {ver}" if ver != loader.name else loader.name)
    return " · ".join(parts)


def default_name(mc_version: str, chosen: dict[str, str]) -> str:
    """实例名默认值：版本 + 主加载器，不把技术串拼进去。"""
    main = next((chosen[l.id] for l in loaders_of(PRIMARY) if chosen.get(l.id)), "")
    suffix = ""
    for loader in loaders_of(PRIMARY):
        if chosen.get(loader.id):
            suffix = f" · {loader.name}"
            break
    return f"{mc_version}{suffix}" if mc_version else (suffix.lstrip(" · ") or "新实例")

def tag_from_optifine_jar(path: str) -> str:
    """从 OptiFine_1.12.2_HD_U_G5.jar 这样的文件名里取出 HD_U_G5。

    OptiFine 没有版本 API，用户下载到的就是一个 jar，版本号只在文件名里。
    取不出来就返回去掉扩展名的整个名字，至少不会撒谎。
    """
    name = str(path or "").rsplit(chr(92), 1)[-1].rsplit("/", 1)[-1]
    if name.lower().endswith(".jar"):
        name = name[:-4]
    parts = name.split("_")
    if len(parts) >= 3 and parts[0].lower().startswith("optifine"):
        return "_".join(parts[2:])
    return name

def detect_from_version_id(vid: str) -> dict:
    """从版本目录名反推它是什么材料合成的。

    这是 minecraft-launcher-lib 的命名约定，不是我们发明的：
        1.12.2-forge-14.23.5.2860
        1.20.1-fabric-loader-0.15.11            （有时带尾缀 -1.20.1）
        neoforge-21.1.80                         （也见过 1.20.4-neoforge-20.4.237）
        1.12.2-OptiFine_HD_U_G5
    认不出来就返回空 dict，宁可不显示也不要瞎猜。
    """
    text = str(vid or "")
    low = text.lower()
    if not low:
        return {}
    hits = _marker_hits(low)
    out: dict = {}
    for n, (start, stop_mark, marker) in enumerate(hits):
        end = hits[n + 1][0] if n + 1 < len(hits) else len(text)
        raw = text[stop_mark:end].strip(" -_")
        lid = _MARKER_TO_ID[marker]
        if lid == "optifine":
            # OptiFine 的版本号区分大小写（HD_U_G5），原样保留
            out[lid] = raw.lstrip("_-")
            continue
        value = _strip_mc_suffix(raw)
        if value:
            out[lid] = value
    return out


# 材料标记 → 加载器 id
_MARKER_TO_ID = {
    "optifine": "optifine",
    "liteloader": "liteloader",
    "neoforge": "neoforge",
    "forge": "forge",
    "quilt-loader": "quilt",
    "quilt": "quilt",
    "fabric-loader": "fabric",
    "fabric": "fabric",
}


def _marker_hits(low: str) -> list:
    """找出所有材料标记的位置，丢掉被更长标记覆盖的那些（forge 落在 neoforge 里）。"""
    cands = []
    for marker in _MARKER_TO_ID:
        start = 0
        while True:
            i = low.find(marker, start)
            if i < 0:
                break
            cands.append((i, i + len(marker), marker))
            start = i + 1
    cands.sort()
    kept: list = []
    for cand in cands:
        if kept and cand[0] < kept[-1][1]:
            if (cand[1] - cand[0]) > (kept[-1][1] - kept[-1][0]):
                kept[-1] = cand
            continue
        kept.append(cand)
    return kept


def _strip_mc_suffix(value: str) -> str:
    """去掉版本号尾巴上挂的 Minecraft 版本（-1.7.10 / -26.2）。"""
    import re as _re
    return _re.sub(r"-(?:1\.\d+(?:\.\d+)?|\d{2}\.\d+)$", "", value).strip(" -_")

def mc_version_of(vid: str) -> str:
    """从版本目录名里抠出 Minecraft 版本号；抠不出就返回空串。

    "1.12.2-forge-14.23.5.2860" -> 1.12.2
    "fabric-loader-0.15.11-1.20.1" -> 1.20.1
    "neoforge-21.1.80" -> ""（这里 21.1.80 是 NeoForge 的版本，不是 MC 的）
    """
    import re as _re
    pattern = _re.compile(r"^(1\.\d+(\.\d+)?|\d{2}\.\d+)$")

    def ok(text):
        return bool(text) and bool(pattern.match(text))

    head = str(vid or "").split("-")[0]
    if ok(head):
        return head
    for part in reversed(str(vid or "").split("-")):
        if ok(part):
            return part
    return ""
