"""
Apollo Agent V1.7.R - Infrastructure Scanner
==============================================

Collecte les données hardware du serveur local :
- Disques physiques (type HDD/SSD/NVMe, modèle, taille, bus)
- Configuration RAID software (md, Storage Spaces, ZFS)
- Débit réseau (interface principale)
- Agents de sauvegarde détectés (présence uniquement)
- Données SMART basiques si disponibles sans outil externe

ZERO DEPENDANCE EXTERNE : utilise uniquement les API natives OS.
- Linux : /sys, /proc, lsblk, ethtool
- Windows : WMI / PowerShell (Get-PhysicalDisk, Get-StoragePool, etc.)
- macOS : diskutil, system_profiler, networksetup

TIMEOUT : 30 secondes max pour la collecte complète.
AGENT = COLLECTE UNIQUEMENT : scores=None, ZERO calcul.

Sprint 101 — Server Risk & Infrastructure Scanner
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

import json
import logging
import os
import platform
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for each subprocess call (seconds)
_CMD_TIMEOUT = 10

# Overall scan timeout (seconds)
_SCAN_TIMEOUT = 30


def _run_cmd(cmd: List[str], timeout: int = _CMD_TIMEOUT) -> Optional[str]:
    """Run a subprocess command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _run_powershell(script: str, timeout: int = _CMD_TIMEOUT) -> Optional[str]:
    """Run a PowerShell command (Windows only)."""
    return _run_cmd(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )


# =============================================================================
# DISK COLLECTION
# =============================================================================

def _classify_disk_linux(rota, tran: str, model: str) -> str:
    """
    Classify disk type using cascade: TRAN > ROTA > model name.

    Best practice cross-platform:
    - ROTA=0 + TRAN=nvme  → NVMe SSD
    - ROTA=0 + TRAN=sata  → SATA SSD
    - ROTA=1              → HDD
    - Fallback: grep "SSD" in model name
    """
    tran = tran.lower()
    model_lower = (model or "").lower()

    # Priority 1: transport type
    if tran == "nvme":
        return "NVMe"

    # Priority 2: rotational flag
    if rota is False or rota == "0" or rota == 0:
        return "SSD"
    if rota is True or rota == "1" or rota == 1:
        # Double-check: some SSDs behind RAID controllers report ROTA=1
        if "ssd" in model_lower or "nvme" in model_lower:
            return "SSD"
        return "HDD"

    # Priority 3: model name fallback
    if "ssd" in model_lower:
        return "SSD"
    if "nvme" in model_lower:
        return "NVMe"

    return "Unknown"


