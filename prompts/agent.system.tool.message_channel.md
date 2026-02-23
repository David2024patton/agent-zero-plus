## message_channel

Send messages through registered channel plugins (Discord, Telegram, Slack, etc.).

Use this tool to proactively communicate with the user or others via messaging platforms.

**Example usage:**
~~~json
{
    "tool_name": "message_channel",
    "tool_args": {
        "channel": "discord",
        "to": "user:DISCORD_USER_ID",
        "message": "Task complete! The deployment was successful."
    }
}
~~~

**Parameters:**
- **channel** (required): The channel to send through (e.g., "discord", "telegram")
- **to** (required): Target in format "user:<id>" or "channel:<id>"  
- **message** (required): The message content to send

**Notes:**
- Only works with channels that have been registered via the plugin system
- Discord messages are automatically split if they exceed 2000 characters
- Use "user:<id>" for direct messages, "channel:<id>" for channel messages
