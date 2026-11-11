"""Java 版 mod 依赖解析 —— 只读扫描 mods 目录里的 jar 元数据，产出可读的依赖报告。"""

import io
import json
import os
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from typing import Optional

# 单个元数据条目的读取上限：畸形/恶意 jar 不能靠一个超大条目把内存撑爆
MAX_META_BYTES = 4 * 1024 * 1024
# JarJar 内嵌 jar 的扫描预算（kotlinforforge 这类 all-jar 的 mod 藏在里面）
MAX_NESTED_JARS = 8
MAX_NESTED_BYTES = 64 * 1024 * 1024

# 平台占位 id：这些不算「缺失的前置 mod」
PLATFORM_IDS = frozenset({
    "minecraft", "java", "forge", "neoforge", "minecraftforge", "fmlloader",
    "fabric", "fabricloader", "fabric-loader", "fabric_api", "quilt_loader",
    "quilt-loader", "quilt_base", "qsl", "javafml", "lowcodefml", "fml",
    "mixin", "coremods",
})

# 一个 jar 可能同时带 Forge 与 NeoForge 元数据（1.20.1 ~ 1.20.4 的兼容包），
# 顺序即优先级：mods.toml 是 1.20.4 及以前 Forge/NeoForge 都认的那份。
_METADATA_ORDER = (
    ("META-INF/mods.toml", "forge"),
    ("META-INF/neoforge.mods.toml", "neoforge"),
    ("fabric.mod.json", "fabric"),
    ("quilt.mod.json", "quilt"),
    ("mcmod.info", "forge"),
)
_MANIFEST = "META-INF/MANIFEST.MF"

# 加载器之间的兼容关系（Forge mod 能在 NeoForge 上跑，Fabric 的能在 Quilt 上跑）
_COMPATIBLE_LOADERS = {
    "forge": {"forge"},
    "neoforge": {"neoforge", "forge"},
    "fabric": {"fabric"},
    "quilt": {"quilt", "fabric"},
}


@dataclass
class ModInfo:
    """一个 jar 的 mod 元数据摘要。bad 非空表示这个 jar 有问题。"""

    file: str
    mod_id: str = ""
    name: str = ""
    version: str = ""
    loader: str = ""
    mc_dep: str = ""
    deps: list[dict] = field(default_factory=list)
    bad: str = ""


# ═══════════════════ zip 读取（只读，不解压到磁盘） ═══════════════════

def _safe_entry(name: str) -> bool:
    """zip 条目名是否安全：拒绝绝对路径、盘符与 ".."（zip slip 防御）。

    这里只读不写盘，但仍然按同一条规则过滤 —— 一旦将来有代码复用这些名字去
    落盘，越界条目不会被放行。
    """
    if not name:
        return False
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return False
    return ".." not in [p for p in n.split("/") if p not in ("", ".")]


def _read_entry(zf: zipfile.ZipFile, name: str,
                limit: int = MAX_META_BYTES) -> Optional[bytes]:
    if not _safe_entry(name):
        return None
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > limit:
        return None
    try:
        with zf.open(name) as f:
            return f.read(limit + 1)[:limit]
    except Exception:
        return None


def _text(raw: bytes) -> str:
    return raw.decode("utf-8-sig", "replace")


def _range_text(value) -> str:
    if value is None:
        return "*"
    if isinstance(value, (list, tuple)):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return " | ".join(parts) if parts else "*"
    return str(value).strip() or "*"


