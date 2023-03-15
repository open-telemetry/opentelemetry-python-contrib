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

from opentelemetry.instrumentation.sqlalchemy.engine import (
    _normalize_vendor,
    _sanitize_query,
)
from opentelemetry.test.test_base import TestBase


class TestSQLAlchemyEngine(TestBase):
    def test_sql_query_sanitization(self):
        sanitized = "SELECT ? FROM ? WHERE ? = ?"
        select1 = "SELECT * FROM users WHERE name = 'John'"
        select2 = "SELECT  * FROM users WHERE name = 'John'"
        select3 = "SELECT\t*\tFROM\tusers\tWHERE\tname\t=\t'John'"

        self.assertEqual(_sanitize_query(select1), sanitized)
        self.assertEqual(_sanitize_query(select2), sanitized)
        self.assertEqual(_sanitize_query(select3), sanitized)
        self.assertEqual(_sanitize_query(""), "")
        self.assertEqual(_sanitize_query(None), "")

    def test_normalize_vendor(self):
        self.assertEqual(_normalize_vendor("mysql"), "mysql")
        self.assertEqual(_normalize_vendor("sqlite"), "sqlite")
        self.assertEqual(_normalize_vendor("sqlite~12345"), "sqlite")
        self.assertEqual(_normalize_vendor("postgres"), "postgresql")
        self.assertEqual(_normalize_vendor("postgres 12345"), "postgresql")
        self.assertEqual(_normalize_vendor("psycopg2"), "postgresql")
        self.assertEqual(_normalize_vendor(""), "db")
        self.assertEqual(_normalize_vendor(None), "db")
