# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import importlib
import os
import sys
import types
from unittest import mock

import click
import pytest
from click.testing import CliRunner

try:
    from flask import cli as flask_cli
except ImportError:
    flask_cli = None

try:
    import uvicorn
except ImportError:
    uvicorn = None

from opentelemetry.instrumentation.click import ClickInstrumentor, _skip_servers
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode


class ClickTestCase(TestBase):
    # pylint: disable=unbalanced-tuple-unpacking
    def setUp(self):
        super().setUp()

        ClickInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        ClickInstrumentor().uninstrument()

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_wrapping(self):
        @click.command()
        def command():
            pass

        runner = CliRunner()
        result = runner.invoke(command)
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

    @mock.patch("sys.argv", ["flask", "command"])
    def test_flask_command_wrapping(self):
        @click.command()
        def command():
            pass

        runner = CliRunner()
        result = runner.invoke(command)
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.kind, SpanKind.INTERNAL)
        self.assertEqual(span.name, "command")
        self.assertEqual(
            dict(span.attributes),
            {
                "process.executable.name": "flask",
                "process.command_args": (
                    "flask",
                    "command",
                ),
                "process.exit.code": 0,
                "process.pid": os.getpid(),
            },
        )

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_wrapping_with_name(self):
        @click.command("mycommand")
        def renamedcommand():
            pass

        runner = CliRunner()
        result = runner.invoke(renamedcommand)
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
        @click.command()
        @click.argument("argument")
        @click.option("--opt/--no-opt", default=False)
        def command(argument, opt):
            pass

        argv = ["command.py", "--opt", "argument"]
        runner = CliRunner()
        result = runner.invoke(command, argv[1:])
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
        @click.command()
        def command_raises():
            raise ValueError()

        runner = CliRunner()
        result = runner.invoke(command_raises)
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
        self.assertEqual([event.name for event in span.events], ["exception"])

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_ctx_exit_zero_is_not_an_error(self):
        @click.command()
        @click.pass_context
        def command(ctx):
            ctx.exit(0)

        result = CliRunner().invoke(command)
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["process.exit.code"], 0)
        self.assertNotIn("error.type", span.attributes)
        self.assertEqual(span.events, ())

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_ctx_exit_nonzero_is_an_error(self):
        @click.command()
        @click.pass_context
        def command(ctx):
            ctx.exit(2)

        result = CliRunner().invoke(command)
        self.assertEqual(result.exit_code, 2)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["process.exit.code"], 2)
        self.assertEqual(span.attributes["error.type"], "Exit")

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_sys_exit_records_exit_code(self):
        @click.command()
        def command():
            raise SystemExit(3)

        result = CliRunner().invoke(command)
        self.assertEqual(result.exit_code, 3)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["process.exit.code"], 3)
        self.assertEqual(span.attributes["error.type"], "SystemExit")

    @mock.patch("sys.argv", ["command.py"])
    def test_cli_command_sys_exit_none_is_not_an_error(self):
        @click.command()
        def command():
            raise SystemExit()

        result = CliRunner().invoke(command)
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["process.exit.code"], 0)
        self.assertNotIn("error.type", span.attributes)

    def test_uvicorn_cli_command_ignored(self):
        @click.command("uvicorn")
        def command_uvicorn():
            pass

        runner = CliRunner()
        result = runner.invoke(command_uvicorn)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())

    def test_skip_servers_python_m_uvicorn(self):
        @click.command()
        def command():
            pass

        # Click's _detect_program_name always uses the literal "python"
        # prefix. Also accept other interpreter basenames so a synthetic
        # context matches `python3 -m uvicorn` and `python3.12 -m uvicorn`.
        for info_name in (
            "python -m uvicorn",
            "python3 -m uvicorn",
            "python3.12 -m uvicorn",
            "python -m uvicorn.main",
        ):
            with self.subTest(info_name=info_name):
                ctx = click.Context(command, info_name=info_name)
                self.assertTrue(_skip_servers(ctx))

        for info_name in ("python -m flask", "routes", "upgrade", "flask"):
            with self.subTest(info_name=info_name):
                ctx = click.Context(command, info_name=info_name)
                self.assertFalse(_skip_servers(ctx))

        def server():
            pass

        server.__module__ = "uvicorn.main"
        ctx = click.Context(click.command("main")(server), info_name="main")
        self.assertTrue(_skip_servers(ctx))

    def test_python_m_uvicorn_program_name_ignored(self):
        @click.command()
        def command():
            pass

        for program_name in (
            "python -m uvicorn",
            "python3 -m uvicorn",
            "python3.12 -m uvicorn",
            "python -m uvicorn.main",
        ):
            with self.subTest(program_name=program_name):
                self.memory_exporter.clear()
                result = CliRunner().invoke(command, prog_name=program_name)
                self.assertEqual(result.exit_code, 0)
                self.assertFalse(self.memory_exporter.get_finished_spans())

    @pytest.mark.skipif(uvicorn is None, reason="requires uvicorn")
    def test_python_m_uvicorn_invocation_ignored(self):
        entry = importlib.import_module("uvicorn.__main__")
        server_module = importlib.import_module("uvicorn.main")
        cases = (
            ("uvicorn", entry.__file__),
            ("uvicorn", server_module.__file__),
        )
        for package, argv0 in cases:
            with self.subTest(argv0=argv0):
                self.memory_exporter.clear()
                main_module = types.ModuleType("__main__")
                main_module.__package__ = package
                main_module.__file__ = argv0
                with (
                    mock.patch.dict(sys.modules, {"__main__": main_module}),
                    mock.patch("sys.argv", [argv0, "app:app"]),
                    mock.patch.object(server_module, "run") as run,
                ):
                    result = click.Command.main(
                        server_module.main,
                        args=["app:app"],
                        standalone_mode=False,
                    )
                self.assertIsNone(result)
                run.assert_called_once()
                self.assertFalse(self.memory_exporter.get_finished_spans())

    @pytest.mark.skipif(flask_cli is None, reason="requires flask")
    @mock.patch.dict(
        sys.modules, {"opentelemetry.instrumentation.asgi": types.ModuleType("opentelemetry.instrumentation.asgi")}
    )
    def test_flask_management_command_is_traced(self):
        @click.command("upgrade")
        def upgrade():
            pass

        result = CliRunner().invoke(upgrade, obj=flask_cli.ScriptInfo())
        self.assertEqual(result.exit_code, 0)

        (span,) = self.memory_exporter.get_finished_spans()
        self.assertEqual(span.name, "upgrade")

    @pytest.mark.skipif(flask_cli is None, reason="requires flask")
    def test_flask_run_command_ignored(self):
        runner = CliRunner()
        result = runner.invoke(flask_cli.run_command, obj=flask_cli.ScriptInfo())
        self.assertEqual(result.exit_code, 2)

        self.assertFalse(self.memory_exporter.get_finished_spans())

    def test_uninstrument(self):
        ClickInstrumentor().uninstrument()

        @click.command()
        def notracecommand():
            pass

        runner = CliRunner()
        result = runner.invoke(notracecommand)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())
