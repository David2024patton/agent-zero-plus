"""
Agent Zero Plugin API (SDK)
===========================
Provides the AgentZeroPluginApi class that plugins use to register
channels, tools, hooks, and access configuration/secrets.

Modeled after OpenClaw's OpenClawPluginApi but adapted for Python.
"""

from __future__ import annotations
import os
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from agent import Agent

logger = logging.getLogger("agent-zero.plugins")


@dataclass
class ChannelMessage:
    """A message received from or sent to a channel."""
    channel_id: str          # e.g. "discord", "telegram"
    sender_id: str           # user identifier on that channel
    sender_name: str         # display name
    content: str             # message text
    attachments: List[str] = field(default_factory=list)  # file paths
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None  # message ID being replied to


class ChannelAdapter:
    """
    Base class for channel adapters (Discord, Telegram, Slack, etc.)
    Subclass and implement the abstract methods.
    """
    
    def __init__(self, channel_id: str):
        self.channel_id = channel_id
        self._message_callback: Optional[Callable] = None
    
    async def start(self):
        """Start listening for messages. Called once at startup."""
        raise NotImplementedError
    
    async def stop(self):
        """Gracefully stop the channel adapter."""
        raise NotImplementedError
    
    async def send_message(self, to: str, content: str, 
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """Send a message to a target (user/channel) on this platform."""
        raise NotImplementedError
    
    def on_message(self, callback: Callable):
        """Register callback for incoming messages: callback(ChannelMessage)"""
        self._message_callback = callback
    
    async def _dispatch_message(self, message: ChannelMessage):
        """Internal: dispatch an incoming message to the registered callback."""
        if self._message_callback:
            await self._message_callback(message)


class AgentZeroPluginApi:
    """
    The Plugin SDK — passed to each plugin's register() function.
    Provides methods to register channels, tools, hooks, and access config.
    """
    
    def __init__(self, plugin_id: str, config: Dict[str, Any]):
        self.plugin_id = plugin_id
        self.config = config
        self._channels: Dict[str, ChannelAdapter] = {}
        self._tools: List[Any] = []
        self._hooks: Dict[str, List[Callable]] = {}
    
    def register_channel(self, adapter: ChannelAdapter):
        """Register a messaging channel adapter."""
        self._channels[adapter.channel_id] = adapter
        logger.info(f"[Plugin:{self.plugin_id}] Registered channel: {adapter.channel_id}")
    
    def register_tool(self, tool_class: Any):
        """Register a new tool class that will be made available to the agent."""
        self._tools.append(tool_class)
        logger.info(f"[Plugin:{self.plugin_id}] Registered tool: {tool_class.__name__ if hasattr(tool_class, '__name__') else tool_class}")
    
    def register_hook(self, event: str, callback: Callable):
        """
        Register a callback for a lifecycle event.
        Events match Agent Zero's extension system:
        - message_loop_start, message_loop_end
        - tool_execute_before, tool_execute_after
        - system_prompt, etc.
        """
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
        logger.info(f"[Plugin:{self.plugin_id}] Registered hook: {event}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a value from the plugin's config."""
        return self.config.get(key, default)
    
    def get_secret(self, env_key: str) -> Optional[str]:
        """Get a secret from environment variables."""
        return os.environ.get(env_key)
    
    @property
    def channels(self) -> Dict[str, ChannelAdapter]:
        return self._channels
    
    @property
    def tools(self) -> List[Any]:
        return self._tools
    
    @property
    def hooks(self) -> Dict[str, List[Callable]]:
        return self._hooks
