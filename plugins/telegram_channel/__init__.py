"""
Telegram Channel Plugin for Agent Zero
=======================================
Connects Agent Zero to Telegram as a messaging channel.
Users can DM the bot or mention it in groups to interact with the agent.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import TelegramChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    bot_token_env = api.get_config("bot_token_env", "TELEGRAM_BOT_TOKEN")
    allowed_users = api.get_config("allowed_users", "")
    respond_to_groups = api.get_config("respond_to_groups", True)
    respond_to_private = api.get_config("respond_to_private", True)

    adapter = TelegramChannelAdapter(
        bot_token_env=bot_token_env,
        allowed_users=allowed_users,
        respond_to_groups=respond_to_groups,
        respond_to_private=respond_to_private,
    )

    api.register_channel(adapter)
