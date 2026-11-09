# === system.py ===
# Theo dõi tài nguyên máy: CPU, RAM, GPU, VRAM (qua nvidia-smi nếu có card NVIDIA).

import shutil
import subprocess
import time

import psutil

_gpu_cache = {"t": 0, "data": None}


def gpu_info():
    """[{name, used_mb, total_mb, util}] hoặc [] nếu không có GPU NVIDIA. Cache 3 giây."""
    if time.time() - _gpu_cache["t"] < 3:
        return _gpu_cache["data"] or []
    data = []
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run(
                [exe, "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            for line in out.strip().splitlines():
                name, used, total, util = [x.strip() for x in line.split(",")]
                data.append({"name": name, "used_mb": int(used), "total_mb": int(total), "util": int(util)})
        except Exception:
            data = []
    _gpu_cache.update(t=time.time(), data=data)
    return data


def snapshot():
    mem = psutil.virtual_memory()
    process = psutil.Process()
    ram = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            ram += child.memory_info().rss
        except psutil.Error:
            pass
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(),
        "ram_used_gb": round(mem.used / 1024 ** 3, 1),
        "ram_total_gb": round(mem.total / 1024 ** 3, 1),
        "ram_percent": mem.percent,
        "process_ram_gb": round(ram / 1024 ** 3, 2),
        "gpus": gpu_info(),
    }
