# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
This library allows tracing discord.py bots: prefix commands (``ext.commands``)
and application/slash commands (``discord.app_commands``) are wrapped in spans
automatically once instrumented.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.discord_py import DiscordPyInstrumentor

    DiscordPyInstrumentor().instrument()

    # ... create and run your discord.py Bot as usual

Every prefix command invocation produces a span named ``discord.command`` and
every application (slash) command invocation produces a span named
``discord.app_command``. Both carry ``discord.command.name``,
``discord.guild.id``, ``discord.channel.id`` and ``discord.user.id`` as
attributes.

API
---
"""

# pylint: disable=no-name-in-module,no-self-use

from typing import Collection

import discord.app_commands.tree
import discord.ext.commands.bot
import wrapt

from opentelemetry.instrumentation.discord_py.package import _instruments
from opentelemetry.instrumentation.discord_py.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import SpanKind, Status, StatusCode, get_tracer

_PREFIX_COMMAND_SPAN_NAME = "discord.command"
_APP_COMMAND_SPAN_NAME = "discord.app_command"


def _set_common_attributes(span, *, guild_id, channel_id, user_id, command_name):
    """Attach the low-cardinality attributes every discord.py span carries.

    ``None`` values are dropped rather than set, so call sites can pass
    optional discord.py fields (e.g. ``guild_id`` on a DM interaction)
    without branching.
    """
    if command_name is not None:
        span.set_attribute("discord.command.name", command_name)
    if guild_id is not None:
        span.set_attribute("discord.guild.id", guild_id)
    if channel_id is not None:
        span.set_attribute("discord.channel.id", channel_id)
    if user_id is not None:
        span.set_attribute("discord.user.id", user_id)


class DiscordPyInstrumentor(BaseInstrumentor):
    """An instrumentor for discord.py.

    See `BaseInstrumentor`.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        wrapt.wrap_function_wrapper(
            "discord.ext.commands.bot",
            "Bot.invoke",
            _wrap_prefix_command_invoke(tracer),
        )
        wrapt.wrap_function_wrapper(
            "discord.app_commands.tree",
            "CommandTree._call",
            _wrap_app_command_call(tracer),
        )

    def _uninstrument(self, **kwargs):
        unwrap(discord.ext.commands.bot.Bot, "invoke")
        unwrap(discord.app_commands.tree.CommandTree, "_call")


def _wrap_prefix_command_invoke(tracer):
    async def wrapper(wrapped, instance, args, kwargs):
        # signature: Bot.invoke(self, ctx)
        ctx = args[0] if args else kwargs.get("ctx")
        command = getattr(ctx, "command", None)
        command_name = command.qualified_name if command else None

        with tracer.start_as_current_span(
            _PREFIX_COMMAND_SPAN_NAME,
            kind=SpanKind.SERVER,
        ) as span:
            if span.is_recording():
                _set_common_attributes(
                    span,
                    guild_id=getattr(getattr(ctx, "guild", None), "id", None),
                    channel_id=getattr(getattr(ctx, "channel", None), "id", None),
                    user_id=getattr(getattr(ctx, "author", None), "id", None),
                    command_name=command_name,
                )
            try:
                return await wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise

    return wrapper


def _wrap_app_command_call(tracer):
    async def wrapper(wrapped, instance, args, kwargs):
        # signature: CommandTree._call(self, interaction)
        interaction = args[0] if args else kwargs.get("interaction")

        with tracer.start_as_current_span(
            _APP_COMMAND_SPAN_NAME,
            kind=SpanKind.SERVER,
        ) as span:
            try:
                return await wrapped(*args, **kwargs)
            finally:
                # The command isn't resolved on the interaction until
                # after ``_call`` runs its internal lookup, so read it back
                # out afterwards rather than before invoking ``wrapped``.
                if span.is_recording():
                    command = getattr(interaction, "command", None)
                    command_name = (
                        command.qualified_name if command else None
                    )
                    _set_common_attributes(
                        span,
                        guild_id=getattr(interaction, "guild_id", None),
                        channel_id=getattr(interaction, "channel_id", None),
                        user_id=getattr(
                            getattr(interaction, "user", None), "id", None
                        ),
                        command_name=command_name,
                    )

    return wrapper
