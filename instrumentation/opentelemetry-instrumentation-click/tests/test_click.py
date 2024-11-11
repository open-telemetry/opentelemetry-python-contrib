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

import click
from click.testing import CliRunner

from opentelemetry.instrumentation.click import ClickInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode


class ClickTestCase(TestBase):
    def setUp(self):
        super().setUp()

        ClickInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        ClickInstrumentor().uninstrument()

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

    def test_uninstrument(self):
        ClickInstrumentor().uninstrument()

        @click.command()
        def notracecommand():
            pass

        runner = CliRunner()
        result = runner.invoke(notracecommand)
        self.assertEqual(result.exit_code, 0)

        self.assertFalse(self.memory_exporter.get_finished_spans())
