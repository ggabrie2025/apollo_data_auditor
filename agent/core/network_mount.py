"""
Apollo Agent - Network Mount Detection (V2.0)
==============================================

Detects network mounts (NFS, SMB, CIFS, FUSE) on Linux and Windows.
Used to exclude network paths from FILES scan by default.

Version: 2.0.0
Date: 2025-12-28
"""

import os
import platform
from pathlib import Path
from typing import List, Optional

# Default network filesystem types
DEFAULT_NETWORK_FS_TYPES = ['nfs', 'nfs4', 'cifs', 'smbfs', 'fuse', 'sshfs', 's3fs']


def is_network_mount_linux(path: str, network_fs_types: Optional[List[str]] = None) -> bool:
    """
    Check if path is on a network mount (Linux only).

    Reads /proc/self/mountinfo to detect network filesystems.

    Args:
        path: Absolute path to check
        network_fs_types: List of filesystem types to consider as network

    Returns:
        True if path is on a network mount
    """
    if platform.system() != 'Linux':
        return False

    if network_fs_types is None:
        network_fs_types = DEFAULT_NETWORK_FS_TYPES

    try:
        resolved_path = str(Path(path).resolve())

        with open('/proc/self/mountinfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 9:
                    continue

                mount_point = parts[4]
                # fs_type is after the " - " separator
                try:
                    separator_idx = parts.index('-')
                    fs_type = parts[separator_idx + 1] if len(parts) > separator_idx + 1 else ""
                except ValueError:
                    fs_type = parts[8] if len(parts) > 8 else ""

                if resolved_path.startswith(mount_point) or resolved_path == mount_point:
                    if fs_type.lower() in [t.lower() for t in network_fs_types]:
                        return True

    except (FileNotFoundError, PermissionError, OSError):
        pass  # Not Linux or no access to mountinfo

    return False


def is_network_mount_windows(path: str) -> bool:
    """
    Check if path is on a network mount (Windows only).

    Detects:
    - UNC paths (\\\\server\\share)
    - Mapped network drives (Z:\\)

    Args:
        path: Path to check

    Returns:
        True if path is on a network mount
    """
    if platform.system() != 'Windows':
        return False

    # UNC path (\\server\share)
    if path.startswith("\\\\"):
        return True

    # Mapped drive letter
    drive = os.path.splitdrive(path)[0]
    if drive:
        try:
            import ctypes
            DRIVE_REMOTE = 4
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
            return drive_type == DRIVE_REMOTE
        except (AttributeError, OSError):
            pass  # ctypes not available or error

    return False


def is_network_mount(path: str, network_fs_types: Optional[List[str]] = None) -> bool:
    """
    Check if path is on a network mount (Windows or Linux).

    Args:
        path: Path to check
        network_fs_types: List of filesystem types to consider as network (Linux)

    Returns:
        True if path is on a network mount
    """
    return (
        is_network_mount_linux(path, network_fs_types) or
        is_network_mount_windows(path)
    )


def get_mount_info(path: str) -> Optional[dict]:
    """
    Get mount information for a path (Linux only).

    Args:
        path: Path to check

    Returns:
        Dict with mount_point, fs_type, or None if not found
    """
    if platform.system() == 'Windows':
        try:
            drive = os.path.splitdrive(str(Path(path).resolve()))[0]
            if drive:
                import ctypes
                DRIVE_REMOTE = 4
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
                return {
                    'mount_point': drive + "\\",
                    'fs_type': 'network' if drive_type == DRIVE_REMOTE else 'local'
                }
        except Exception:
            pass
        return None

    if platform.system() != 'Linux':
        return None

    try:
        resolved_path = str(Path(path).resolve())
        best_match = None
        best_match_len = 0

        with open('/proc/self/mountinfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 9:
                    continue

                mount_point = parts[4]

                # Find the most specific mount point
                if resolved_path.startswith(mount_point) or resolved_path == mount_point:
                    if len(mount_point) > best_match_len:
                        try:
                            separator_idx = parts.index('-')
                            fs_type = parts[separator_idx + 1] if len(parts) > separator_idx + 1 else ""
                        except ValueError:
                            fs_type = parts[8] if len(parts) > 8 else ""

                        best_match = {
                            'mount_point': mount_point,
                            'fs_type': fs_type
                        }
                        best_match_len = len(mount_point)

        return best_match

    except (FileNotFoundError, PermissionError, OSError):
        return None
