"""
Webhook Channel Plugin for Agent Zero
=======================================
Generic HTTP webhook endpoint.
Receives JSON payloads and routes them to Agent Zero as messages.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import WebhookChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    webhook_path = api.get_config("webhook_path", "/webhook/agent")
    auth_token_env = api.get_config("auth_token_env", "WEBHOOK_AUTH_TOKEN")
    response_mode = api.get_config("response_mode", "sync")

    adapter = WebhookChannelAdapter(
        webhook_path=webhook_path,
        auth_token_env=auth_token_env,
        response_mode=response_mode,
    )

    api.register_channel(adapter)
