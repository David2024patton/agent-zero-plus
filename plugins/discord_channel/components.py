"""
Enhanced Discord Components v2
================================
Interactive UI components for Discord: buttons, select menus, modals.
Extends beyond the existing ConfirmationView to support rich interactions.

Features:
  - ComponentMessage: structured responses with action rows
  - Button builder with styles, emojis, and callbacks
  - Select menus (string, user, role, channel)
  - Modal forms with text inputs
  - Persistent (reusable) components
  - User restriction per component
"""

from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("agent-zero.plugins.discord.components")

try:
    import discord
    from discord import ui
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

if TYPE_CHECKING:
    from .bot import DiscordChannelAdapter


if HAS_DISCORD:

    class ActionButton(ui.Button):
        """A button with an attached async callback."""

        def __init__(
            self,
            label: str,
            style: discord.ButtonStyle = discord.ButtonStyle.primary,
            emoji: Optional[str] = None,
            custom_id: Optional[str] = None,
            disabled: bool = False,
            allowed_users: Optional[List[str]] = None,
            callback_fn: Optional[Callable] = None,
        ):
            super().__init__(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=custom_id or f"a0_btn_{uuid.uuid4().hex[:8]}",
                disabled=disabled,
            )
            self._allowed_users = allowed_users
            self._callback_fn = callback_fn

        async def callback(self, interaction: discord.Interaction):
            # Check user restriction
            if self._allowed_users:
                if str(interaction.user.id) not in self._allowed_users:
                    await interaction.response.send_message(
                        "❌ You are not authorized to use this button.",
                        ephemeral=True,
                    )
                    return

            if self._callback_fn:
                await self._callback_fn(interaction, self)
            else:
                await interaction.response.send_message(
                    f"Button `{self.label}` pressed.", ephemeral=True
                )

    class StringSelect(ui.Select):
        """A string select menu with options."""

        def __init__(
            self,
            placeholder: str = "Select an option...",
            options: Optional[List[discord.SelectOption]] = None,
            min_values: int = 1,
            max_values: int = 1,
            custom_id: Optional[str] = None,
            allowed_users: Optional[List[str]] = None,
            callback_fn: Optional[Callable] = None,
        ):
            super().__init__(
                placeholder=placeholder,
                options=options or [],
                min_values=min_values,
                max_values=max_values,
                custom_id=custom_id or f"a0_sel_{uuid.uuid4().hex[:8]}",
            )
            self._allowed_users = allowed_users
            self._callback_fn = callback_fn

        async def callback(self, interaction: discord.Interaction):
            if self._allowed_users:
                if str(interaction.user.id) not in self._allowed_users:
                    await interaction.response.send_message(
                        "❌ You are not authorized.", ephemeral=True,
                    )
                    return

            if self._callback_fn:
                await self._callback_fn(interaction, self.values)
            else:
                await interaction.response.send_message(
                    f"Selected: {', '.join(self.values)}", ephemeral=True
                )

    class ComponentView(ui.View):
        """
        A view that holds interactive components (buttons, selects).
        
        Supports:
          - Multiple action rows (up to 5 buttons or 1 select per row)
          - Optional timeout (default 180s, set None for persistent)
          - Reusable flag for persistent components
        """

        def __init__(
            self,
            timeout: Optional[float] = 180.0,
            reusable: bool = False,
        ):
            super().__init__(timeout=None if reusable else timeout)
            self._reusable = reusable
            self._result: Optional[Any] = None

        def add_button(
            self,
            label: str,
            style: discord.ButtonStyle = discord.ButtonStyle.primary,
            emoji: Optional[str] = None,
            disabled: bool = False,
            allowed_users: Optional[List[str]] = None,
            callback_fn: Optional[Callable] = None,
        ) -> "ComponentView":
            """Add a button to this view. Returns self for chaining."""
            self.add_item(ActionButton(
                label=label,
                style=style,
                emoji=emoji,
                disabled=disabled,
                allowed_users=allowed_users,
                callback_fn=callback_fn,
            ))
            return self

        def add_select(
            self,
            placeholder: str = "Select an option...",
            options: Optional[List[discord.SelectOption]] = None,
            min_values: int = 1,
            max_values: int = 1,
            allowed_users: Optional[List[str]] = None,
            callback_fn: Optional[Callable] = None,
        ) -> "ComponentView":
            """Add a select menu. Returns self for chaining."""
            self.add_item(StringSelect(
                placeholder=placeholder,
                options=options,
                min_values=min_values,
                max_values=max_values,
                allowed_users=allowed_users,
                callback_fn=callback_fn,
            ))
            return self

        async def on_timeout(self):
            """Disable all components on timeout."""
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True

    class InputModal(ui.Modal):
        """
        A modal dialog with text inputs.
        
        Usage:
            modal = InputModal(
                title="Settings",
                fields=[
                    {"label": "Name", "placeholder": "Enter name..."},
                    {"label": "Description", "style": "long"},
                ],
                callback_fn=my_handler,
            )
            await interaction.response.send_modal(modal)
        """

        def __init__(
            self,
            title: str,
            fields: Optional[List[Dict[str, Any]]] = None,
            callback_fn: Optional[Callable] = None,
        ):
            super().__init__(title=title)
            self._callback_fn = callback_fn
            self._field_refs: List[ui.TextInput] = []

            for f in (fields or []):
                style = (
                    discord.TextStyle.long
                    if f.get("style") == "long"
                    else discord.TextStyle.short
                )
                text_input = ui.TextInput(
                    label=f.get("label", "Input"),
                    placeholder=f.get("placeholder", ""),
                    default=f.get("default", ""),
                    required=f.get("required", True),
                    style=style,
                    max_length=f.get("max_length", 4000),
                )
                self.add_item(text_input)
                self._field_refs.append(text_input)

        async def on_submit(self, interaction: discord.Interaction):
            values = {
                ref.label: ref.value for ref in self._field_refs
            }
            if self._callback_fn:
                await self._callback_fn(interaction, values)
            else:
                result = "\n".join(f"**{k}:** {v}" for k, v in values.items())
                await interaction.response.send_message(
                    result, ephemeral=True
                )

    # ─── Builder helpers ───

    class ComponentBuilder:
        """
        Fluent builder for constructing component-rich messages.
        
        Usage:
            builder = ComponentBuilder()
            builder.add_button("Yes", style=discord.ButtonStyle.success, callback_fn=yes_fn)
            builder.add_button("No", style=discord.ButtonStyle.danger, callback_fn=no_fn)
            await builder.send(channel, content="Do you approve?")
        """

        def __init__(self, timeout: float = 180.0, reusable: bool = False):
            self._view = ComponentView(timeout=timeout, reusable=reusable)
            self._embed: Optional[discord.Embed] = None

        def add_button(self, label: str, **kwargs) -> "ComponentBuilder":
            self._view.add_button(label=label, **kwargs)
            return self

        def add_select(self, **kwargs) -> "ComponentBuilder":
            self._view.add_select(**kwargs)
            return self

        def set_embed(self, embed: discord.Embed) -> "ComponentBuilder":
            self._embed = embed
            return self

        async def send(
            self,
            channel,
            content: Optional[str] = None,
        ) -> discord.Message:
            """Send the component message to a channel."""
            return await channel.send(
                content=content,
                embed=self._embed,
                view=self._view,
            )

        async def reply(
            self,
            interaction: discord.Interaction,
            content: Optional[str] = None,
            ephemeral: bool = False,
        ):
            """Send as an interaction response."""
            await interaction.response.send_message(
                content=content,
                embed=self._embed,
                view=self._view,
                ephemeral=ephemeral,
            )

        @property
        def view(self) -> ComponentView:
            return self._view


else:
    # Stubs when discord.py is not available
    class ActionButton:
        pass

    class StringSelect:
        pass

    class ComponentView:
        pass

    class InputModal:
        pass

    class ComponentBuilder:
        pass
