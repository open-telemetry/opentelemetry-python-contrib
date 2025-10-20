# Copyright 2025, OpenTelemetry Authors
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

import mysql.connector

from opentelemetry.instrumentation.mysql import MySQLInstrumentor
from opentelemetry.test.test_base import TestBase

MYSQL_USER = os.getenv("MYSQL_USER", "testuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "testpassword")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB_NAME = os.getenv("MYSQL_DB_NAME", "opentelemetry-tests")

class TestFunctionalMySqlCommenter(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        MySQLInstrumentor().instrument(enable_commenter=True)
        self._connection = mysql.connector.connect(
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DB_NAME,
        )
        self._cursor = self._connection.cursor()

    def tearDown(self):
        self._cursor.close()
        self._connection.close()
        MySQLInstrumentor().uninstrument()
        super().tearDown()

    def test_commenter_enabled(self):
        self._cursor.execute("SELECT  1;")
        self.assertRegex(
            self._cursor._query.query.decode("ascii"),
            r"SELECT  1 /\*db_driver='mysql.connector(.*)',dbapi_level='\d.\d',dbapi_threadsafety=\d,driver_paramstyle=(.*),mysql_client_version=\d*,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
