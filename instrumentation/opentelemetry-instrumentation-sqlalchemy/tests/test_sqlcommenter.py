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

import logging
from io import StringIO

from sqlalchemy import create_engine

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.test.test_base import TestBase

log_stream = StringIO()
logging.basicConfig(stream=log_stream, )
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


class TestSqlalchemyInstrumentationWithSQLCommenter(TestBase):

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

    def test_sqlcommenter_enabled(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True
        )
        cnx = engine.connect()
        log_stream.truncate(0)
        log_stream.seek(0)
        cnx.execute("SELECT	1;").fetchall()

        query_log = log_stream.getvalue().split("\n")[0].replace('INFO:sqlalchemy.engine.Engine:', "")
        self.assertRegex(query_log, "SELECT	1;\/\*traceparent=\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}\*\/")

    def test_sqlcommenter_disabled(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider
        )
        cnx = engine.connect()
        log_stream.truncate(0)
        log_stream.seek(0)
        cnx.execute("SELECT	1;").fetchall()

        query_log = log_stream.getvalue().split('\n')[0].replace('INFO:sqlalchemy.engine.Engine:', "")
        self.assertEqual(query_log, "SELECT	1;")