def _dedupe_deps(deps: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for dep in deps:
        key = (dep.get("mod_id", "").lower(), dep.get("version_range", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(dep)
    return out


# ═══════════════════ 元数据解析 ═══════════════════

def _parse_toml_mod(raw: bytes, loader: str) -> dict:
    """META-INF/mods.toml（Forge / NeoForge）。

    依赖写成 [[dependencies.<modid>]] 表数组，键是 modId / mandatory / versionRange；
    NeoForge 1.20.5+ 把 mandatory 换成了 type="required|optional|...".
    """
    data = tomllib.loads(_text(raw))
    mods = data.get("mods") or []
    first = mods[0] if isinstance(mods, list) and mods else {}
    if not isinstance(first, dict):
        first = {}

    deps: list[dict] = []
    dep_root = data.get("dependencies") or {}
    blocks: list = []
    if isinstance(dep_root, dict):
        for _owner, items in dep_root.items():
            if isinstance(items, list):
                blocks.extend(items)
            elif isinstance(items, dict):
                blocks.append(items)
    for item in blocks:
        if not isinstance(item, dict):
            continue
        dep_id = str(item.get("modId") or item.get("modid") or "").strip()
        if not dep_id:
            continue
        mandatory = item.get("mandatory")
        if mandatory is None:
            mandatory = str(item.get("type") or "").strip().lower() == "required"
        deps.append({
            "mod_id": dep_id,
            "mandatory": bool(mandatory),
            "version_range": _range_text(item.get("versionRange")
                                         or item.get("versionrange")),
        })
    deps = _dedupe_deps(deps)
    return {
        "loader": loader,
        "mod_id": str(first.get("modId") or first.get("modid") or "").strip(),
        "name": str(first.get("displayName") or first.get("displayname") or "").strip(),
        "version": str(first.get("version") or "").strip(),
        "mc_dep": next((d["version_range"] for d in deps
                        if d["mod_id"].lower() == "minecraft"), ""),
        "deps": deps,
    }


def _parse_fabric(raw: bytes) -> dict:
    """fabric.mod.json（depends / recommends）。"""
    data = json.loads(_text(raw))
    deps: list[dict] = []
    for section, mandatory in (("depends", True), ("recommends", False)):
        block = data.get(section) or {}
        if not isinstance(block, dict):
            continue
        for dep_id, rng in block.items():
            deps.append({
                "mod_id": str(dep_id).strip(),
                "mandatory": mandatory,
                "version_range": _range_text(rng),
            })
    depends = data.get("depends") if isinstance(data.get("depends"), dict) else {}
    return {
        "loader": "fabric",
        "mod_id": str(data.get("id") or "").strip(),
        "name": str(data.get("name") or "").strip(),
        "version": str(data.get("version") or "").strip(),
        "mc_dep": _range_text(depends.get("minecraft")),
        "deps": _dedupe_deps(deps),
    }


def _parse_quilt(raw: bytes) -> dict:
    """quilt.mod.json（quilt_loader.depends 是 [{id, versions}] 列表）。"""
    data = json.loads(_text(raw))
    ql = data.get("quilt_loader") if isinstance(data.get("quilt_loader"), dict) else {}
    meta = ql.get("metadata") if isinstance(ql.get("metadata"), dict) else {}
    deps: list[dict] = []
    for section, mandatory in (("depends", True), ("recommends", False)):
        block = ql.get(section) or data.get(section) or []
        if isinstance(block, list):
            for item in block:
                if not isinstance(item, dict):
                    continue
                dep_id = str(item.get("id") or "").strip()
                if not dep_id:
                    continue
                deps.append({
                    "mod_id": dep_id,
                    "mandatory": mandatory,
                    "version_range": _range_text(item.get("versions")),
                })
        elif isinstance(block, dict):
            for dep_id, rng in block.items():
                deps.append({
                    "mod_id": str(dep_id).strip(),
                    "mandatory": mandatory,
                    "version_range": _range_text(rng),
                })
    deps = _dedupe_deps(deps)
    return {
        "loader": "quilt",
        "mod_id": str(ql.get("id") or data.get("id") or "").strip(),
        "name": str(meta.get("name") or "").strip(),
        "version": str(ql.get("version") or "").strip(),
        "mc_dep": next((d["version_range"] for d in deps
                        if d["mod_id"].lower() == "minecraft"), ""),
        "deps": deps,
    }


def _parse_mcmod(raw: bytes) -> Optional[dict]:
    """mcmod.info（1.7~1.12 的 Forge 老格式）。"""
    data = json.loads(_text(raw))
    entries = data.get("modList") if isinstance(data, dict) else data
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or not entries:
        return None
    first = entries[0] if isinstance(entries[0], dict) else {}
    deps: list[dict] = []
    for name in first.get("requiredMods") or []:
        dep_id = str(name or "").strip()
        if dep_id:
            deps.append({"mod_id": dep_id, "mandatory": True, "version_range": "*"})
    return {
        "loader": "forge",
        "mod_id": str(first.get("modid") or first.get("modId") or "").strip(),
        "name": str(first.get("name") or "").strip(),
        "version": str(first.get("version") or "").strip(),
        "mc_dep": _range_text(first.get("mcversion")
                              or first.get("acceptableMinecraftVersions")),
        "deps": deps,
    }


def _parse_manifest(text: str) -> dict:
    """解析 MANIFEST.MF（续行以单个空格开头）。"""
    out: dict[str, str] = {}
    last = None
    for line in text.splitlines():
        if line.startswith(" ") and last:
            out[last] += line[1:]
            continue
        if ":" not in line:
            continue
        key, _sep, value = line.partition(":")
        last = key.strip().lower()
        out[last] = value.strip()
    return out


def _sanitize_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (name or "").lower()).strip("_")[:64]


def _parse_metadata(entry: str, raw: bytes, loader: str) -> Optional[dict]:
    if entry.endswith("mods.toml"):
        return _parse_toml_mod(raw, loader)
    if entry == "fabric.mod.json":
        return _parse_fabric(raw)
    if entry == "quilt.mod.json":
        return _parse_quilt(raw)
    if entry == "mcmod.info":
        return _parse_mcmod(raw)
    return None


# ═══════════════════ 单个 jar ═══════════════════

def _nested_ids(zf: zipfile.ZipFile) -> set[str]:
    """读 JarJar 内嵌 jar 的 modId（kotlinforforge / Connector 这类打包型 jar）。

    Forge 的 JarJar 会在运行时把这些 jar 注册成独立 mod，所以它们算「已安装的前置」；
    不扫这一层就会把 flywheel、kotlinforforge 之类的依赖误报成缺失。
    """
    ids: set[str] = set()
    try:
        names = [n for n in zf.namelist()
                 if n.lower().endswith(".jar") and _safe_entry(n)]
    except Exception:
        return ids
    if not names:
        return ids
    # jarjar 目录优先，其余按名字排序，保证结果稳定
    names.sort(key=lambda n: (0 if "/jarjar/" in n.lower() else 1, n.lower()))
    budget = MAX_NESTED_BYTES
    for entry in names[:MAX_NESTED_JARS]:
        try:
            size = zf.getinfo(entry).file_size
        except KeyError:
            continue
        if size > budget:
            continue
        try:
            raw = zf.read(entry)
        except Exception:
            continue
        budget -= len(raw)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                inner_names = set(inner.namelist())
                for cand, loader in _METADATA_ORDER:
                    if cand not in inner_names:
                        continue
                    payload = _read_entry(inner, cand)
                    if payload is None:
                        continue
                    parsed = _parse_metadata(cand, payload, loader)
                    if parsed and parsed.get("mod_id"):
                        ids.add(str(parsed["mod_id"]).lower())
                    break
        except Exception:
            continue
    return ids


def _scan_one(path: str, with_nested: bool = False) -> tuple[ModInfo, set[str]]:
    name = os.path.basename(path)
    info = ModInfo(file=name)
    provided: set[str] = set()

    try:
        with zipfile.ZipFile(path) as zf:
            try:
                names = {n for n in zf.namelist() if _safe_entry(n)}
            except Exception as e:
                info.bad = f"无法读取条目列表: {e}"
                return info, provided

            for cand, loader in _METADATA_ORDER:
                if cand not in names:
                    continue
                payload = _read_entry(zf, cand)
                if payload is None:
                    continue
                parsed = _parse_metadata(cand, payload, loader)
                if not parsed:
                    continue
                info.loader = parsed.get("loader") or loader
                info.mod_id = parsed.get("mod_id") or ""
                info.name = parsed.get("name") or info.mod_id
                info.version = parsed.get("version") or ""
                info.mc_dep = parsed.get("mc_dep") or ""
                info.deps = parsed.get("deps") or []
                break

            if not info.mod_id and not info.name and _MANIFEST in names:
                payload = _read_entry(zf, _MANIFEST)
                if payload:
                    mf = _parse_manifest(_text(payload))
                    title = mf.get("implementation-title") or mf.get("specification-title") or ""
                    info.name = title
                    info.version = (mf.get("implementation-version")
                                    or mf.get("specification-version") or "")
                    info.mod_id = _sanitize_id(title)
                    if any(k in mf for k in ("fmlmodtype", "tweakclass", "fmlcoreplugin")):
                        info.loader = "forge"

            if with_nested:
                provided = _nested_ids(zf)

            if not info.name:
                info.name = os.path.splitext(name)[0]
    except zipfile.BadZipFile as e:
        info.bad = f"不是有效的 zip/jar: {e}"
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        info.bad = f"元数据解析失败: {e}"
    except NotImplementedError as e:
        info.bad = f"用了不支持的压缩方式: {e}"
    except OSError as e:
        info.bad = f"无法读取: {e}"
    except Exception as e:      # 兜底：一个坏 jar 不能中断整次扫描
        info.bad = f"{type(e).__name__}: {e}"

    return info, provided


def _scan(mods_dir: str, with_nested: bool = False) -> tuple[list[ModInfo], set[str]]:
    infos: list[ModInfo] = []
    provided: set[str] = set()
    try:
        entries = sorted(f for f in os.listdir(mods_dir) if f.lower().endswith(".jar"))
    except OSError:
        return infos, provided
    for entry in entries:
        info, ids = _scan_one(os.path.join(mods_dir, entry), with_nested=with_nested)
        infos.append(info)
        provided |= ids
    return infos, provided


def scan_mods(mods_dir: str) -> list[ModInfo]:
    """扫描 mods 目录，返回每个 jar 的 mod 元数据（不联网、不解压）。"""
    if not mods_dir or not os.path.isdir(mods_dir):
        return []
    return _scan(mods_dir, with_nested=False)[0]


# ═══════════════════ 版本范围判定 ═══════════════════

_VER_RE = re.compile(r"^[vV]?([0-9]+(?:[._][0-9]+)*)")
_CLAUSE_RE = re.compile(r"^(\^|~|>=|<=|>|<|=)?\s*([0-9][0-9A-Za-z._+\-]*)$")


def _ver_tuple(text) -> Optional[tuple]:
    match = _VER_RE.match(str(text or "").strip())
    if not match:
        return None
    return tuple(int(x) for x in re.split(r"[._]", match.group(1)))


def _clause_ok(version: str, clause: str) -> bool:
    match = _CLAUSE_RE.match(clause.strip())
    if not match:
        return True          # 认不出的写法不报错：宁可漏报，也不制造假警报
    op = match.group(1) or "="
    vt = _ver_tuple(version)
    tt = _ver_tuple(match.group(2))
    if vt is None or tt is None:
        return True
    if op == "=":
        return vt[:len(tt)] == tt or tt[:len(vt)] == vt
    if op == ">=":
        return vt >= tt
    if op == "<=":
        return vt <= tt
    if op == ">":
        return vt > tt
    if op == "<":
        return vt < tt
    if op == "^":
        return vt >= tt and vt[:1] == tt[:1]
    if op == "~":
        return vt >= tt and vt[:2] == tt[:2]
    return True


def _maven_ok(version: str, spec: str) -> bool:
    """Maven 区间：[1.20.1]、[1.20,1.21)、(,1.21]、[47,)。"""
    body = spec.strip()
    if not body or body[0] not in "[(" or body[-1] not in "])":
        return True
    lower_open = body[0]
    upper_close = body[-1]
    inner = body[1:-1]
    if "," not in inner:
        return _clause_ok(version, "=" + inner.strip())

    low, _sep, high = inner.partition(",")
    low, high = low.strip(), high.strip()
    vt = _ver_tuple(version)
    if vt is None:
        return True
    if low:
        lt = _ver_tuple(low)
        if lt is not None:
            if lower_open == "[":
                if vt < lt:
                    return False
            elif vt <= lt:
                return False
    if high:
        ht = _ver_tuple(high)
        if ht is not None:
            if upper_close == "]":
                if vt > ht:
                    return False
            elif vt >= ht:
                return False
    return True


def _single_ok(version: str, spec: str) -> bool:
    spec = spec.strip()
    if not spec:
        return True
    if spec[0] in "[(":
        return _maven_ok(version, spec)
    clauses = [c for c in re.split(r"[\s,]+", spec) if c]
    return all(_clause_ok(version, c) for c in clauses)


def version_ok(version: str, spec: str) -> bool:
    """判断 version 是否落在 spec 里。

    支持 Maven 区间（[1.20.1,1.21)、[1.20.1]、[47,)）、Fabric/Quilt 风格
    （">=1.20 <1.21"、"*"）以及 "|" 分隔的多个备选。
    """
    spec = (spec or "").strip()
    # "0" 是 Forge 生态里 versionRange 的「不限制」写法，不是真的要求 0 版本
    if not spec or spec in ("*", "?", "any", "0"):
        return True
    alternatives = [p.strip() for p in spec.split("|") if p.strip()]
    if not alternatives:
        return True
    return any(_single_ok(version, alt) for alt in alternatives)


# ═══════════════════ 依赖检查 ═══════════════════

def check_mods(mods_dir: str, mc_version: str, loader: str = "") -> list[str]:
    """检查 mods 目录，返回人话问题列表（重复 modId / 缺前置 / MC 版本不符 / jar 损坏）。

    loader 是当前实例用的加载器（forge / neoforge / fabric / quilt），
    用于免掉平台占位依赖并标出加载器不匹配的 jar；传空串则跳过这两项。
    """
    if not mods_dir or not os.path.isdir(mods_dir):
        return [f"mods 目录不存在: {mods_dir}"]

    infos, nested = _scan(mods_dir, with_nested=True)
    problems: list[str] = []

    for info in infos:
        if info.bad:
            problems.append(f"[jar 损坏] {info.file}: {info.bad}")

    healthy = [m for m in infos if not m.bad]

    by_id: dict[str, list[ModInfo]] = {}
    for m in healthy:
        if m.mod_id:
            by_id.setdefault(m.mod_id.lower(), []).append(m)
    for mod_id, group in sorted(by_id.items()):
        if len(group) > 1:
            files = "、".join(m.file for m in group)
            problems.append(
                f"[重复 modId] {mod_id} 同时出现在 {len(group)} 个 jar 里: {files}"
            )

    available = {m.mod_id.lower() for m in healthy if m.mod_id} | nested | set(PLATFORM_IDS)

    mc_ver = str(mc_version or "").strip()
    if mc_ver:
        for m in healthy:
            if not m.mc_dep:
                continue
            if not version_ok(mc_ver, m.mc_dep):
                problems.append(
                    f"[MC 版本不符] {m.file}: 要求 Minecraft {m.mc_dep}，当前是 {mc_ver}"
                )

    for m in healthy:
        for dep in m.deps:
            if not dep.get("mandatory"):
                continue
            dep_id = str(dep.get("mod_id") or "").strip()
            if not dep_id or dep_id.lower() in available:
                continue
            rng = str(dep.get("version_range") or "*").strip()
            extra = "" if rng in ("", "*") else f"（要求 {rng}）"
            problems.append(f"[缺少前置] {m.file}: 需要 {dep_id}{extra}")

    target = (loader or "").strip().lower()
    if target:
        compatible = _COMPATIBLE_LOADERS.get(target, {target})
        for m in healthy:
            own = (m.loader or "").lower()
            if not own or own in compatible:
                continue
            problems.append(
                f"[加载器可能不符] {m.file}: 元数据是 {own} 的，当前实例是 {target}，可能无法加载"
            )

    return list(dict.fromkeys(problems))
