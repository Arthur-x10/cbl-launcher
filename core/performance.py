"""系统性能检测 + JVM 参数智能优化。

自动检测 RAM/CPU，根据系统配置 + 游戏版本（原版/Mod）
生成最优 JVM 参数，让 Minecraft 流畅运行。
"""

import os
import platform


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


def calc_optimal_ram(total_mb: int, has_mods: bool = False) -> tuple[int, int]:
    """计算最优内存分配 (min_mb, max_mb)。

    规则:
    - 不超过系统总内存的 50%（留给 OS）
    - 有 Mod 时额外 +1~2GB
    - 最低 1GB，最高 12GB（MC 超过 12GB 反而 GC 压力大）
    """
    if total_mb <= 4096:
        base = 1536
    elif total_mb <= 8192:
        base = 3072
    elif total_mb <= 16384:
        base = 6144
    elif total_mb <= 32768:
        base = 8192
    else:
        base = 10240

    if has_mods:
        base = min(base + 2048, 12288)

    cap = total_mb // 2
    max_mb = min(base, cap, 12288)
    max_mb = max(max_mb, 1024)

    min_mb = max(512, max_mb // 4)

    return min_mb, max_mb


def generate_jvm_args(total_ram_mb: int, cpu_cores: int,
                      has_mods: bool = False,
                      java_major: int = 17) -> list[str]:
    """生成优化的 JVM 参数列表。"""
    min_mb, max_mb = calc_optimal_ram(total_ram_mb, has_mods)
    args = [f"-Xms{min_mb}M", f"-Xmx{max_mb}M"]

    args.append("-XX:+UseG1GC")
    args.append("-XX:MaxGCPauseMillis=50")
    args.append("-XX:+ParallelRefProcEnabled")
    args.append("-XX:+DisableExplicitGC")

    if max_mb >= 4096:
        args.append("-XX:G1HeapRegionSize=16M")
    elif max_mb >= 2048:
        args.append("-XX:G1HeapRegionSize=8M")

    if java_major >= 11:
        args.append("-XX:+UnlockExperimentalVMOptions")
        args.append("-XX:G1NewSizePercent=30")
        args.append("-XX:G1MaxNewSizePercent=40")
        args.append("-XX:G1ReservePercent=20")

    gc_threads = min(cpu_cores, 4)
    args.append(f"-XX:ParallelGCThreads={gc_threads}")
    args.append(f"-XX:ConcGCThreads={max(1, gc_threads // 2)}")

    args.append("-Dfml.ignoreInvalidMinecraftCertificates=true")
    args.append("-Dfml.ignorePatchDiscrepancies=true")

    return args


def get_optimization_summary(sys_info: dict, has_mods: bool = False) -> str:
    """生成可读的优化摘要。"""
    total = sys_info["total_ram_mb"]
    cores = sys_info["cpu_cores"]
    min_mb, max_mb = calc_optimal_ram(total, has_mods)

    lines = [
        f"系统: {total // 1024}GB RAM / {cores} 核心",
        f"分配: {min_mb}MB ~ {max_mb}MB",
        f"GC: G1GC (目标暂停 ≤50ms)",
        f"GC 线程: {min(cores, 4)} 并行 / {max(1, min(cores, 4) // 2)} 并发",
        f"Mod 优化: {'是' if has_mods else '否'}",
    ]
    return "\n".join(lines)
