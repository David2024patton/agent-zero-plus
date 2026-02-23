"""
Agent Zero Plugin Loader
========================
Discovers plugins from the plugins/ directory, loads them, and manages
their lifecycle (start/stop channels, dispatch messages).
"""

from __future__ import annotations
import os
import json
import asyncio
import logging
import importlib
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from python.helpers import files

from python.helpers.plugin_api import (
    AgentZeroPluginApi,
    ChannelAdapter,
    ChannelMessage,
)

if TYPE_CHECKING:
    from agent import Agent

logger = logging.getLogger("agent-zero.plugins")


class PluginLoader:
    """
    Discovers, loads, and manages Agent Zero plugins.
    
    Usage:
        loader = PluginLoader(plugins_dir="/a0/plugins")
        loader.discover()
        await loader.start_all(message_handler)
        
        # Send a message to a channel
        await loader.send("discord", to="user:YOUR_DISCORD_USER_ID", content="Hello!")
        
        # Shutdown
        await loader.stop_all()
    """
    
    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            # Default: <agent-zero-root>/plugins/
            plugins_dir = str(Path(__file__).parent.parent.parent / "plugins")
        self.plugins_dir = Path(plugins_dir)
        self._apis: Dict[str, AgentZeroPluginApi] = {}
        self._channels: Dict[str, ChannelAdapter] = {}
        self._message_handler: Optional[Callable] = None
        self._started = False
    
    def _load_plugins_state(self) -> dict:
        """Load the plugins_state.json which has user-saved enabled/config."""
        state_path = Path(files.get_abs_path("usr", "plugins_state.json"))
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def discover(self) -> List[str]:
        """
        Scan the plugins directory for valid plugins.
        Each plugin must have a plugin.json manifest and __init__.py.
        Reads enabled state and saved config from usr/plugins_state.json.
        Returns list of discovered plugin IDs.
        """
        discovered = []
        
        if not self.plugins_dir.exists():
            logger.info(f"Plugins directory not found: {self.plugins_dir}")
            return discovered
        
        # Load user-saved plugin state (enabled flags + config values)
        plugins_state = self._load_plugins_state()
        enabled_map = plugins_state.get("enabled", {})
        configs_map = plugins_state.get("configs", {})
        
        for entry in sorted(self.plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith(("_", ".")):
                continue
            
            manifest_path = entry / "plugin.json"
            init_path = entry / "__init__.py"
            
            if not manifest_path.exists():
                logger.warning(f"Skipping {entry.name}: no plugin.json")
                continue
            
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                
                plugin_id = manifest.get("id", entry.name)
                
                # Check enabled status: plugins_state.json takes priority,
                # then manifest, default to False (explicit opt-in)
                if plugin_id in enabled_map:
                    enabled = enabled_map[plugin_id]
                elif entry.name in enabled_map:
                    enabled = enabled_map[entry.name]
                else:
                    enabled = manifest.get("enabled", False)
                
                if not enabled:
                    logger.info(f"Plugin '{plugin_id}' is disabled, skipping")
                    continue
                
                # Build config: start with manifest schema defaults,
                # then overlay user-saved values from plugins_state.json
                config_schema = manifest.get("config", {})
                config = {}
                for key, schema in config_schema.items():
                    if isinstance(schema, dict):
                        # Schema objects have 'default', 'env', etc.
                        if "env" in schema:
                            config[key] = os.environ.get(schema["env"], schema.get("default", ""))
                        else:
                            config[key] = schema.get("default", "")
                    else:
                        config[key] = schema
                
                # Overlay saved user config
                saved_config = configs_map.get(plugin_id, configs_map.get(entry.name, {}))
                for key, value in saved_config.items():
                    config[key] = value
                
                api = AgentZeroPluginApi(plugin_id=plugin_id, config=config)
                
                # Try to load and register the plugin
                if init_path.exists():
                    self._load_python_plugin(entry, api)
                else:
                    logger.warning(f"Plugin '{plugin_id}' has no __init__.py, skipping")
                    continue
                
                # Collect registered channels
                for ch_id, adapter in api.channels.items():
                    self._channels[ch_id] = adapter
                
                self._apis[plugin_id] = api
                discovered.append(plugin_id)
                logger.info(f"Loaded plugin: {plugin_id} (channels: {list(api.channels.keys())}, tools: {len(api.tools)}, hooks: {len(api.hooks)})")
                
            except Exception as e:
                logger.error(f"Failed to load plugin from {entry.name}: {e}\n{traceback.format_exc()}")
        
        return discovered
    
    def _load_python_plugin(self, plugin_dir: Path, api: AgentZeroPluginApi):
        """Load a Python plugin module and call its register() function."""
        import sys
        
        # Add the plugins directory to sys.path if not already there
        plugins_parent = str(self.plugins_dir)
        if plugins_parent not in sys.path:
            sys.path.insert(0, plugins_parent)
        
        module_name = f"plugins.{plugin_dir.name}"
        
        # Remove cached module to allow reloading
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        spec = importlib.util.spec_from_file_location(
            module_name,
            str(plugin_dir / "__init__.py"),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Call register(api) if it exists
            if hasattr(module, "register"):
                module.register(api)
            else:
                logger.warning(f"Plugin {plugin_dir.name} has no register() function")
    
    async def start_all(self, message_handler: Callable = None):
        """
        Start all registered channel adapters.
        message_handler receives ChannelMessage objects from incoming messages.
        """
        self._message_handler = message_handler
        self._started = True
        
        for ch_id, adapter in self._channels.items():
            try:
                # Wire up incoming message handler
                adapter.on_message(self._handle_incoming)
                
                # Start the adapter in a background task
                asyncio.create_task(
                    self._start_adapter(ch_id, adapter),
                    name=f"plugin-channel-{ch_id}",
                )
                logger.info(f"Starting channel adapter: {ch_id}")
            except Exception as e:
                logger.error(f"Failed to start channel {ch_id}: {e}")
    
    async def _start_adapter(self, ch_id: str, adapter: ChannelAdapter):
        """Start a single adapter with error handling."""
        try:
            await adapter.start()
        except Exception as e:
            logger.error(f"Channel adapter {ch_id} crashed: {e}\n{traceback.format_exc()}")
    
    async def _handle_incoming(self, message: ChannelMessage):
        """Handle an incoming message from any channel."""
        logger.info(f"Incoming [{message.channel_id}] from {message.sender_name}: {message.content[:100]}")
        if self._message_handler:
            try:
                await self._message_handler(message)
            except Exception as e:
                logger.error(f"Error handling message: {e}\n{traceback.format_exc()}")
    
    async def send(self, channel_id: str, to: str, content: str,
                   attachments: Optional[List[str]] = None, **kwargs) -> bool:
        """Send a message through a registered channel."""
        adapter = self._channels.get(channel_id)
        if not adapter:
            logger.error(f"No channel adapter registered for: {channel_id}")
            return False
        
        try:
            return await adapter.send_message(to=to, content=content,
                                               attachments=attachments, **kwargs)
        except Exception as e:
            logger.error(f"Failed to send via {channel_id}: {e}")
            return False
    
    async def stop_all(self):
        """Stop all channel adapters gracefully."""
        self._started = False
        for ch_id, adapter in self._channels.items():
            try:
                await adapter.stop()
                logger.info(f"Stopped channel adapter: {ch_id}")
            except Exception as e:
                logger.error(f"Error stopping {ch_id}: {e}")
    
    def list_channels(self) -> List[str]:
        """Return list of registered channel IDs."""
        return list(self._channels.keys())
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """Return info about all loaded plugins."""
        result = []
        for pid, api in self._apis.items():
            result.append({
                "id": pid,
                "channels": list(api.channels.keys()),
                "tools": len(api.tools),
                "hooks": len(api.hooks),
            })
        return result
    
    def get_channel(self, channel_id: str) -> Optional[ChannelAdapter]:
        """Get a specific channel adapter by ID."""
        return self._channels.get(channel_id)


# Singleton instance
_loader: Optional[PluginLoader] = None

def get_plugin_loader(plugins_dir: str = None) -> PluginLoader:
    """Get or create the singleton PluginLoader instance."""
    global _loader
    if _loader is None:
        _loader = PluginLoader(plugins_dir)
    return _loader


def get_channel_adapter(channel_id: str) -> Optional[ChannelAdapter]:
    """
    Module-level convenience: get a channel adapter by ID from the singleton loader.
    Used by webhook_incoming.py to route payloads to adapters.
    Returns None if loader not initialized or channel not found.
    """
    if _loader is None:
        return None
    return _loader.get_channel(channel_id)