def _collect_disks_linux() -> List[Dict[str, Any]]:
    """
    Collect physical disk info on Linux.

    Cascade:
    1. lsblk -J -d (JSON, physical disks only, structured parsing)
    2. Fallback: /sys/block/*/queue/rotational + /sys/block/*/device/model
    """
    # --- Method 1: lsblk -J -d (preferred) ---
    output = _run_cmd([
        "lsblk", "-J", "-d", "-o",
        "NAME,TYPE,SIZE,ROTA,MODEL,SERIAL,TRAN",
    ])

    if output:
        try:
            data = json.loads(output)
            disks = []
            for dev in data.get("blockdevices", []):
                if dev.get("type") != "disk":
                    continue

                model = (dev.get("model") or "").strip()
                tran = (dev.get("tran") or "")
                disk_type = _classify_disk_linux(dev.get("rota"), tran, model)

                # Read firmware from /sys if available
                firmware = ""
                dev_name = dev.get("name", "")
                fw_path = f"/sys/block/{dev_name}/device/firmware_rev"
                try:
                    with open(fw_path, "r") as f:
                        firmware = f.read().strip()
                except (FileNotFoundError, PermissionError):
                    pass

                disks.append({
                    "name": dev_name,
                    "type": disk_type,
                    "model": model,
                    "serial": (dev.get("serial") or "").strip(),
                    "size": dev.get("size", ""),
                    "bus": tran.lower() or "unknown",
                    "firmware": firmware,
                })
            if disks:
                return disks
        except json.JSONDecodeError:
            pass

    # --- Method 2: /sys fallback (no lsblk or parse failure) ---
    disks = []
    try:
        for dev_name in os.listdir("/sys/block"):
            # Only physical disks (sd*, nvme*, hd*, vd*)
            if not dev_name.startswith(("sd", "nvme", "hd", "vd")):
                continue

            dev_base = f"/sys/block/{dev_name}"

            # Read rotational
            rota = None
            rota_path = f"{dev_base}/queue/rotational"
            try:
                with open(rota_path, "r") as f:
                    rota = int(f.read().strip())
            except (FileNotFoundError, PermissionError, ValueError):
                pass

            # Read model
            model = ""
            model_path = f"{dev_base}/device/model"
            try:
                with open(model_path, "r") as f:
                    model = f.read().strip()
            except (FileNotFoundError, PermissionError):
                pass

            # Read size (in 512-byte sectors)
            size_str = ""
            size_path = f"{dev_base}/size"
            try:
                with open(size_path, "r") as f:
                    sectors = int(f.read().strip())
                    size_gb = (sectors * 512) / (1024 ** 3)
                    size_str = f"{size_gb:.1f}G"
            except (FileNotFoundError, PermissionError, ValueError):
                pass

            # Detect transport
            tran = ""
            if dev_name.startswith("nvme"):
                tran = "nvme"
            elif os.path.exists(f"{dev_base}/device/transport"):
                try:
                    with open(f"{dev_base}/device/transport", "r") as f:
                        tran = f.read().strip().lower()
                except (FileNotFoundError, PermissionError):
                    pass

            disk_type = _classify_disk_linux(rota, tran, model)

            # Read firmware revision
            firmware = ""
            fw_path = f"{dev_base}/device/firmware_rev"
            try:
                with open(fw_path, "r") as f:
                    firmware = f.read().strip()
            except (FileNotFoundError, PermissionError):
                pass

            disks.append({
                "name": dev_name,
                "type": disk_type,
                "model": model,
                "serial": "",
                "size": size_str,
                "bus": tran or "unknown",
                "firmware": firmware,
            })
    except (PermissionError, OSError):
        pass

    return disks


def _classify_disk_windows(media_type: str, bus_type: str, friendly_name: str, model: str) -> str:
    """
    Classify disk type on Windows.

    Cascade:
    1. MediaType from Get-PhysicalDisk (SSD/HDD)
    2. BusType (NVMe → NVMe SSD)
    3. Fallback if Unspecified: grep "SSD" in FriendlyName/Model

    Piege Windows: MediaType retourne parfois "Unspecified" pour disques
    amovibles ou certains controleurs RAID.
    """
    media = str(media_type).strip()
    bus = str(bus_type).strip()
    name_lower = (friendly_name or "").lower()
    model_lower = (model or "").lower()

    # Priority 1: MediaType (numeric: 3=HDD, 4=SSD; or string)
    if media == "4" or media == "SSD":
        # NVMe SSD vs SATA SSD
        if "NVMe" in bus:
            return "NVMe"
        return "SSD"
    if media == "3" or media == "HDD":
        return "HDD"

    # Priority 2: BusType
    if "NVMe" in bus:
        return "NVMe"

    # Priority 3: Fallback for Unspecified — grep model/name
    if "ssd" in name_lower or "ssd" in model_lower:
        return "SSD"
    if "nvme" in name_lower or "nvme" in model_lower:
        return "NVMe"
    if "hdd" in name_lower or "hdd" in model_lower:
        return "HDD"

    return "Unknown"


