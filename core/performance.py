"""系统性能检测 + JVM 参数自动调优。

以前这里是「有 mod / 没 mod」两档拍脑袋。现在按四件事算，并且把依据一起返回，
让界面能解释给用户听：

    1. 机器：物理内存、核心数
    2. 版本：Minecraft 版本号（1.7.10 和 1.21 的堆需求差一倍多）
    3. 加载器：Forge/NeoForge 自身就吃掉几百 MB，Fabric 轻一些
    4. mod 数量：整合包和原版不是一个量级

几条写在这里免得以后又改回去的经验：
  * 堆不是越大越好。MC 的 GC 停顿随堆线性变长，超过 12 GB 基本是负收益，
    1.12.2 时代的大整合包给到 8 GB 反而比 12 GB 稳。
  * 不要加 -XX:+DisableExplicitGC。Netty（MC 的网络层）靠 System.gc() 回收
    直接内存，禁掉以后 native 内存只涨不降，表现为"越玩越吃内存"。
  * -XX:+AlwaysPreTouch 能减少运行时缺页，但会把预留内存立刻吃满，
    只在 4 GB 以上堆、且用户内存宽裕时才加。
  * Java 8 的 G1 从 8u40 起可用；G1NewSizePercent 这类百分比参数在
    老版本属于实验参数，要 UnlockExperimentalVMOptions。
"""

import os
import platform

# 堆上限：再大只会拉长 GC 停顿
HARD_MAX_MB = 12288
# 老版本（1.13 之前）的 Forge 大整合包堆越大越不稳，压一手
LEGACY_CAP_MB = 8192


def get_system_info() -> dict:
    """检测系统硬件信息。"""
    import ctypes

    total_ram_mb = 0
    free_ram_mb = 0
    cpu_cores = os.cpu_count() or 4

    if platform.system() == "Windows":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
            total_ram_mb = mem.ullTotalPhys // (1024 * 1024)
            free_ram_mb = mem.ullAvailPhys // (1024 * 1024)
        except Exception:
            total_ram_mb = 8192
            free_ram_mb = 4096
    else:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        total_ram_mb = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable"):
                        free_ram_mb = int(line.split()[1]) // 1024
        except Exception:
            total_ram_mb = 8192
            free_ram_mb = 4096

    return {
        "total_ram_mb": total_ram_mb,
        "free_ram_mb": free_ram_mb,
        "cpu_cores": cpu_cores,
        "os": platform.system(),
        "arch": platform.machine(),
    }


# ═══════════════════ 版本 / mod 数 ═══════════════════

def count_mod_jars(*dirs) -> int:
    """数一数 mods 目录里的 jar（含 1.7.10 那种 mods/<版本>/ 子目录）。"""
    seen = 0
    for base in dirs:
        if not base or not os.path.isdir(base):
            continue
        try:
            for root, _dirs, files in os.walk(base):
                depth = root[len(base):].count(os.sep)
                if depth > 2:
                    _dirs[:] = []
                    continue
                seen += sum(1 for f in files if f.lower().endswith(".jar"))
        except OSError:
            continue
        if seen:
            break
    return seen


def _version_tuple(text: str) -> tuple:
    parts = []
    for chunk in str(text or "").replace("_", ".").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
    return tuple(parts) or (0,)


# ═══════════════════ 调优 ═══════════════════

class Profile:
    """调优输入。字段都可缺省，缺了就当"不知道"，按保守值算。"""

    def __init__(self, total_ram_mb=8192, cpu_cores=4, mc_version="",
                 loader="", mod_count=0, java_major=17):
        self.total_ram_mb = int(total_ram_mb or 8192)
        self.cpu_cores = int(cpu_cores or 4)
        self.mc_version = str(mc_version or "")
        self.loader = str(loader or "")
        self.mod_count = int(mod_count or 0)
        self.java_major = int(java_major or 17)

    def __repr__(self):
        return ("Profile(%dMB/%d核, mc=%s, loader=%s, mods=%d, java=%d)"
                % (self.total_ram_mb, self.cpu_cores, self.mc_version or "?",
                   self.loader or "vanilla", self.mod_count, self.java_major))


def build_profile(total_ram_mb=0, cpu_cores=0, mc_version="", loader="",
                  mod_count=0, java_major=17) -> Profile:
    if not total_ram_mb or not cpu_cores:
        info = get_system_info()
        total_ram_mb = total_ram_mb or info["total_ram_mb"]
        cpu_cores = cpu_cores or info["cpu_cores"]
    return Profile(total_ram_mb, cpu_cores, mc_version, loader, mod_count, java_major)


