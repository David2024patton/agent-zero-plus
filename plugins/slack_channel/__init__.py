"""
Slack Channel Plugin for Agent Zero
====================================
Connects Agent Zero to Slack as a messaging channel.
Responds to DMs, @mentions, and slash commands via Socket Mode.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import SlackChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    bot_token_env = api.get_config("bot_token_env", "SLACK_BOT_TOKEN")
    app_token_env = api.get_config("app_token_env", "SLACK_APP_TOKEN")
    signing_secret_env = api.get_config("signing_secret_env", "SLACK_SIGNING_SECRET")
    allowed_channels = api.get_config("allowed_channels", "")
    respond_to_dms = api.get_config("respond_to_dms", True)
    respond_to_mentions = api.get_config("respond_to_mentions", True)

    adapter = SlackChannelAdapter(
        bot_token_env=bot_token_env,
        app_token_env=app_token_env,
        signing_secret_env=signing_secret_env,
        allowed_channels=allowed_channels,
        respond_to_dms=respond_to_dms,
        respond_to_mentions=respond_to_mentions,
    )

    api.register_channel(adapter)
