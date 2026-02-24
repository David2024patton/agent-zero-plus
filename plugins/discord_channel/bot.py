"""
Discord Channel Adapter for Agent Zero
=======================================
Uses discord.py to connect Agent Zero to Discord.
Supports direct messages, mentions, and proactive messaging.
"""

from __future__ import annotations
import os
import asyncio
import logging
import time
from typing import Dict, List, Optional

try:
    import discord
    from discord import Intents, app_commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage
from python.helpers.lifecycle_reactions import (
    LifecycleTracker, SubAgentManager, check_dm_access, get_model_override,
)
from .thread_manager import ThreadBindingManager
from .pairing import PairingManager
from .streaming import DiscordStreamingReply

logger = logging.getLogger("agent-zero.plugins.discord")


# --- Discord Components v2: Confirmation View ---
class ConfirmationView(discord.ui.View if HAS_DISCORD else object):
    """Interactive confirmation buttons for tool execution approvals."""

    def __init__(self, timeout: float = 120.0):
        if HAS_DISCORD:
            super().__init__(timeout=timeout)
        self.result: Optional[bool] = None
        self._event = asyncio.Event()

    if HAS_DISCORD:
        @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
        async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.result = True
            self._event.set()
            await interaction.response.edit_message(content="✅ **Approved**", view=None)

        @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
        async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.result = False
            self._event.set()
            await interaction.response.edit_message(content="❌ **Denied**", view=None)

    async def wait_for_result(self) -> Optional[bool]:
        """Wait for user to click a button. Returns True/False/None (timeout)."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            pass
        return self.result

class DiscordChannelAdapter(ChannelAdapter):
    """
    Discord channel adapter.
    Listens for DMs and @mentions, dispatches them as ChannelMessages,
    and can send messages back to Discord channels/users.
    """
    
    def __init__(
        self,
        bot_token_env: str = "DISCORD_BOT_TOKEN",
        owner_user_id: str = None,
        command_prefix: str = "!a0",
        respond_to_dms: bool = True,
        respond_to_mentions: bool = True,
    ):
        super().__init__(channel_id="discord")
        self.bot_token_env = bot_token_env
        self.owner_user_id = owner_user_id
        self.command_prefix = command_prefix
        self.respond_to_dms = respond_to_dms
        self.respond_to_mentions = respond_to_mentions
        self._client: Optional[discord.Client] = None
        self._ready_event = asyncio.Event()

        # --- Slash command & feature state ---
        self._session_reset_channels: set = set()
        self._abort_channels: set = set()
        self._verbose_mode: str = "off"
        self._streaming_mode: str = "off"  # off, partial, block
        self._usage_stats: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "message_count": 0,
        }
        self._thread_bindings: Dict[str, dict] = {}  # Legacy compat
        self._thread_manager = ThreadBindingManager(ttl_hours=24.0)
        self._subagent_manager = SubAgentManager()
        self._pairing_manager = PairingManager(
            policy="owner",
            owner_user_id=owner_user_id,
        )
        self._project_manager = None  # Initialized on start() after imports
    
    async def start(self):
        """Start the Discord bot."""
        if not HAS_DISCORD:
            logger.error("discord.py is not installed. Run: pip install discord.py")
            return
        
        token = os.environ.get(self.bot_token_env)
        if not token:
            logger.error(f"Discord bot token not found in env var: {self.bot_token_env}")
            return
        
        # Set up intents
        intents = Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.guilds = True
        intents.members = True  # Needed for role-based routing
        
        self._client = discord.Client(intents=intents)
        
        # --- Set up slash commands ---
        tree = app_commands.CommandTree(self._client)
        self._command_tree = tree
        try:
            from .commands import setup_commands
            setup_commands(self, tree)
        except Exception as e:
            logger.error(f"Failed to set up slash commands: {e}")
        
        # --- Set up project system ---
        try:
            from .projects import ProjectManager
            self._project_manager = ProjectManager(adapter=self)
            logger.info("Project system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize project system: {e}")
            self._project_manager = None
        
        @self._client.event
        async def on_ready():
            logger.info(f"Discord bot connected as: {self._client.user}")
            # Sync slash commands with Discord
            try:
                synced = await tree.sync()
                logger.info(f"Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"Failed to sync slash commands: {e}")
            # Start thread binding cleanup loop
            await self._thread_manager.start_cleanup_loop()
            # Set bot presence
            try:
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Skynet",
                )
                await self._client.change_presence(
                    status=discord.Status.online,
                    activity=activity,
                )
            except Exception as e:
                logger.debug(f"Failed to set presence: {e}")
            self._ready_event.set()
        
        @self._client.event
        async def on_interaction(interaction: discord.Interaction):
            """Route slash command interactions to the CommandTree."""
            if interaction.type == discord.InteractionType.application_command:
                await tree._call(interaction)
            elif interaction.type == discord.InteractionType.autocomplete:
                await tree._call(interaction)
        
        @self._client.event
        async def on_message(message: discord.Message):
            # Don't respond to ourselves
            if message.author == self._client.user:
                return
            
            # --- Check for thread binding ---
            thread_id = str(message.channel.id)
            thread_binding = self._thread_manager.get_binding(thread_id)
            
            # --- Check session resets ---
            channel_key = str(message.channel.id)
            if channel_key in self._session_reset_channels:
                self._session_reset_channels.discard(channel_key)
                # Context reset flag in metadata
            
            # Check if we should respond
            should_respond = False
            content = message.content
            project_context = None  # Set if message is in a project channel
            
            # Project channel check — always respond, with access control
            if self._project_manager and not isinstance(message.channel, discord.DMChannel):
                has_access, project = self._project_manager.check_access(
                    str(message.channel.id), str(message.author.id)
                )
                if project is not None:
                    if not has_access:
                        await message.reply(
                            "🔒 You don't have access to this project.",
                            mention_author=False,
                        )
                        return
                    should_respond = True
                    project_context = {
                        "project_id": project.id,
                        "project_name": project.name,
                        "project_owner": project.user_id,
                        "project_slug": project.slug,
                    }
                    self._project_manager.touch(str(message.channel.id))
            
            # Thread-bound messages always respond
            if thread_binding:
                should_respond = True
                # Update activity tracking
                self._thread_manager.touch(thread_id)
            # DM check
            elif isinstance(message.channel, discord.DMChannel):
                if self.respond_to_dms:
                    # Use PairingManager for DM access control
                    pm = self._pairing_manager
                    user_id = str(message.author.id)
                    
                    if pm.is_authorized(user_id):
                        should_respond = True
                    elif pm.policy == "pairing":
                        # Auto-create pairing request for unknown sender
                        request = pm.create_request(
                            sender_id=user_id,
                            sender_name=message.author.display_name,
                            channel_id=str(message.channel.id),
                        )
                        if request:
                            await message.channel.send(
                                f"🔐 **Pairing Required**\n"
                                f"Your pairing code: `{request.code}`\n"
                                f"Send this code to the bot owner to get approved.\n"
                                f"Code expires in {request.remaining_minutes()} minutes."
                            )
                            logger.info(
                                f"Pairing request sent to {message.author.display_name}"
                            )
                        else:
                            # Request already pending or at limit
                            pass
                        return  # Don't process the message
                    elif pm.policy == "disabled":
                        return  # DMs completely off
                    else:
                        # "owner" policy — check_dm_access fallback
                        if not check_dm_access("discord", user_id):
                            return
                        should_respond = True
            
            # Mention check
            elif self._client.user in message.mentions:
                if self.respond_to_mentions:
                    # Remove the mention from the message
                    content = content.replace(f"<@{self._client.user.id}>", "").strip()
                    content = content.replace(f"<@!{self._client.user.id}>", "").strip()
                    should_respond = True
            
            # Thread messages (non-bound) — respond if in a thread we created
            elif isinstance(message.channel, discord.Thread):
                if message.channel.owner_id == self._client.user.id:
                    should_respond = True
            
            # Command prefix check
            elif content.startswith(self.command_prefix):
                content = content[len(self.command_prefix):].strip()
                should_respond = True
            
            if not should_respond or not content:
                return
            
            # Track usage
            self._usage_stats["message_count"] += 1
            
            # Build attachments list — download text files inline, keep image URLs for VLM
            attachments = []
            for att in message.attachments:
                # Text-based files: download content and inject inline so the LLM can read them
                is_text = (
                    (att.content_type and att.content_type.startswith("text/"))
                    or att.filename.lower().endswith((
                        ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
                        ".py", ".js", ".ts", ".html", ".css", ".sh", ".bat",
                        ".log", ".cfg", ".ini", ".toml", ".env", ".sql",
                    ))
                )
                if is_text:
                    try:
                        file_bytes = await att.read()
                        text_content = file_bytes.decode("utf-8", errors="replace")
                        # Truncate very large files to avoid context overflow
                        if len(text_content) > 50000:
                            text_content = text_content[:50000] + "\n... [truncated, file too large]"
                        content += (
                            f"\n\n--- Attached file: {att.filename} ---\n"
                            f"{text_content}\n"
                            f"--- End of {att.filename} ---"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read text attachment {att.filename}: {e}")
                        attachments.append(att.url)
                else:
                    # Images, PDFs, etc. — pass URL for VLM processing
                    attachments.append(att.url)
            
            
            # --- Lifecycle reactions ---
            async def _react(msg_ref, emoji):
                try:
                    await msg_ref.add_reaction(emoji)
                except Exception as e:
                    logger.debug(f"Could not add reaction {emoji}: {e}")

            async def _unreact(msg_ref, emoji):
                try:
                    await msg_ref.remove_reaction(emoji, self._client.user)
                except Exception as e:
                    logger.debug(f"Could not remove reaction {emoji}: {e}")

            tracker = LifecycleTracker(
                channel_id="discord",
                message_ref=message,
                react_fn=_react,
                unreact_fn=_unreact,
            )

            # Create ChannelMessage with lifecycle tracker
            # Build the reply target so initialize.py knows where to send the response.
            # For DMs, reply back via DM (user:<id>). For channels, reply to the channel.
            is_dm = isinstance(message.channel, discord.DMChannel)
            if is_dm:
                reply_target = f"user:{message.author.id}"
            else:
                reply_target = f"channel:{message.channel.id}"

            channel_msg = ChannelMessage(
                channel_id="discord",
                sender_id=reply_target,
                sender_name=message.author.display_name,
                content=content,
                attachments=attachments,
                metadata={
                    "guild_id": str(message.guild.id) if message.guild else None,
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "is_dm": is_dm,
                    "is_thread": isinstance(message.channel, discord.Thread),
                    "thread_binding": thread_binding,  # None or {target, user_id, bound_at}
                    "session_reset": channel_key in self._session_reset_channels,
                    "lifecycle_tracker": tracker,
                    "model_override": get_model_override("discord"),
                    "discord_message": message,  # For Components v2
                    "reply_target": reply_target,  # Where to send the reply
                    "author_id": str(message.author.id),  # Original author for context
                    "project": project_context,  # None or {project_id, project_name, ...}
                },
            )
            
            # Lifecycle: queued → thinking → done/error
            await tracker.phase("queued")

            try:
                async with message.channel.typing():
                    await tracker.phase("thinking")
                    await self._dispatch_message(channel_msg)
                await tracker.done()
            except Exception as e:
                await tracker.error()
                logger.error(f"Error handling Discord message: {e}")
                raise
        
        # Start the bot (this blocks, so run in background)
        try:
            await self._client.start(token)
        except discord.LoginFailure:
            logger.error("Invalid Discord bot token!")
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
    
    async def stop(self):
        """Stop the Discord bot gracefully."""
        # Stop thread binding cleanup
        await self._thread_manager.stop_cleanup_loop()
        if self._client and not self._client.is_closed():
            await self._client.close()
            logger.info("Discord bot disconnected")
    
    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send a message to a Discord target with full attachment support.
        
        'to' formats:
          - "user:<user_id>" — Send DM to a user
          - "channel:<channel_id>" — Send to a Discord channel
        
        Attachments can be:
          - Local file paths (e.g. "/tmp/output.txt", "/app/image.png")
          - URLs (e.g. "https://cdn.discordapp.com/...")
        
        Long messages (>6000 chars) are automatically uploaded as .txt files.
        """
        if not self._client or self._client.is_closed():
            logger.error("Discord client not connected")
            return False
        
        # Wait for bot to be ready
        await self._ready_event.wait()
        
        try:
            # Handle bare numeric IDs — default to DM (user:)
            if ":" not in str(to):
                to = f"user:{to}"
            target_type, target_id = to.split(":", 1)
            target_id = int(target_id)
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'user:<id>' or 'channel:<id>'")
            return False
        
        try:
            # Build discord.File objects from explicit attachments
            explicit_paths = set(attachments or [])
            discord_files = await self._prepare_attachments(attachments or [])
            
            # Auto-detect file paths in content (skip already-attached ones)
            auto_attachments = [
                p for p in self._extract_file_paths(content)
                if p not in explicit_paths
            ]
            if auto_attachments:
                auto_files = await self._prepare_attachments(auto_attachments)
                discord_files.extend(auto_files)
            
            # For very long messages, upload as a text file instead of
            # splitting into many small chunks (cleaner UX)
            if len(content) > 6000:
                import io
                text_file = discord.File(
                    io.BytesIO(content.encode("utf-8")),
                    filename="response.txt",
                    description="Full response (too long for Discord)"
                )
                discord_files.insert(0, text_file)
                # Truncate the visible message to a preview
                preview = content[:1900] + "\n\n📄 *Full response attached as `response.txt`*"
                content = preview
            
            # Split message into chunks
            chunks = self._split_message(content, max_length=2000)
            
            if target_type == "user":
                user = await self._client.fetch_user(target_id)
                dm_channel = await user.create_dm()
                for i, chunk in enumerate(chunks):
                    # Attach files only on the first chunk
                    files = discord_files if i == 0 else []
                    await dm_channel.send(chunk, files=files)
                    
            elif target_type == "channel":
                channel = self._client.get_channel(target_id)
                if channel is None:
                    channel = await self._client.fetch_channel(target_id)
                
                # Forum channel: auto-create thread
                if isinstance(channel, discord.ForumChannel):
                    first_line = chunks[0].split("\n", 1)[0][:100] or "Skynet"
                    full_content = "\n".join(chunks)
                    thread = await channel.create_thread(
                        name=first_line,
                        content=full_content[:2000],
                        files=discord_files,
                    )
                    if len(full_content) > 2000:
                        remaining = full_content[2000:]
                        for sub_chunk in self._split_message(remaining):
                            await thread.thread.send(sub_chunk)
                else:
                    for i, chunk in enumerate(chunks):
                        files = discord_files if i == 0 else []
                        await channel.send(chunk, files=files)
                    
            else:
                logger.error(f"Unknown target type: {target_type}")
                return False
            
            return True
            
        except discord.Forbidden:
            logger.error(f"Bot lacks permission to send to {to}")
            return False
        except discord.NotFound:
            logger.error(f"Discord target not found: {to}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False
    
    async def _prepare_attachments(self, attachments: List[str]) -> list:
        """
        Convert attachment paths/URLs to discord.File objects.
        
        Handles:
          - Local file paths → read from disk
          - HTTP(S) URLs → download via aiohttp
          - Skips files >25MB (Discord limit)
        """
        import os
        import io
        
        files = []
        for att in attachments:
            try:
                if att.startswith(("http://", "https://")):
                    # Download from URL
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(att, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                logger.warning(f"Failed to download attachment {att}: HTTP {resp.status}")
                                continue
                            data = await resp.read()
                            if len(data) > 25 * 1024 * 1024:  # 25MB Discord limit
                                logger.warning(f"Attachment too large (>25MB): {att}")
                                continue
                            # Extract filename from URL
                            filename = att.split("/")[-1].split("?")[0] or "attachment"
                            files.append(discord.File(io.BytesIO(data), filename=filename))
                else:
                    # Local file path
                    if not os.path.exists(att):
                        logger.warning(f"Attachment file not found: {att}")
                        continue
                    file_size = os.path.getsize(att)
                    if file_size > 25 * 1024 * 1024:
                        logger.warning(f"Attachment too large (>25MB): {att}")
                        continue
                    filename = os.path.basename(att)
                    files.append(discord.File(att, filename=filename))
            except Exception as e:
                logger.warning(f"Failed to prepare attachment {att}: {e}")
        return files
    
    def _extract_file_paths(self, content: str) -> List[str]:
        """
        Auto-detect file paths in response text and return existing ones
        that look like they should be attached (images, files, etc).
        
        This handles the common case where the LLM generates a file
        (e.g. an image) and reports the path in its response text,
        but nobody explicitly passes it as an attachment.
        """
        import re
        import os
        
        # File extensions we should auto-attach
        ATTACHABLE_EXTENSIONS = {
            # Images
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg',
            # Documents
            '.pdf', '.txt', '.csv', '.json', '.xml', '.html',
            # Audio/Video
            '.mp3', '.wav', '.mp4', '.webm', '.ogg',
            # Archives
            '.zip', '.tar', '.gz',
            # Code outputs
            '.py', '.js', '.ts', '.md',
        }
        
        # Patterns to find file paths in text
        # Match: /absolute/path/to/file.ext or `backtick-wrapped paths`
        path_patterns = [
            r'`(/[^\s`]+\.[a-zA-Z0-9]{2,5})`',           # `backtick-quoted` paths
            r'(?:^|[\s:])(/[^\s\'"`,\)]+\.[a-zA-Z0-9]{2,5})',  # bare absolute paths
            r'\*\*Saved to:\*\*\s*`?(/[^\s`]+)`?',        # **Saved to:** /path
            r'saved (?:to|at|in)[:\s]+`?(/[^\s`]+)`?',    # saved to: /path
            r'output[:\s]+`?(/[^\s`]+\.[a-zA-Z0-9]{2,5})`?',  # output: /path
            r'generated[:\s]+`?(/[^\s`]+\.[a-zA-Z0-9]{2,5})`?',  # generated: /path
        ]
        
        found_paths = set()
        for pattern in path_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                path = match.group(1)
                # Verify: must exist, have attachable extension, be under 25MB
                ext = os.path.splitext(path)[1].lower()
                if ext in ATTACHABLE_EXTENSIONS and os.path.isfile(path):
                    file_size = os.path.getsize(path)
                    if file_size <= 25 * 1024 * 1024:
                        found_paths.add(path)
                        logger.info(f"Auto-detected attachable file: {path}")
        
        return list(found_paths)
    
    async def send_confirmation(self, channel, prompt: str) -> Optional[bool]:
        """
        Send a Components v2 confirmation prompt with Approve/Deny buttons.

        Args:
            channel: Discord channel or message to reply to.
            prompt: The text to display with the buttons.

        Returns:
            True if approved, False if denied, None if timed out.
        """
        if not HAS_DISCORD:
            return None

        view = ConfirmationView()
        msg = await channel.send(content=prompt, view=view)
        result = await view.wait_for_result()

        # Clean up buttons if timed out
        if result is None:
            try:
                await msg.edit(content=f"{prompt}\n⏰ *Timed out*", view=None)
            except Exception:
                pass

        return result

    @staticmethod
    def _split_message(content: str, max_length: int = 2000) -> List[str]:
        """Split a long message into chunks that fit Discord's limit."""
        if len(content) <= max_length:
            return [content]
        
        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break
            
            # Try to split at a newline
            split_at = content.rfind("\n", 0, max_length)
            if split_at == -1:
                # Try space
                split_at = content.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length
            
            chunks.append(content[:split_at])
            content = content[split_at:].lstrip()
        
        return chunks