def _collect_disks_windows() -> List[Dict[str, Any]]:
    """
    Collect physical disk info on Windows via Get-PhysicalDisk.

    Get-PhysicalDisk returns: FriendlyName, MediaType, BusType, Size,
    HealthStatus, SerialNumber, Model, FirmwareVersion.
    """
    script = (
        "Get-PhysicalDisk | Select-Object "
        "DeviceId, FriendlyName, MediaType, Size, HealthStatus, BusType, "
        "Model, SerialNumber, FirmwareVersion "
        "| ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    if not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    # PowerShell returns a single object if only one disk
    if isinstance(data, dict):
        data = [data]

    disks = []
    for d in data:
        friendly = str(d.get("FriendlyName", "")).strip()
        model = str(d.get("Model", "")).strip()
        bus = str(d.get("BusType", "")).strip()
        media = str(d.get("MediaType", "")).strip()

        disk_type = _classify_disk_windows(media, bus, friendly, model)

        size_bytes = d.get("Size", 0)
        try:
            size_bytes = int(size_bytes)
        except (ValueError, TypeError):
            size_bytes = 0

        size_str = f"{size_bytes / (1024**3):.1f}G" if size_bytes > 0 else ""

        disks.append({
            "name": str(d.get("DeviceId", "")),
            "friendly_name": friendly,
            "type": disk_type,
            "model": model,
            "serial": str(d.get("SerialNumber", "")).strip(),
            "size": size_str,
            "size_bytes": size_bytes,
            "bus": bus,
            "health": str(d.get("HealthStatus", "")).strip(),
            "firmware": str(d.get("FirmwareVersion", "")).strip(),
        })

    return disks


def _collect_disks_macos() -> List[Dict[str, Any]]:
    """
    Collect physical disk info on macOS.

    Cascade:
    1. diskutil list → get physical disk identifiers
    2. diskutil info -plist diskX → per-disk details (protocol, medium type, model)
    3. system_profiler SPNVMeDataType -json → NVMe-specific details
    4. system_profiler SPStorageDataType -json → fallback for all storage
    """
    import plistlib

    disks = []

    # --- Step 1: Get list of whole disks via diskutil list -plist ---
    list_output = _run_cmd(["diskutil", "list", "-plist"])
    whole_disks = []
    if list_output:
        try:
            plist = plistlib.loads(list_output.encode("utf-8"))
            whole_disks = plist.get("WholeDisks", [])
        except Exception:
            pass

    # --- Step 2: Get details per disk via diskutil info -plist ---
    if whole_disks:
        for disk_id in whole_disks:
            info_output = _run_cmd(["diskutil", "info", "-plist", disk_id])
            if not info_output:
                continue

            try:
                info = plistlib.loads(info_output.encode("utf-8"))
            except Exception:
                continue

            # Skip virtual/synthesized disks (APFS containers, CoreStorage)
            virtual = info.get("VirtualOrPhysical", "")
            if virtual == "Virtual":
                continue

            model = info.get("MediaName", info.get("IORegistryEntryName", ""))
            protocol = info.get("DeviceProtocol", "")
            medium = info.get("SolidState", None)  # True/False
            size_bytes = info.get("TotalSize", info.get("Size", 0))
            bus = info.get("BusProtocol", protocol)

            # Classify
            protocol_lower = (protocol or "").lower()
            bus_lower = (bus or "").lower()
            model_lower = (model or "").lower()

            if "nvme" in protocol_lower or "nvme" in bus_lower:
                disk_type = "NVMe"
            elif medium is True:
                disk_type = "SSD"
            elif medium is False:
                # Double-check model name (some USB SSDs report SolidState=False)
                if "ssd" in model_lower:
                    disk_type = "SSD"
                else:
                    disk_type = "HDD"
            elif "apple ssd" in model_lower or "apple fabric" in protocol_lower:
                disk_type = "NVMe"  # Apple silicon SSDs are NVMe
            elif "ssd" in model_lower:
                disk_type = "SSD"
            else:
                disk_type = "Unknown"

            try:
                size_bytes = int(size_bytes)
            except (ValueError, TypeError):
                size_bytes = 0

            disks.append({
                "name": disk_id,
                "type": disk_type,
                "model": model.strip(),
                "serial": "",
                "size": f"{size_bytes / (1024**3):.1f}G" if size_bytes > 0 else "",
                "size_bytes": size_bytes,
                "bus": bus or protocol or "unknown",
            })

        if disks:
            return disks

    # --- Step 3: Fallback to system_profiler SPNVMeDataType + SPStorageDataType ---
    # NVMe specific data
    nvme_models = set()
    nvme_output = _run_cmd(["system_profiler", "SPNVMeDataType", "-json"])
    if nvme_output:
        try:
            nvme_data = json.loads(nvme_output)
            for item in nvme_data.get("SPNVMeDataType", []):
                model = item.get("device_model", item.get("_name", ""))
                nvme_models.add(model.lower())
                size_str = item.get("size", "")
                disks.append({
                    "name": item.get("bsd_name", ""),
                    "type": "NVMe",
                    "model": model.strip(),
                    "serial": item.get("device_serial", ""),
                    "size": size_str,
                    "bus": "NVMe",
                })
        except json.JSONDecodeError:
            pass

    # Storage overview (catches USB drives, etc.)
    sp_output = _run_cmd(["system_profiler", "SPStorageDataType", "-json"])
    if sp_output:
        try:
            sp_data = json.loads(sp_output)
            seen_models = set()
            for store in sp_data.get("SPStorageDataType", []):
                phys = store.get("physical_drive", {})
                model = phys.get("device_name", "")
                if not model or model.lower() in seen_models:
                    continue
                # Skip if already found via NVMe profiler
                if model.lower() in nvme_models:
                    continue
                seen_models.add(model.lower())

                medium = store.get("spstorage_medium_type", "")
                protocol = phys.get("protocol", "")
                model_lower = model.lower()

                if medium == "Solid State" or "ssd" in model_lower:
                    disk_type = "SSD"
                else:
                    disk_type = "HDD"

                size_bytes = store.get("size_in_bytes", 0)
                try:
                    size_bytes = int(size_bytes)
                except (ValueError, TypeError):
                    size_bytes = 0

                disks.append({
                    "name": store.get("bsd_name", ""),
                    "type": disk_type,
                    "model": model.strip(),
                    "serial": "",
                    "size": f"{size_bytes / (1024**3):.1f}G" if size_bytes > 0 else "",
                    "size_bytes": size_bytes,
                    "bus": protocol or "unknown",
                })
        except json.JSONDecodeError:
            pass

    return disks


def collect_disks() -> List[Dict[str, Any]]:
    """Collect physical disk information (multi-OS)."""
    system = platform.system()
    if system == "Linux":
        return _collect_disks_linux()
    elif system == "Windows":
        return _collect_disks_windows()
    elif system == "Darwin":
        return _collect_disks_macos()
    return []


# =============================================================================
# RAID DETECTION
# =============================================================================

def _detect_raid_linux() -> Optional[Dict[str, Any]]:
    """Detect software RAID on Linux (md, ZFS)."""
    # Check mdadm (Linux software RAID)
    mdstat = None
    try:
        with open("/proc/mdstat", "r") as f:
            mdstat = f.read().strip()
    except (FileNotFoundError, PermissionError):
        pass

    if mdstat and "md" in mdstat:
        arrays = []
        for line in mdstat.split("\n"):
            if line.startswith("md"):
                parts = line.split(":")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    detail = parts[1].strip()
                    # Extract RAID level
                    level = ""
                    for token in detail.split():
                        if token.startswith("raid"):
                            level = token
                            break
                    arrays.append({
                        "name": name,
                        "level": level,
                        "detail": detail,
                    })
        if arrays:
            return {
                "type": "md",
                "arrays": arrays,
                "raw": mdstat,
            }

    # Check ZFS
    zpool_output = _run_cmd(["zpool", "status"])
    if zpool_output and "pool:" in zpool_output:
        return {
            "type": "zfs",
            "raw": zpool_output[:2000],  # Limit output size
        }

    return None


def _detect_raid_windows() -> Optional[Dict[str, Any]]:
    """Detect Storage Spaces on Windows."""
    script = (
        "Get-StoragePool | Where-Object { $_.IsPrimordial -eq $false } "
        "| Select-Object FriendlyName, HealthStatus, OperationalStatus, Size "
        "| ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    if not output or output == "":
        return None

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        data = [data]

    if not data:
        return None

    return {
        "type": "storage_spaces",
        "pools": data,
    }


def detect_raid() -> Optional[Dict[str, Any]]:
    """Detect software RAID configuration (multi-OS)."""
    system = platform.system()
    if system == "Linux":
        return _detect_raid_linux()
    elif system == "Windows":
        return _detect_raid_windows()
    # macOS: APFS RAID is rare in server context, skip for V1
    return None


# =============================================================================
# NETWORK SPEED
# =============================================================================

def _get_network_linux() -> Dict[str, Any]:
    """Get network interface speed on Linux."""
    result = {"speed_mbps": None, "type": "unknown", "interface": ""}

    # Find the default route interface
    route_output = _run_cmd(["ip", "route", "show", "default"])
    if route_output:
        # "default via 192.168.1.1 dev eth0 ..."
        parts = route_output.split()
        try:
            dev_idx = parts.index("dev")
            iface = parts[dev_idx + 1]
            result["interface"] = iface
        except (ValueError, IndexError):
            pass

    iface = result["interface"]
    if not iface:
        return result

    # Read speed from /sys
    speed_path = f"/sys/class/net/{iface}/speed"
    try:
        with open(speed_path, "r") as f:
            speed = int(f.read().strip())
            if speed > 0:
                result["speed_mbps"] = speed
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    # Detect type (Ethernet vs WiFi)
    wireless_path = f"/sys/class/net/{iface}/wireless"
    if os.path.exists(wireless_path):
        result["type"] = "WiFi"
    else:
        # Check if it looks like ethernet
        type_path = f"/sys/class/net/{iface}/type"
        try:
            with open(type_path, "r") as f:
                net_type = int(f.read().strip())
                if net_type == 1:
                    result["type"] = "Ethernet"
        except (FileNotFoundError, PermissionError, ValueError):
            pass

    return result


def _get_network_windows() -> Dict[str, Any]:
    """Get network interface speed on Windows."""
    result = {"speed_mbps": None, "type": "unknown", "interface": ""}

    script = (
        "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } "
        "| Sort-Object -Property LinkSpeed -Descending "
        "| Select-Object -First 1 Name, LinkSpeed, MediaType, InterfaceDescription "
        "| ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    if not output:
        return result

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return result

    result["interface"] = data.get("Name", "")

    # Parse LinkSpeed ("1 Gbps", "100 Mbps", "10 Gbps")
    link_speed = str(data.get("LinkSpeed", ""))
    try:
        parts = link_speed.split()
        if len(parts) >= 2:
            value = float(parts[0])
            unit = parts[1].lower()
            if "gbps" in unit:
                result["speed_mbps"] = int(value * 1000)
            elif "mbps" in unit:
                result["speed_mbps"] = int(value)
    except (ValueError, IndexError):
        pass

    # Detect type
    media_type = str(data.get("MediaType", "")).lower()
    desc = str(data.get("InterfaceDescription", "")).lower()
    if "802.3" in media_type or "ethernet" in desc:
        result["type"] = "Ethernet"
    elif "802.11" in media_type or "wi-fi" in desc or "wireless" in desc:
        result["type"] = "WiFi"

    return result


def _get_network_macos() -> Dict[str, Any]:
    """Get network interface speed on macOS."""
    result = {"speed_mbps": None, "type": "unknown", "interface": ""}

    # Try en0 (usually primary)
    for iface in ["en0", "en1"]:
        output = _run_cmd(["ifconfig", iface])
        if output and "status: active" in output:
            result["interface"] = iface
            # Check media line for speed
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("media:"):
                    if "1000baseT" in line or "1000Base" in line:
                        result["speed_mbps"] = 1000
                    elif "100baseTX" in line or "100Base" in line:
                        result["speed_mbps"] = 100
                    elif "10baseT" in line:
                        result["speed_mbps"] = 10

                    if "autoselect" in line and "Ethernet" in line:
                        result["type"] = "Ethernet"
            break

    # WiFi check
    if result["type"] == "unknown":
        wifi_output = _run_cmd([
            "/System/Library/PrivateFrameworks/Apple80211.framework/"
            "Versions/Current/Resources/airport", "-I",
        ])
        if wifi_output and "SSID" in wifi_output:
            result["type"] = "WiFi"

    return result


def get_network_info() -> Dict[str, Any]:
    """Get primary network interface speed and type (multi-OS)."""
    system = platform.system()
    if system == "Linux":
        return _get_network_linux()
    elif system == "Windows":
        return _get_network_windows()
    elif system == "Darwin":
        return _get_network_macos()
    return {"speed_mbps": None, "type": "unknown", "interface": ""}


# =============================================================================
# BACKUP AGENT DETECTION
# =============================================================================

# Known backup agents: (service_name_or_process, display_name)
_BACKUP_AGENTS_LINUX = [
    ("veeamtransport", "Veeam"),
    ("veeamagent", "Veeam"),
    ("acronis_mms", "Acronis"),
    ("acronis_monitor", "Acronis"),
    ("cvd", "Commvault"),
    ("duplicati", "Duplicati"),
    ("borg", "BorgBackup"),
    ("restic", "Restic"),
    ("bacula-fd", "Bacula"),
    ("bareos-fd", "Bareos"),
    ("urbackupclient", "UrBackup"),
]

_BACKUP_AGENTS_WINDOWS = [
    ("VeeamBackupSvc", "Veeam"),
    ("VeeamEndpointBackupSvc", "Veeam"),
    ("AcronisCyberProtect", "Acronis"),
    ("AcronisAgent", "Acronis"),
    ("GxCVD", "Commvault"),
    ("Duplicati", "Duplicati"),
    ("wbengine", "Windows Backup"),
    ("UrBackupClientBackend", "UrBackup"),
]


def _detect_backup_linux() -> List[Dict[str, str]]:
    """Detect backup agents on Linux via systemctl/ps."""
    detected = []
    seen = set()

    # Method 1: systemctl (preferred)
    output = _run_cmd([
        "systemctl", "list-units", "--type=service",
        "--state=running", "--no-pager", "--plain",
    ])

    running_services = (output or "").lower()

    for process_name, display_name in _BACKUP_AGENTS_LINUX:
        if process_name.lower() in running_services and display_name not in seen:
            detected.append({"name": display_name, "method": "systemctl"})
            seen.add(display_name)

    # Method 2: ps (fallback for non-systemd)
    if not detected:
        ps_output = _run_cmd(["ps", "aux"])
        if ps_output:
            ps_lower = ps_output.lower()
            for process_name, display_name in _BACKUP_AGENTS_LINUX:
                if process_name.lower() in ps_lower and display_name not in seen:
                    detected.append({"name": display_name, "method": "process"})
                    seen.add(display_name)

    return detected


def _detect_backup_windows() -> List[Dict[str, str]]:
    """Detect backup agents on Windows via services."""
    detected = []
    seen = set()

    script = (
        "Get-Service | Where-Object { $_.Status -eq 'Running' } "
        "| Select-Object Name | ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    if not output:
        return []

    try:
        services = json.loads(output)
    except json.JSONDecodeError:
        return []

    if isinstance(services, dict):
        services = [services]

    running_names = {str(s.get("Name", "")).lower() for s in services}

    for service_name, display_name in _BACKUP_AGENTS_WINDOWS:
        if service_name.lower() in running_names and display_name not in seen:
            detected.append({"name": display_name, "method": "service"})
            seen.add(display_name)

    return detected


def _detect_backup_macos() -> List[Dict[str, str]]:
    """Detect backup agents on macOS."""
    detected = []

    # Time Machine
    tm_output = _run_cmd(["tmutil", "status"])
    if tm_output and "Running" in tm_output:
        detected.append({"name": "Time Machine", "method": "tmutil"})

    return detected


def detect_backup_agents() -> List[Dict[str, str]]:
    """Detect running backup agents (multi-OS)."""
    system = platform.system()
    if system == "Linux":
        return _detect_backup_linux()
    elif system == "Windows":
        return _detect_backup_windows()
    elif system == "Darwin":
        return _detect_backup_macos()
    return []


# =============================================================================
# SMART DATA (best effort, no external tools)
# =============================================================================

def _collect_smart_windows() -> Optional[List[Dict[str, Any]]]:
    """Collect SMART data on Windows via Get-StorageReliabilityCounter."""
    script = (
        "Get-PhysicalDisk | Get-StorageReliabilityCounter "
        "| Select-Object DeviceId, Temperature, Wear, "
        "ReadErrorsTotal, WriteErrorsTotal, PowerOnHours "
        "| ConvertTo-Json -Compress"
    )
    output = _run_powershell(script)
    if not output:
        return None

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        data = [data]

    result = []
    for d in data:
        entry = {}
        for key in ["DeviceId", "Temperature", "Wear", "ReadErrorsTotal",
                     "WriteErrorsTotal", "PowerOnHours"]:
            val = d.get(key)
            if val is not None:
                entry[key.lower()] = val
        if entry:
            result.append(entry)

    return result if result else None


def _collect_smart_linux() -> Optional[List[Dict[str, Any]]]:
    """Collect basic SMART indicators on Linux from /sys (no smartctl needed)."""
    # Without smartctl, we can only get very limited info from /sys
    # Check if any SMART data is exposed via device attributes
    result = []

    try:
        for dev_name in os.listdir("/sys/block"):
            if not dev_name.startswith(("sd", "nvme")):
                continue

            dev_path = f"/sys/block/{dev_name}/device"
            if not os.path.exists(dev_path):
                continue

            entry = {"device": dev_name}

            # For NVMe, some stats are available
            if dev_name.startswith("nvme"):
                # hwmon temperature
                hwmon_path = f"/sys/block/{dev_name}/device/hwmon/"
                hwmon_entries = os.listdir(hwmon_path) if os.path.exists(hwmon_path) else []
                for hwmon in hwmon_entries:
                    temp_path = f"/sys/block/{dev_name}/device/hwmon/{hwmon}/temp1_input"
                    try:
                        with open(temp_path, "r") as f:
                            temp_milli = int(f.read().strip())
                            entry["temperature_c"] = temp_milli // 1000
                    except (FileNotFoundError, PermissionError, ValueError):
                        pass
                    break

            if len(entry) > 1:
                result.append(entry)
    except (PermissionError, OSError):
        pass

    return result if result else None


def collect_smart_data() -> Optional[List[Dict[str, Any]]]:
    """Collect SMART data if available without external tools (multi-OS)."""
    system = platform.system()
    if system == "Windows":
        return _collect_smart_windows()
    elif system == "Linux":
        return _collect_smart_linux()
    # macOS: diskutil SMART status is very limited, skip for V1
    return None


# =============================================================================
# MAIN SCANNER ENTRY POINT
# =============================================================================

def scan_infrastructure(source_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Scan local server infrastructure.

    Collects:
    - OS / hostname / CPU / RAM
    - Physical disks (type, model, size)
    - RAID software configuration
    - Network interface speed
    - Backup agents detected
    - SMART data (best effort)
    - Disk usage (total/free)

    Args:
        source_path: Optional path to check disk usage for.
                     Defaults to root filesystem.

    Returns:
        Dict with all infrastructure data, ready for Hub payload.
        scores=None (agent never computes scores).
    """
    start = time.time()
    logger.info("Starting infrastructure scan...")

    # --- OS / System ---
    hostname = platform.node()
    os_name = platform.system()
    os_version = platform.release()
    os_full = platform.platform()
    cpu_count = os.cpu_count() or 0

    # RAM via psutil if available
    ram_total = None
    ram_available = None
    try:
        import psutil
        mem = psutil.virtual_memory()
        ram_total = mem.total
        ram_available = mem.available
    except ImportError:
        logger.warning("psutil not available, RAM info will be empty")

    # --- Disk usage ---
    disk_path = source_path or os.path.abspath(os.sep)
    try:
        disk_usage = shutil.disk_usage(disk_path)
        disk_total_bytes = disk_usage.total
        disk_free_bytes = disk_usage.free
    except OSError:
        disk_total_bytes = None
        disk_free_bytes = None

    # --- Collect all hardware data ---
    disks = collect_disks()
    logger.info(f"Disks collected: {len(disks)}")

    raid = detect_raid()
    logger.info(f"RAID detected: {'yes' if raid else 'no'}")

    network = get_network_info()
    logger.info(
        f"Network: {network.get('interface', '?')} "
        f"{network.get('speed_mbps', '?')} Mbps "
        f"({network.get('type', '?')})"
    )

    backup_agents = detect_backup_agents()
    logger.info(f"Backup agents: {[a['name'] for a in backup_agents] if backup_agents else 'none'}")

    smart = collect_smart_data()
    logger.info(f"SMART data: {'available' if smart else 'not available'}")

    duration = round(time.time() - start, 2)
    logger.info(f"Infrastructure scan completed in {duration}s")

    # --- Build result dict ---
    # Maps to D176-D194 metric definitions
    return {
        # D176
        "hostname": hostname,
        # D177
        "os_name": os_name,
        # D178
        "os_version": os_version,
        # Extra (not scored, for context)
        "os_full": os_full,
        # D179
        "cpu_count": cpu_count,
        # D180
        "ram_total_bytes": ram_total,
        # D181
        "ram_available_bytes": ram_available,
        # D182
        "disk_count": len(disks),
        # D183 (JSONB)
        "disks": disks,
        # D184
        "disk_total_bytes": disk_total_bytes,
        # D185
        "disk_free_bytes": disk_free_bytes,
        # D186
        "has_ssd": any(
            d.get("type") in ("SSD", "NVMe") for d in disks
        ),
        # D187
        "has_raid": raid is not None,
        # D188 (JSONB)
        "raid_config": raid,
        # D189
        "network_speed_mbps": network.get("speed_mbps"),
        # D190
        "network_type": network.get("type", "unknown"),
        # Extra
        "network_interface": network.get("interface", ""),
        # D191 (JSONB)
        "backup_agents_detected": backup_agents,
        # D192
        "has_backup_agent": len(backup_agents) > 0,
        # D193
        "smart_available": smart is not None,
        # D194 (JSONB)
        "smart_data": smart,
        # Metadata
        "scan_duration_seconds": duration,
    }
