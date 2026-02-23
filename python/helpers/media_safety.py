"""
Media Safety: Path Validation for File Attachments
====================================================
Inspired by OpenClaw #22348 (localRoots for media access).

Prevents directory traversal attacks by validating that file paths
resolve to locations within allowed root directories.
"""

from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import List, Optional

from python.helpers.files import get_abs_path

logger = logging.getLogger("agent-zero.media_safety")

# Default allowed roots for media file access
DEFAULT_ALLOWED_ROOTS = [
    get_abs_path("usr"),      # User data directory
    get_abs_path("tmp"),      # Temp files
    get_abs_path("work_dir"), # Agent workspace
]


def validate_media_path(
    file_path: str,
    allowed_roots: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Validate that a file path is within allowed directories.
    
    Returns the resolved absolute path if valid, None if rejected.
    
    This prevents:
    - Directory traversal (../../etc/passwd)
    - Symlink escapes
    - Access to system files outside the sandbox
    
    Args:
        file_path: The path to validate
        allowed_roots: List of allowed root directories. 
                       Defaults to DEFAULT_ALLOWED_ROOTS.
    
    Returns:
        Resolved absolute path string if valid, None if rejected.
    """
    if not file_path:
        return None

    if allowed_roots is None:
        allowed_roots = DEFAULT_ALLOWED_ROOTS

    try:
        # Resolve to absolute path (follows symlinks)
        resolved = Path(file_path).resolve()

        # Check if path exists
        if not resolved.exists():
            logger.warning(f"Media path does not exist: {file_path}")
            return None

        # Check if path is under any allowed root
        for root in allowed_roots:
            root_resolved = Path(root).resolve()
            try:
                resolved.relative_to(root_resolved)
                return str(resolved)
            except ValueError:
                continue

        logger.warning(
            f"Media path rejected (outside allowed roots): {file_path} "
            f"(resolved: {resolved})"
        )
        return None

    except Exception as e:
        logger.error(f"Error validating media path: {e}")
        return None


def validate_media_paths(
    file_paths: List[str],
    allowed_roots: Optional[List[str]] = None,
) -> List[str]:
    """
    Validate multiple file paths. Returns only valid paths.
    
    Args:
        file_paths: List of paths to validate
        allowed_roots: List of allowed root directories
    
    Returns:
        List of valid resolved paths (invalid paths silently dropped)
    """
    valid = []
    for path in file_paths:
        validated = validate_media_path(path, allowed_roots)
        if validated:
            valid.append(validated)
    return valid
