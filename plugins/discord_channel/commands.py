"""
Discord Slash Commands for Agent Zero
=======================================
Native Discord slash commands (application commands) modeled after OpenClaw's
slash command system. Requires discord.py >= 2.0.

Commands:
  /help          - Show available commands
  /status        - Show bot status, active model, uptime
  /model         - Switch or list available models
  /reset         - Clear context / start new session
  /stop          - Abort current processing
  /whoami        - Show sender ID and permissions
  /agents        - List active sub-agents for session
  /focus         - Bind current/new thread to a sub-agent target
  /unfocus       - Remove current thread binding
  /subagents     - Manage sub-agents (list/kill/steer)
  /config        - View/modify settings (owner-only)
  /verbose       - Toggle verbose output
  /usage         - Show token usage stats
  /clear         - Clear message history
"""

from __future__ import annotations
import os
import time
import logging
import platform
from typing import Optional, TYPE_CHECKING

logger = logging.getLogger("agent-zero.plugins.discord.commands")

try:
    import discord
    from discord import app_commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

if TYPE_CHECKING:
    from .bot import DiscordChannelAdapter


# ─── Start time for uptime calculation ───
_start_time = time.time()


def _format_uptime() -> str:
    """Format uptime as human-readable string."""
    elapsed = int(time.time() - _start_time)
    days, remainder = divmod(elapsed, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


if HAS_DISCORD:

    class AgentZeroCommands(app_commands.Group):
        """
        Agent Zero slash commands — registered as /a0 <subcommand>.
        
        This uses a command group so all commands appear as:
          /a0 help, /a0 status, /a0 model, etc.
        """

        def __init__(self, adapter: "DiscordChannelAdapter"):
            super().__init__(name="a0", description="Agent Zero commands")
            self.adapter = adapter

        # ─── /a0 help ───
        @app_commands.command(name="help", description="Show all Agent Zero commands")
        async def cmd_help(self, interaction: discord.Interaction):
            embed = discord.Embed(
                title="🤖 Agent Zero Commands",
                description="Use `/a0 <command>` to interact with Agent Zero.",
                color=0x5865F2,
            )
            commands_list = [
                ("`/a0 help`", "Show this help message"),
                ("`/a0 status`", "Show bot status, model, and uptime"),
                ("`/a0 model [name]`", "Switch or list available models"),
                ("`/a0 reset`", "Clear session and start fresh"),
                ("`/a0 stop`", "Abort current processing"),
                ("`/a0 whoami`", "Show your user ID and permissions"),
                ("`/a0 agents`", "List active sub-agents & thread bindings"),
                ("`/a0 focus [target]`", "Bind this thread to a sub-agent"),
                ("`/a0 unfocus`", "Remove thread binding"),
                ("`/a0 approve [code]`", "Approve a DM pairing code"),
                ("`/a0 pair`", "Show pending pairing requests"),
                ("`/a0 subagents [action]`", "Manage sub-agents (list/kill)"),
                ("`/a0 verbose [on|off]`", "Toggle verbose output"),
                ("`/a0 usage`", "Show token usage stats"),
                ("`/a0 config [key] [value]`", "View/modify settings (owner-only)"),
                ("`/a0 clear`", "Clear message history"),
            ]
            for name, desc in commands_list:
                embed.add_field(name=name, value=desc, inline=False)
            embed.set_footer(text="Agent Zero • OpenClaw-compatible commands")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ─── /a0 status ───
        @app_commands.command(name="status", description="Show bot status, active model, and uptime")
        async def cmd_status(self, interaction: discord.Interaction):
            uptime = _format_uptime()
            guild_count = len(self.adapter._client.guilds) if self.adapter._client else 0
            
            # Try to get current model from settings/env
            current_model = os.environ.get("CHAT_MODEL", os.environ.get("MODEL_CHAT", "unknown"))
            util_model = os.environ.get("UTILITY_MODEL", os.environ.get("MODEL_UTILITY", "unknown"))
            
            embed = discord.Embed(
                title="📊 Agent Zero Status",
                color=0x00D26A,
            )
            embed.add_field(name="⏱️ Uptime", value=uptime, inline=True)
            embed.add_field(name="🏠 Servers", value=str(guild_count), inline=True)
            embed.add_field(name="🧠 Chat Model", value=f"`{current_model}`", inline=False)
            embed.add_field(name="🔧 Utility Model", value=f"`{util_model}`", inline=False)
            embed.add_field(name="💻 Platform", value=f"{platform.system()} {platform.release()}", inline=True)
            embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)
            
            # Sub-agent count
            if hasattr(self.adapter, '_subagent_manager') and self.adapter._subagent_manager:
                all_subs = self.adapter._subagent_manager.list_all()
                embed.add_field(name="🤖 Active Sub-agents", value=str(len(all_subs)), inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ─── /a0 whoami ───
        @app_commands.command(name="whoami", description="Show your Discord user ID and permissions")
        async def cmd_whoami(self, interaction: discord.Interaction):
            user = interaction.user
            is_owner = (
                self.adapter.owner_user_id
                and str(user.id) == self.adapter.owner_user_id
            )
            
            embed = discord.Embed(
                title="👤 Who Am I",
                color=0x5865F2,
            )
            embed.add_field(name="User", value=f"{user.display_name} (`{user.name}`)", inline=False)
            embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
            embed.add_field(name="Is Owner", value="✅ Yes" if is_owner else "❌ No", inline=True)
            
            if interaction.guild:
                roles = [r.name for r in user.roles if r.name != "@everyone"]
                embed.add_field(
                    name="Roles",
                    value=", ".join(f"`{r}`" for r in roles) if roles else "None",
                    inline=False,
                )
                embed.add_field(name="Guild ID", value=f"`{interaction.guild.id}`", inline=True)
                embed.add_field(name="Channel ID", value=f"`{interaction.channel.id}`", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ─── /a0 model ───
        @app_commands.command(name="model", description="Switch or list available models")
        @app_commands.describe(name="Model name to switch to (leave empty to list current)")
        async def cmd_model(self, interaction: discord.Interaction, name: Optional[str] = None):
            if name is None:
                # Show current model
                current = os.environ.get("CHAT_MODEL", os.environ.get("MODEL_CHAT", "not set"))
                await interaction.response.send_message(
                    f"🧠 **Current model:** `{current}`\n"
                    f"Use `/a0 model <name>` to switch.",
                    ephemeral=True,
                )
            else:
                # Set model via env (will take effect on next message)
                os.environ["CHAT_MODEL"] = name
                os.environ["MODEL_CHAT"] = name
                await interaction.response.send_message(
                    f"✅ Model switched to: `{name}`\n"
                    f"This will take effect on the next message.",
                    ephemeral=True,
                )

        # ─── /a0 reset ───
        @app_commands.command(name="reset", description="Clear session context and start fresh")
        async def cmd_reset(self, interaction: discord.Interaction):
            # Signal to the adapter that this session should be cleared
            channel_id = str(interaction.channel.id)
            if hasattr(self.adapter, '_session_reset_channels'):
                self.adapter._session_reset_channels.add(channel_id)
            await interaction.response.send_message(
                "🔄 **Session reset.** Context cleared — next message starts fresh.",
                ephemeral=False,
            )

        # ─── /a0 stop ───
        @app_commands.command(name="stop", description="Abort current processing")
        async def cmd_stop(self, interaction: discord.Interaction):
            # Set abort flag for current processing
            if hasattr(self.adapter, '_abort_channels'):
                self.adapter._abort_channels.add(str(interaction.channel.id))
            await interaction.response.send_message(
                "🛑 **Stop requested.** Current processing will be aborted.",
                ephemeral=False,
            )

        # ─── /a0 clear ───
        @app_commands.command(name="clear", description="Clear message history for this channel")
        async def cmd_clear(self, interaction: discord.Interaction):
            channel_id = str(interaction.channel.id)
            if hasattr(self.adapter, '_session_reset_channels'):
                self.adapter._session_reset_channels.add(channel_id)
            await interaction.response.send_message(
                "🧹 **History cleared.** All previous context has been removed.",
                ephemeral=False,
            )

        # ─── /a0 verbose ───
        @app_commands.command(name="verbose", description="Toggle verbose output mode")
        @app_commands.describe(mode="on, off, or full")
        @app_commands.choices(mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
            app_commands.Choice(name="full", value="full"),
        ])
        async def cmd_verbose(self, interaction: discord.Interaction, mode: Optional[app_commands.Choice[str]] = None):
            if mode is None:
                current = getattr(self.adapter, '_verbose_mode', 'off')
                await interaction.response.send_message(
                    f"📝 **Verbose mode:** `{current}`",
                    ephemeral=True,
                )
            else:
                self.adapter._verbose_mode = mode.value
                emoji = "📝" if mode.value == "on" else "📋" if mode.value == "full" else "🔇"
                await interaction.response.send_message(
                    f"{emoji} **Verbose mode:** `{mode.value}`",
                    ephemeral=True,
                )

        # ─── /a0 usage ───
        @app_commands.command(name="usage", description="Show token usage statistics")
        async def cmd_usage(self, interaction: discord.Interaction):
            stats = getattr(self.adapter, '_usage_stats', {})
            if not stats:
                await interaction.response.send_message(
                    "📊 No usage data available yet. Send some messages first!",
                    ephemeral=True,
                )
                return
            
            embed = discord.Embed(title="📊 Token Usage", color=0xFFA500)
            embed.add_field(
                name="Prompt Tokens",
                value=f"`{stats.get('prompt_tokens', 0):,}`",
                inline=True,
            )
            embed.add_field(
                name="Completion Tokens",
                value=f"`{stats.get('completion_tokens', 0):,}`",
                inline=True,
            )
            embed.add_field(
                name="Total",
                value=f"`{stats.get('total_tokens', 0):,}`",
                inline=True,
            )
            embed.add_field(
                name="Messages",
                value=f"`{stats.get('message_count', 0)}`",
                inline=True,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ─── /a0 agents ───
        @app_commands.command(name="agents", description="List active sub-agents and thread bindings")
        async def cmd_agents(self, interaction: discord.Interaction):
            embed = discord.Embed(title="🤖 Agents & Thread Bindings", color=0x5865F2)
            
            # Sub-agents
            if hasattr(self.adapter, '_subagent_manager') and self.adapter._subagent_manager:
                all_agents = self.adapter._subagent_manager.list_all()
                if all_agents:
                    for parent_id, children in all_agents.items():
                        child_list = "\n".join(
                            f"• `{cid}` — {info.get('name', 'unnamed')}"
                            for cid, info in children.items()
                        )
                        embed.add_field(
                            name=f"Parent: `{parent_id}`",
                            value=child_list or "No children",
                            inline=False,
                        )
                else:
                    embed.add_field(name="Sub-Agents", value="No active sub-agents", inline=False)
            
            # Thread bindings
            if hasattr(self.adapter, '_thread_manager'):
                tm = self.adapter._thread_manager
                bindings = tm.list_bindings()
                if bindings:
                    binding_lines = []
                    for b in bindings:
                        idle = round((time.time() - b.last_active) / 3600, 1)
                        binding_lines.append(
                            f"• <#{b.thread_id}> → `{b.target}` "
                            f"({b.message_count} msgs, idle {idle}h)"
                        )
                    embed.add_field(
                        name=f"🔗 Thread Bindings ({len(bindings)})",
                        value="\n".join(binding_lines),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="🔗 Thread Bindings",
                        value="No active bindings",
                        inline=False,
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ─── /a0 focus ───
        @app_commands.command(name="focus", description="Bind this thread to a sub-agent or session target")
        @app_commands.describe(target="Sub-agent ID or session key to bind to this thread")
        async def cmd_focus(self, interaction: discord.Interaction, target: str):
            # Check if thread manager is available
            tm = getattr(self.adapter, '_thread_manager', None)
            if tm is None:
                await interaction.response.send_message(
                    "❌ Thread bindings are not enabled. "
                    "Set `threadBindings.enabled = true` in Discord plugin settings.",
                    ephemeral=True,
                )
                return
            
            channel = interaction.channel
            
            # If not in a thread, create one
            if not isinstance(channel, (discord.Thread,)):
                if isinstance(channel, discord.TextChannel):
                    thread = await channel.create_thread(
                        name=f"🤖 {target}"[:100],
                        type=discord.ChannelType.public_thread,
                    )
                    tm.bind(
                        thread_id=str(thread.id),
                        target=target,
                        user_id=str(interaction.user.id),
                        guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                        metadata={"auto_created": True},
                    )
                    await interaction.response.send_message(
                        f"🔗 Created and bound thread {thread.mention} → `{target}`",
                        ephemeral=False,
                    )
                    await thread.send(
                        f"🔗 **Thread bound to:** `{target}`\n"
                        "All messages here route to this target.\n"
                        "Use `/a0 unfocus` to unbind."
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Cannot create threads in this channel type.",
                        ephemeral=True,
                    )
                return
            
            # Already in a thread — bind it
            tm.bind(
                thread_id=str(channel.id),
                target=target,
                user_id=str(interaction.user.id),
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            )
            await interaction.response.send_message(
                f"🔗 **Thread bound** → `{target}`\nAll messages here now route to this target.",
                ephemeral=False,
            )

        # ─── /a0 unfocus ───
        @app_commands.command(name="unfocus", description="Remove the current thread binding")
        async def cmd_unfocus(self, interaction: discord.Interaction):
            tm = getattr(self.adapter, '_thread_manager', None)
            if tm is None:
                await interaction.response.send_message(
                    "❌ Thread bindings are not enabled.",
                    ephemeral=True,
                )
                return
            
            channel = interaction.channel
            thread_id = str(channel.id)
            
            binding = tm.unbind(thread_id)
            if binding:
                await interaction.response.send_message(
                    f"🔓 **Thread unbound** from `{binding.target}`.\n"
                    f"Had {binding.message_count} messages. "
                    "Messages here will route normally.",
                    ephemeral=False,
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ This thread has no active binding.",
                    ephemeral=True,
                )

        # ─── /a0 subagents ───
        @app_commands.command(name="subagents", description="Manage sub-agents (list, kill)")
        @app_commands.describe(action="Action to perform")
        @app_commands.choices(action=[
            app_commands.Choice(name="list", value="list"),
            app_commands.Choice(name="kill all", value="kill_all"),
        ])
        async def cmd_subagents(
            self,
            interaction: discord.Interaction,
            action: app_commands.Choice[str],
        ):
            if action.value == "list":
                await self.cmd_agents.callback(self, interaction)
                return
            
            if action.value == "kill_all":
                if hasattr(self.adapter, '_subagent_manager') and self.adapter._subagent_manager:
                    # Clear all sub-agents
                    mgr = self.adapter._subagent_manager
                    all_agents = mgr.list_all()
                    count = sum(len(children) for children in all_agents.values())
                    mgr._children.clear()
                    await interaction.response.send_message(
                        f"🛑 Killed **{count}** sub-agent(s).",
                        ephemeral=False,
                    )
                else:
                    await interaction.response.send_message(
                        "🤖 No sub-agent manager active.",
                        ephemeral=True,
                    )

        # ─── /a0 config ───
        @app_commands.command(name="config", description="View or modify settings (owner-only)")
        @app_commands.describe(
            action="show, get, or set",
            key="Config key (for get/set)",
            value="New value (for set)",
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="show", value="show"),
            app_commands.Choice(name="get", value="get"),
            app_commands.Choice(name="set", value="set"),
        ])
        async def cmd_config(
            self,
            interaction: discord.Interaction,
            action: app_commands.Choice[str],
            key: Optional[str] = None,
            value: Optional[str] = None,
        ):
            # Owner-only check
            if self.adapter.owner_user_id and str(interaction.user.id) != self.adapter.owner_user_id:
                await interaction.response.send_message(
                    "🔒 **Owner-only command.** You are not authorized.",
                    ephemeral=True,
                )
                return
            
            if action.value == "show":
                config_items = {
                    "owner_user_id": self.adapter.owner_user_id or "not set",
                    "command_prefix": self.adapter.command_prefix,
                    "respond_to_dms": str(self.adapter.respond_to_dms),
                    "respond_to_mentions": str(self.adapter.respond_to_mentions),
                    "verbose_mode": getattr(self.adapter, '_verbose_mode', 'off'),
                    "thread_bindings": f"{len(self.adapter._thread_manager.list_bindings())} active" if hasattr(self.adapter, '_thread_manager') else "disabled",
                    "dm_policy": self.adapter._pairing_manager.policy if hasattr(self.adapter, '_pairing_manager') else "unknown",
                    "allowed_users": str(len(self.adapter._pairing_manager.list_allowed())) if hasattr(self.adapter, '_pairing_manager') else "unknown",
                    "pending_pairing": str(len(self.adapter._pairing_manager.list_pending())) if hasattr(self.adapter, '_pairing_manager') else "0",
                }
                embed = discord.Embed(title="⚙️ Configuration", color=0x5865F2)
                for k, v in config_items.items():
                    embed.add_field(name=f"`{k}`", value=f"`{v}`", inline=True)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif action.value == "get":
                if not key:
                    await interaction.response.send_message(
                        "❌ Provide a `key` to look up.",
                        ephemeral=True,
                    )
                    return
                val = getattr(self.adapter, key, None)
                if val is None:
                    val = os.environ.get(key, "not found")
                await interaction.response.send_message(
                    f"⚙️ `{key}` = `{val}`",
                    ephemeral=True,
                )
            
            elif action.value == "set":
                if not key or value is None:
                    await interaction.response.send_message(
                        "❌ Provide both `key` and `value`.",
                        ephemeral=True,
                    )
                    return
                # Apply to env for runtime override
                os.environ[key] = value
                await interaction.response.send_message(
                    f"✅ Set `{key}` = `{value}` (runtime override)",
                    ephemeral=True,
                )

        # ─── /a0 approve ───
        @app_commands.command(name="approve", description="Approve a DM pairing code (owner-only)")
        @app_commands.describe(code="The pairing code to approve")
        async def cmd_approve(self, interaction: discord.Interaction, code: str):
            # Owner-only
            if self.adapter.owner_user_id and str(interaction.user.id) != self.adapter.owner_user_id:
                await interaction.response.send_message(
                    "🔒 **Owner-only command.** You are not authorized.",
                    ephemeral=True,
                )
                return
            
            pm = getattr(self.adapter, '_pairing_manager', None)
            if pm is None:
                await interaction.response.send_message(
                    "❌ Pairing manager is not available.",
                    ephemeral=True,
                )
                return
            
            request = pm.approve_code(code)
            if request:
                await interaction.response.send_message(
                    f"✅ **Approved!** User `{request.sender_name}` "
                    f"(`{request.sender_id}`) can now DM the bot.",
                    ephemeral=False,
                )
                # Notify the user in DM
                try:
                    user = await self.adapter._client.fetch_user(int(request.sender_id))
                    if user:
                        await user.send(
                            "✅ **Pairing approved!** You can now chat with me directly."
                        )
                except Exception:
                    pass  # Best effort DM
            else:
                await interaction.response.send_message(
                    "❌ Invalid or expired pairing code.",
                    ephemeral=True,
                )

        # ─── /a0 pair ───
        @app_commands.command(name="pair", description="Show pending pairing requests (owner-only)")
        async def cmd_pair(self, interaction: discord.Interaction):
            # Owner-only
            if self.adapter.owner_user_id and str(interaction.user.id) != self.adapter.owner_user_id:
                await interaction.response.send_message(
                    "🔒 **Owner-only command.** You are not authorized.",
                    ephemeral=True,
                )
                return
            
            pm = getattr(self.adapter, '_pairing_manager', None)
            if pm is None:
                await interaction.response.send_message(
                    "❌ Pairing manager is not available.",
                    ephemeral=True,
                )
                return
            
            pending = pm.list_pending()
            if not pending:
                await interaction.response.send_message(
                    "📋 No pending pairing requests.",
                    ephemeral=True,
                )
                return
            
            embed = discord.Embed(
                title="🔐 Pending Pairing Requests",
                color=0xFFA500,
            )
            for req in pending:
                embed.add_field(
                    name=f"`{req.code}`",
                    value=(
                        f"**User:** {req.sender_name} (`{req.sender_id}`)\n"
                        f"**Expires in:** {req.remaining_minutes()} min"
                    ),
                    inline=False,
                )
            embed.set_footer(text="Use /a0 approve <code> to approve")
            await interaction.response.send_message(embed=embed, ephemeral=True)


    def setup_commands(adapter: "DiscordChannelAdapter", tree: app_commands.CommandTree):
        """Register all Agent Zero slash commands on the command tree."""
        group = AgentZeroCommands(adapter=adapter)
        tree.add_command(group)
        logger.info("Registered /a0 slash command group")
        return group


else:
    # Stub when discord.py is not installed
    class AgentZeroCommands:
        pass

    def setup_commands(adapter, tree):
        logger.warning("discord.py not available — slash commands disabled")
        return None
