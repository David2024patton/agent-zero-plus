"""
Matrix Channel Plugin for Agent Zero
======================================
Connects Agent Zero to Matrix/Element as a messaging channel.
Uses the matrix-nio library for E2EE-capable communication.
"""

from python.helpers.plugin_api import AgentZeroPluginApi
from .bot import MatrixChannelAdapter


def register(api: AgentZeroPluginApi):
    """Called by the plugin loader to register this plugin."""
    homeserver_url = api.get_config("homeserver_url", "https://matrix.org")
    user_id = api.get_config("user_id", "")
    access_token_env = api.get_config("access_token_env", "MATRIX_ACCESS_TOKEN")
    allowed_rooms = api.get_config("allowed_rooms", "")
    respond_to_dms = api.get_config("respond_to_dms", True)

    adapter = MatrixChannelAdapter(
        homeserver_url=homeserver_url,
        user_id=user_id,
        access_token_env=access_token_env,
        allowed_rooms=allowed_rooms,
        respond_to_dms=respond_to_dms,
    )

    api.register_channel(adapter)
