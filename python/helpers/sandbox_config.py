"""
Sandbox Browser Configuration for Agent Zero
==============================================
Configures isolated browser container bind mounts separately from
code execution containers, preventing web content from accessing
the agent's filesystem.

Inspired by OpenClaw's sandbox.browser.binds feature.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("agent-zero.sandbox")


@dataclass
class SandboxConfig:
    """
    Configuration for sandboxed execution environments.
    
    Provides separate configurations for:
    - Code execution containers (full access to agent workspace)
    - Browser/automation containers (isolated, read-only)
    """

    # Code execution container settings
    exec_binds: Dict[str, str] = field(default_factory=lambda: {
        "/workspace": "/workspace",
    })
    exec_read_only: List[str] = field(default_factory=list)

    # Browser container settings (isolated by default)
    browser_binds: Dict[str, str] = field(default_factory=lambda: {
        "/tmp/browser": "/tmp/browser",
    })
    browser_read_only: List[str] = field(default_factory=lambda: [
        "/tmp/browser",
    ])
    browser_network_mode: str = "bridge"  # "bridge" | "host" | "none"
    browser_disable_gpu: bool = False

    # Shared security settings
    no_new_privileges: bool = True
    drop_capabilities: List[str] = field(default_factory=lambda: [
        "SYS_ADMIN", "NET_RAW",
    ])


def get_docker_exec_config(config: SandboxConfig) -> dict:
    """
    Generate Docker container config for code execution.
    Returns a dict suitable for docker-py create_container().
    """
    volumes = {}
    binds = []

    for host_path, container_path in config.exec_binds.items():
        mode = "ro" if host_path in config.exec_read_only else "rw"
        volumes[container_path] = {}
        binds.append(f"{host_path}:{container_path}:{mode}")

    return {
        "volumes": volumes,
        "host_config": {
            "binds": binds,
            "security_opt": ["no-new-privileges"] if config.no_new_privileges else [],
            "cap_drop": config.drop_capabilities,
        },
    }


def get_docker_browser_config(config: SandboxConfig) -> dict:
    """
    Generate Docker container config for browser automation.
    Browser containers are isolated from the agent's workspace.
    """
    volumes = {}
    binds = []

    for host_path, container_path in config.browser_binds.items():
        mode = "ro" if host_path in config.browser_read_only else "rw"
        volumes[container_path] = {}
        binds.append(f"{host_path}:{container_path}:{mode}")

    return {
        "volumes": volumes,
        "host_config": {
            "binds": binds,
            "network_mode": config.browser_network_mode,
            "security_opt": ["no-new-privileges"] if config.no_new_privileges else [],
            "cap_drop": config.drop_capabilities,
        },
    }


def from_settings(settings: dict) -> SandboxConfig:
    """
    Create SandboxConfig from Agent Zero settings.

    Settings keys:
        sandbox_exec_binds: str       - comma-separated host:container pairs
        sandbox_browser_binds: str    - comma-separated host:container pairs
        sandbox_browser_read_only: bool
        sandbox_browser_network: str  - "bridge" | "host" | "none"
        sandbox_no_new_privileges: bool
    """
    config = SandboxConfig()

    # Parse exec binds
    exec_binds_str = settings.get("sandbox_exec_binds", "")
    if exec_binds_str:
        config.exec_binds = _parse_binds(exec_binds_str)

    # Parse browser binds
    browser_binds_str = settings.get("sandbox_browser_binds", "")
    if browser_binds_str:
        config.browser_binds = _parse_binds(browser_binds_str)

    # Browser isolation
    if settings.get("sandbox_browser_read_only", True):
        config.browser_read_only = list(config.browser_binds.values())

    config.browser_network_mode = settings.get("sandbox_browser_network", "bridge")
    config.no_new_privileges = settings.get("sandbox_no_new_privileges", True)

    return config


def _parse_binds(binds_str: str) -> Dict[str, str]:
    """Parse comma-separated host:container bind mount pairs."""
    result = {}
    for pair in binds_str.split(","):
        pair = pair.strip()
        if ":" in pair:
            host, container = pair.split(":", 1)
            result[host.strip()] = container.strip()
    return result
