# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from unittest import IsolatedAsyncioTestCase, mock

import asyncclick
import asyncclick.testing
from asyncclick.testing import CliRunner

from opentelemetry.instrumentation.asyncclick import AsyncClickInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode


def run_asyncclick_command_test(
    command: asyncclick.core.Command, args: tuple[Any, ...] = (), **kwargs: Any
) -> asyncclick.testing.Result:
    """
    Run an asyncclick command and return the result.

    Args:
        command: The AsyncClick command to run
        args: Command-line arguments
        **kwargs: Additional arguments for CliRunner.invoke

    Returns:
        The result of invoking the command
    """

    async def _run() -> asyncclick.testing.Result:
        runner = CliRunner()
        return await runner.invoke(command, args, **kwargs)

    return asyncio.run(_run())


class ClickTestCase(TestBase, IsolatedAsyncioTestCase):
    # pylint: disable=unbalanced-tuple-unpacking
    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()

        AsyncClickInstrumentor().instrument()

    def tearDown(self):  # pylint: disable=invalid-name
        super().tearDown()
        AsyncClickInstrumentor().uninstrument()

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_wrapping(self):
        @asyncclick.command()
        async def command() -> None:
            pass

        result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.kind, SpanKind.INTERNAL)
        self.assertEqual(span.name, "command")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "command.py",
                "process.command_args": ("command.py",),
                "process.exit.code": 0,
                "process.pid": os.getpid(),
            },
        )

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_wrapping_with_name(self):
        @asyncclick.command("mycommand")
        async def renamedcommand() -> None:
            pass

        result = run_asyncclick_command_test(renamedcommand)
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.kind, SpanKind.INTERNAL)
        self.assertEqual(span.name, "mycommand")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "command.py",
                "process.command_args": ("command.py",),
                "process.exit.code": 0,
                "process.pid": os.getpid(),
            },
        )

    @mock.patch("sys.argv", ["command.py", "--opt", "argument"])
    def test_cli_command_wrapping_with_options(self):
        @asyncclick.command()
        @asyncclick.argument("argument")
        @asyncclick.option("--opt/--no-opt", default=False)
        async def command(argument: str, opt: str) -> None:
            pass

        argv = ["command.py", "--opt", "argument"]
        result = run_asyncclick_command_test(command, argv[1:])
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.kind, SpanKind.INTERNAL)
        self.assertEqual(span.name, "command")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "command.py",
                "process.command_args": tuple(argv),
                "process.exit.code": 0,
                "process.pid": os.getpid(),
            },
        )

    @mock.patch("sys.argv", ["command-raises.py"])
    def test_cli_command_raises_error(self):
        @asyncclick.command()
        async def command_raises() -> None:
            raise ValueError()

        result = run_asyncclick_command_test(command_raises)
        self.assertEqual(result.exit_code, 1)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.kind, SpanKind.INTERNAL)
        self.assertEqual(span.name, "command-raises")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "command-raises.py",
                "process.command_args": ("command-raises.py",),
                "process.exit.code": 1,
                "process.pid": os.getpid(),
                "error.type": "ValueError",
            },
        )

    @mock.patch("sys.argv", ["command.py"])
    def test_disabled_when_asgi_instrumentation_loaded(self):
        @asyncclick.command()
        async def command():
            pass

        with mock.patch.dict(
            sys.modules,
            {**sys.modules, "opentelemetry.instrumentation.asgi": mock.Mock()},
        ):
            result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())

    @mock.patch("sys.argv", ["command.py"])
    def test_disabled_when_wsgi_instrumentation_loaded(self):
        @asyncclick.command()
        async def command():
            pass

        with mock.patch.dict(
            sys.modules,
            {**sys.modules, "opentelemetry.instrumentation.wsgi": mock.Mock()},
        ):
            result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())

    def test_uninstrument(self):
        AsyncClickInstrumentor().uninstrument()

        @asyncclick.command()
        async def notracecommand() -> None:
            pass

        result = run_asyncclick_command_test(notracecommand)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())
        AsyncClickInstrumentor().instrument()

    @mock.patch("sys.argv", ["command.py", "sub1", "sub2"])
    def test_nested_command_groups(self):
        """Test instrumentation of nested command groups."""

        @asyncclick.group()
        async def cli() -> None:
            pass

        @cli.group()
        async def sub1() -> None:
            pass

        @sub1.command()
        async def sub2() -> None:
            pass

        result = run_asyncclick_command_test(cli, ["sub1", "sub2"])
        self.assertEqual(result.exit_code, 0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(
            len(spans), 1
        )  # Only the leaf command should be instrumented
        span = spans[0]
        self.assertEqual(span.name, "sub2")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "command.py",
                "process.command_args": ("command.py", "sub1", "sub2"),
                "process.exit.code": 0,
                "process.pid": os.getpid(),
            },
        )

    @mock.patch("sys.argv", ["command.py"])
    def test_command_with_callback(self):
        """Test instrumentation of commands with callbacks."""
        callback_called = False

        def callback_func(
            ctx: asyncclick.Context, param: asyncclick.Parameter, value: bool
        ) -> bool:
            nonlocal callback_called
            callback_called = True
            return value

        @asyncclick.command()
        @asyncclick.option(
            "--option", callback=callback_func, default="default"
        )
        async def command(option: str) -> None:
            pass

        result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(callback_called)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.name, "command")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)

    @mock.patch("sys.argv", ["command.py"])
    def test_command_with_result_callback(self):
        """Test instrumentation with result callbacks."""
        callback_called = False

        @asyncclick.group(chain=True)
        async def cli() -> None:
            pass

        @cli.result_callback()
        async def process_result(result: asyncclick.testing.Result) -> None:
            nonlocal callback_called
            callback_called = True

        @cli.command()
        async def command() -> None:
            pass

        result = run_asyncclick_command_test(cli, ["command"])
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(callback_called)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "command")

    @mock.patch("sys.argv", ["command.py"])
    def test_command_chaining(self):
        """Test instrumentation with command chaining."""

        @asyncclick.group(chain=True)
        async def cli() -> None:
            pass

        @cli.command()
        async def cmd1() -> None:
            return "result1"

        @cli.command()
        async def cmd2() -> None:
            return "result2"

        result = run_asyncclick_command_test(cli, ["cmd1", "cmd2"])
        self.assertEqual(result.exit_code, 0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # Spans should be ordered by execution
        self.assertEqual(spans[0].name, "cmd1")
        self.assertEqual(spans[1].name, "cmd2")

    @mock.patch("sys.argv", ["command.py"])
    def test_custom_exit_codes(self) -> None:
        """Test instrumentation with custom exit codes."""

        @asyncclick.command()
        async def command() -> None:
            raise asyncclick.exceptions.Exit(code=42)

        result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 42)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.name, "command")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["process.exit.code"], 42)
        self.assertEqual(span.attributes["error.type"], "Exit")

    @mock.patch("sys.argv", ["command.py"])
    def test_context_object_passing(self):
        """Test that instrumentation preserves context object passing."""

        @asyncclick.group()
        @asyncclick.option("--debug/--no-debug", default=False)
        @asyncclick.pass_context
        async def cli(ctx: asyncclick.Context, debug: bool) -> None:
            ctx.ensure_object(dict)
            ctx.obj["DEBUG"] = debug

        @cli.command()
        @asyncclick.pass_context
        async def command(ctx: asyncclick.Context) -> None:
            assert isinstance(ctx.obj, dict)
            assert "DEBUG" in ctx.obj

        result = run_asyncclick_command_test(cli, ["--debug", "command"])
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.name, "command")

    def test_multiple_instrumentation(self):
        """Test that instrumenting multiple times only applies once."""
        # Already instrumented in setUp, instrument again
        AsyncClickInstrumentor().instrument()

        @asyncclick.command()
        async def command() -> None:
            pass

        result = run_asyncclick_command_test(command)
        self.assertEqual(result.exit_code, 0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_concurrency(self):
        """Test instrumentation with concurrent command execution."""

        @asyncclick.command()
        async def command1() -> None:
            pass

        @asyncclick.command()
        async def command2() -> None:
            pass

        async def run_both() -> tuple[
            asyncclick.testing.Result, asyncclick.testing.Result
        ]:
            runner = CliRunner()
            task1 = asyncio.create_task(runner.invoke(command1))
            task2 = asyncio.create_task(runner.invoke(command2))
            results = await asyncio.gather(task1, task2)
            return results

        results = asyncio.run(run_both())
        self.assertEqual(results[0].exit_code, 0)
        self.assertEqual(results[1].exit_code, 0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        span_names = [span.name for span in spans]
        self.assertIn("command1", span_names)
        self.assertIn("command2", span_names)
