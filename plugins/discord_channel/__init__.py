"""
Discord Channel Plugin for Agent Zero
======================================
Connects Agent Zero to Discord as a messaging channel.
Users can DM the bot or @mention it to interact with the agent.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import DiscordChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    bot_token_env = api.get_config("bot_token_env", "DISCORD_BOT_TOKEN")
    owner_user_id = api.get_config("owner_user_id")
    command_prefix = api.get_config("command_prefix", "!a0")
    respond_to_dms = api.get_config("respond_to_dms", True)
    respond_to_mentions = api.get_config("respond_to_mentions", True)
    
    adapter = DiscordChannelAdapter(
        bot_token_env=bot_token_env,
        owner_user_id=owner_user_id,
        command_prefix=command_prefix,
        respond_to_dms=respond_to_dms,
        respond_to_mentions=respond_to_mentions,
    )
    
    api.register_channel(adapter)
