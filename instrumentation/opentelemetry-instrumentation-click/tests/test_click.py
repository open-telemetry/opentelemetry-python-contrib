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

import os
from unittest import mock

import click
import pytest
from click.testing import CliRunner

try:
    from flask import cli as flask_cli
except ImportError:
    flask_cli = None

from opentelemetry.instrumentation.click import ClickInstrumentor
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

    def test_uvicorn_cli_command_ignored(self):
        @click.command("uvicorn")
        def command_uvicorn():
            pass

        runner = CliRunner()
        result = runner.invoke(command_uvicorn)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())

    @pytest.mark.skipif(flask_cli is None, reason="requires flask")
    def test_flask_run_command_ignored(self):
        runner = CliRunner()
        result = runner.invoke(
            flask_cli.run_command, obj=flask_cli.ScriptInfo()
        )
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