def calc_ram(profile: Profile):
    """返回 (min_mb, max_mb, notes)。notes 是给人看的理由。"""
    notes = []
    mods = profile.mod_count
    if mods <= 0:
        base = 2048 if _version_tuple(profile.mc_version) >= (1, 13) else 1536
        notes.append("没有 mod，%s" % ("现代版本按 2 GB" if base == 2048 else "老版本 1.5 GB 够用"))
    elif mods <= 20:
        base = 3072
        notes.append("%d 个 mod，属于轻量整合" % mods)
    elif mods <= 80:
        base = 4096
        notes.append("%d 个 mod，中量整合包" % mods)
    elif mods <= 150:
        base = 6144
        notes.append("%d 个 mod，重量级整合包" % mods)
    else:
        base = 8192
        notes.append("%d 个 mod，大型整合包" % mods)

    if profile.loader in ("forge", "neoforge"):
        base += 512
        notes.append("%s 自身要吃掉几百 MB" % profile.loader.capitalize())
    elif profile.loader in ("quilt",):
        base += 256
        notes.append("Quilt 比 Fabric 略重")

    cap = max(2048, profile.total_ram_mb // 2)
    if profile.total_ram_mb <= 8192:
        cap = min(cap, 4096)
        notes.append("机器只有 %d GB，最多给一半" % (profile.total_ram_mb // 1024))

    hard = HARD_MAX_MB
    if profile.mc_version and _version_tuple(profile.mc_version) < (1, 13):
        hard = LEGACY_CAP_MB
        if base > hard:
            notes.append("1.13 之前堆给太大 GC 停顿反而更长，压到 %d GB" % (hard // 1024))

    max_mb = min(base, cap, hard)
    max_mb = max(max_mb, 1024)
    max_mb = (max_mb // 256) * 256

    min_mb = max(512, max_mb // 2)
    min_mb = (min_mb // 256) * 256 or 512
    return min_mb, max_mb, notes


def build_args(profile: Profile):
    """返回 (jvm_args, notes)。"""
    min_mb, max_mb, ram_notes = calc_ram(profile)
    notes = list(ram_notes)
    args = ["-Xms%dM" % min_mb, "-Xmx%dM" % max_mb]

    java = profile.java_major
    args.append("-XX:+UseG1GC")
    args.append("-XX:MaxGCPauseMillis=50")
    args.append("-XX:+ParallelRefProcEnabled")
    notes.append("GC 用 G1，目标停顿 50ms（Java %d）" % java)

    if max_mb >= 4096:
        args.append("-XX:G1HeapRegionSize=16M")
    elif max_mb >= 2048:
        args.append("-XX:G1HeapRegionSize=8M")

    if java >= 11:
        # 这几个 G1 百分比参数在老 JDK 里是实验参数，得先解锁
        args.append("-XX:+UnlockExperimentalVMOptions")
        args.extend([
            "-XX:G1NewSizePercent=30",
            "-XX:G1MaxNewSizePercent=40",
            "-XX:G1ReservePercent=20",
            "-XX:G1HeapWastePercent=5",
            "-XX:G1MixedGCCountTarget=4",
            "-XX:InitiatingHeapOccupancyPercent=15",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:SurvivorRatio=32",
            "-XX:MaxTenuringThreshold=1",
            "-XX:+PerfDisableSharedMem",
        ])
        notes.append("补上社区验证过的 G1 细分参数（Aikar 那一套）")

    if max_mb >= 4096 and profile.total_ram_mb >= max_mb * 2:
        args.append("-XX:+AlwaysPreTouch")
        notes.append("堆 ≥4 GB 且机器宽裕，预触碰内存页减少运行时抖动")

    gc_threads = max(1, min(profile.cpu_cores, 4))
    args.append("-XX:ParallelGCThreads=%d" % gc_threads)
    args.append("-XX:ConcGCThreads=%d" % max(1, gc_threads // 2))

    if profile.loader in ("forge", "neoforge"):
        args.append("-Dfml.ignoreInvalidMinecraftCertificates=true")
        args.append("-Dfml.ignorePatchDiscrepancies=true")

    # 注意：不加 -XX:+DisableExplicitGC —— Netty 靠 System.gc() 回收直接内存
    return args, notes


def explain(profile: Profile) -> str:
    """多行可读说明，给设置页和实例详情页用。"""
    min_mb, max_mb, notes = calc_ram(profile)
    lines = [
        "机器 %d GB / %d 核　·　%s%s　·　%d 个 mod　·　Java %d"
        % (profile.total_ram_mb // 1024, profile.cpu_cores,
           profile.mc_version or "版本未知",
           (" + " + profile.loader.capitalize()) if profile.loader else "",
           profile.mod_count, profile.java_major),
        "内存 %d MB ~ %d MB" % (min_mb, max_mb),
    ]
    for n in notes:
        lines.append("· " + n)
    return "\n".join(lines)


def preview_rows(total_ram_mb: int, cpu_cores: int) -> list:
    """在这台机器上，几种典型组合各会分到多少内存。设置页用它做说明。"""
    cases = (
        ("原版（新版本）", "1.21.1", "", 0),
        ("原版（老版本）", "1.12.2", "", 0),
        ("轻量整合", "1.20.1", "fabric", 15),
        ("中量整合", "1.12.2", "forge", 60),
        ("大型整合", "1.12.2", "forge", 200),
    )
    rows = []
    for label, mc, loader, mods in cases:
        profile = build_profile(total_ram_mb, cpu_cores, mc, loader, mods, 17)
        min_mb, max_mb, _notes = calc_ram(profile)
        rows.append((label, min_mb, max_mb))
    return rows


# ═══════════════════ 兼容旧签名 ═══════════════════

def calc_optimal_ram(total_mb: int, has_mods: bool = False) -> tuple:
    """旧接口：只分有 mod / 没 mod。新代码请用 build_profile + calc_ram。"""
    profile = Profile(total_ram_mb=total_mb, mod_count=40 if has_mods else 0)
    min_mb, max_mb, _ = calc_ram(profile)
    return min_mb, max_mb


def generate_jvm_args(total_ram_mb: int, cpu_cores: int,
                      has_mods: bool = False,
                      java_major: int = 17) -> list:
    """旧接口：返回参数列表。新代码请用 build_profile + build_args。"""
    profile = Profile(total_ram_mb=total_ram_mb, cpu_cores=cpu_cores,
                      mod_count=40 if has_mods else 0, java_major=java_major)
    args, _notes = build_args(profile)
    return args


def get_optimization_summary(sys_info: dict, has_mods: bool = False) -> str:
    """旧接口：可读摘要。"""
    profile = Profile(total_ram_mb=sys_info.get("total_ram_mb", 8192),
                      cpu_cores=sys_info.get("cpu_cores", 4),
                      mod_count=40 if has_mods else 0)
    return explain(profile)
