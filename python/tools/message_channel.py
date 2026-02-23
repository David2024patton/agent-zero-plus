"""
Agent Zero Tool: message_channel
=================================
Allows the agent to send messages through registered channel plugins
(Discord, Telegram, Slack, etc.).
"""

from python.helpers.tool import Tool, Response
from python.helpers import plugin_loader


class MessageChannel(Tool):
    
    async def execute(self, **kwargs):
        channel = self.args.get("channel", "").strip()
        to = self.args.get("to", "").strip()
        message = self.args.get("message", "").strip()
        
        if not channel:
            return Response(
                message="Error: 'channel' is required. Available channels: "
                + ", ".join(self._get_channels()),
                break_loop=False,
            )
        
        if not to:
            return Response(
                message="Error: 'to' is required. Format: 'user:<id>' or 'channel:<id>'",
                break_loop=False,
            )
        
        if not message:
            return Response(
                message="Error: 'message' is required.",
                break_loop=False,
            )
        
        # Get the plugin loader
        loader = plugin_loader.get_plugin_loader()
        
        # Check if channel exists
        available = loader.list_channels()
        if channel not in available:
            return Response(
                message=f"Error: Channel '{channel}' is not registered. Available: {', '.join(available) or 'none'}",
                break_loop=False,
            )
        
        # Send the message
        success = await loader.send(channel, to=to, content=message)
        
        if success:
            return Response(
                message=f"Message sent via {channel} to {to}",
                break_loop=False,
            )
        else:
            return Response(
                message=f"Failed to send message via {channel}. Check logs for details.",
                break_loop=False,
            )
    
    def _get_channels(self):
        """Get list of available channels."""
        try:
            loader = plugin_loader.get_plugin_loader()
            return loader.list_channels()
        except Exception:
            return []
