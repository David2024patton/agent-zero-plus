"""
Microsoft Teams Channel Plugin for Agent Zero
================================================
Connects Agent Zero to Microsoft Teams via the Bot Framework.
Responds to messages, @mentions, and 1:1 chats.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import TeamsChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    app_id = api.get_config("app_id", "")
    app_password_env = api.get_config("app_password_env", "TEAMS_APP_PASSWORD")
    tenant_id = api.get_config("tenant_id", "")
    respond_to_personal = api.get_config("respond_to_personal", True)
    respond_to_channels = api.get_config("respond_to_channels", True)

    adapter = TeamsChannelAdapter(
        app_id=app_id,
        app_password_env=app_password_env,
        tenant_id=tenant_id,
        respond_to_personal=respond_to_personal,
        respond_to_channels=respond_to_channels,
    )

    api.register_channel(adapter)
