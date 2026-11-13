"""
Zero-Dependency Windows Hardware Profiler for DevListen.
Probes CPU, RAM, GPU, and Power/Battery state via native Win32 APIs and runtime probes
to dynamically recommend the optimal ASR speech engine tier without thermal throttling.
"""
import os
import sys
import ctypes
from dataclasses import dataclass
from typing import Optional, Tuple

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', ctypes.c_ulong),
        ('dwMemoryLoad', ctypes.c_ulong),
        ('ullTotalPhys', ctypes.c_ulonglong),
        ('ullAvailPhys', ctypes.c_ulonglong),
        ('ullTotalPageFile', ctypes.c_ulonglong),
        ('ullAvailPageFile', ctypes.c_ulonglong),
        ('ullTotalVirtual', ctypes.c_ulonglong),
        ('ullAvailVirtual', ctypes.c_ulonglong),
        ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
    ]

class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ('ACLineStatus', ctypes.c_byte),
        ('BatteryFlag', ctypes.c_byte),
        ('BatteryLifePercent', ctypes.c_byte),
        ('SystemStatusFlag', ctypes.c_byte),
        ('BatteryLifeTime', ctypes.c_ulong),
        ('BatteryFullLifeTime', ctypes.c_ulong),
    ]

@dataclass
class HardwareProfile:
    cpu_cores: int
    total_ram_gb: float
    avail_ram_gb: float
    on_ac_power: bool
    battery_pct: int
    has_cuda: bool
    gpu_name: str
    gpu_vram_gb: float
    recommended_tier: str
    recommended_model: str
    tier_label: str
    reason: str

TIER_1_ECO = "tier_1_eco"
TIER_2_BALANCED = "tier_2_balanced"
TIER_3_WORKSTATION = "tier_3_workstation"
TIER_4_CLOUD = "tier_4_cloud"

def probe_hardware() -> HardwareProfile:
    """Probes local machine hardware specifications and returns a HardwareProfile."""
    # 1. CPU
    cpu_cores = os.cpu_count() or 4

    # 2. RAM via Win32 GlobalMemoryStatusEx
    total_ram_gb = 8.0
    avail_ram_gb = 4.0
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_ram_gb = round(stat.ullTotalPhys / (1024**3), 1)
            avail_ram_gb = round(stat.ullAvailPhys / (1024**3), 1)
    except Exception:
        pass

    # 3. Power State via Win32 GetSystemPowerStatus
    on_ac_power = True
    battery_pct = 100
    try:
        sps = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
            on_ac_power = (sps.ACLineStatus == 1)
            if sps.BatteryLifePercent != 255:
                battery_pct = int(sps.BatteryLifePercent)
    except Exception:
        pass

    # 4. GPU & CUDA Detection
    has_cuda = False
    gpu_name = "Integrated / CPU"
    gpu_vram_gb = 0.0

    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            has_cuda = True
    except Exception:
        pass

    # Check via torch if available, or fallback to nvidia-smi quick probe
    if has_cuda or True:
        try:
            import subprocess
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if res.returncode == 0 and res.stdout.strip():
                line = res.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gpu_name = parts[0]
                    gpu_vram_gb = round(float(parts[1]) / 1024.0, 1)
                    has_cuda = True
        except Exception:
            pass

    # 5. Determine Recommended Tier
    # If on battery power, recommend Eco Tier to conserve laptop battery
    if not on_ac_power and battery_pct < 60:
        tier = TIER_1_ECO
        model = "SenseVoice-Small INT8"
        label = "Eco (Battery Safe)"
        reason = f"Battery mode ({battery_pct}%), running 138ms ultra-lightweight engine to prevent thermal drain"
    elif has_cuda and gpu_vram_gb >= 6.0:
        tier = TIER_3_WORKSTATION
        model = "Whisper Large-v3 Turbo (CUDA)"
        label = "Workstation Turbo"
        reason = f"Dedicated GPU detected ({gpu_name}, {gpu_vram_gb}GB VRAM), running max-fidelity model"
    elif cpu_cores >= 6 and total_ram_gb >= 12.0:
        tier = TIER_2_BALANCED
        model = "NVIDIA Parakeet-TDT 0.6B / SenseVoice"
        label = "Balanced SOTA"
        reason = f"Multi-core CPU ({cpu_cores}T) + {total_ram_gb}GB RAM + {gpu_name}, running sub-200ms FastConformer"
    else:
        tier = TIER_1_ECO
        model = "SenseVoice-Small INT8"
        label = "Eco / Ultra-Light"
        reason = f"Resource-conserving profile for {cpu_cores} cores, {total_ram_gb}GB RAM"

    return HardwareProfile(
        cpu_cores=cpu_cores,
        total_ram_gb=total_ram_gb,
        avail_ram_gb=avail_ram_gb,
        on_ac_power=on_ac_power,
        battery_pct=battery_pct,
        has_cuda=has_cuda,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        recommended_tier=tier,
        recommended_model=model,
        tier_label=label,
        reason=reason
    )

if __name__ == "__main__":
    prof = probe_hardware()
    print("=== DevListen Hardware Profiler ===")
    print(f"CPU: {prof.cpu_cores} threads")
    print(f"RAM: {prof.total_ram_gb} GB (Available: {prof.avail_ram_gb} GB)")
    print(f"Power: {'AC Wall Power' if prof.on_ac_power else 'Battery'} ({prof.battery_pct}%)")
    print(f"GPU: {prof.gpu_name} ({prof.gpu_vram_gb} GB VRAM) [CUDA: {prof.has_cuda}]")
    print(f"Recommended Tier: {prof.tier_label} [{prof.recommended_tier}]")
    print(f"Model: {prof.recommended_model}")
    print(f"Reason: {prof.reason}")
