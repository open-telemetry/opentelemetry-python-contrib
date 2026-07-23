# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=invalid-name,no-name-in-module

from unittest import IsolatedAsyncioTestCase, mock

import discord.app_commands.tree
import discord.ext.commands.bot

from opentelemetry.instrumentation.discord_py import DiscordPyInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestDiscordPyInstrumentor(TestBase, IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        DiscordPyInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        DiscordPyInstrumentor().uninstrument()

    async def test_prefix_command_creates_span(self):
        ctx = mock.Mock()
        ctx.command.qualified_name = "ping"
        ctx.guild.id = 111
        ctx.channel.id = 222
        ctx.author.id = 333

        async def fake_invoke(self, ctx):
            return None

        with mock.patch.object(
            discord.ext.commands.bot.Bot, "invoke", new=fake_invoke
        ):
            # Re-instrument so the patch applied above is what gets wrapped.
            DiscordPyInstrumentor().uninstrument()
            DiscordPyInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
            fake_bot = discord.ext.commands.bot.Bot.__new__(
                discord.ext.commands.bot.Bot
            )
            await fake_bot.invoke(ctx)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "discord.command")
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.attributes["discord.command.name"], "ping")
        self.assertEqual(span.attributes["discord.guild.id"], 111)
        self.assertEqual(span.attributes["discord.channel.id"], 222)
        self.assertEqual(span.attributes["discord.user.id"], 333)

    async def test_prefix_command_records_exception(self):
        ctx = mock.Mock()
        ctx.command = None
        ctx.guild = None
        ctx.channel.id = 222
        ctx.author.id = 333

        async def failing_invoke(self, ctx):
            raise RuntimeError("boom")

        with mock.patch.object(
            discord.ext.commands.bot.Bot, "invoke", new=failing_invoke
        ):
            DiscordPyInstrumentor().uninstrument()
            DiscordPyInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
            fake_bot = discord.ext.commands.bot.Bot.__new__(
                discord.ext.commands.bot.Bot
            )
            with self.assertRaises(RuntimeError):
                await fake_bot.invoke(ctx)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)

    async def test_app_command_creates_span(self):
        interaction = mock.Mock()
        interaction.command.qualified_name = "slash-ping"
        interaction.guild_id = 444
        interaction.channel_id = 555
        interaction.user.id = 666

        async def fake_call(self, interaction):
            return None

        with mock.patch.object(
            discord.app_commands.tree.CommandTree, "_call", new=fake_call
        ):
            DiscordPyInstrumentor().uninstrument()
            DiscordPyInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
            fake_tree = discord.app_commands.tree.CommandTree.__new__(
                discord.app_commands.tree.CommandTree
            )
            await fake_tree._call(interaction)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "discord.app_command")
        self.assertEqual(
            span.attributes["discord.command.name"], "slash-ping"
        )
        self.assertEqual(span.attributes["discord.guild.id"], 444)
        self.assertEqual(span.attributes["discord.channel.id"], 555)
        self.assertEqual(span.attributes["discord.user.id"], 666)
