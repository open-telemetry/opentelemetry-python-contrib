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
    def test_commenter_enabled_direct_reference(self):
        MySQLInstrumentor().instrument(enable_commenter=True)
        cnx = mysql.connector.connect(
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DB_NAME,
        )
        cursor = cnx.cursor()

        cursor.execute("SELECT 1;")
        cursor.fetchall()
        self.assertRegex(
            cursor.statement,
            r"SELECT 1 /\*db_driver='mysql\.connector[^']*',dbapi_level='\d\.\d',dbapi_threadsafety=\d,driver_paramstyle='[^']*',mysql_client_version='[^']*',traceparent='[^']*'\*/;",
        )
        self.assertRegex(
            cursor.statement, r"mysql_client_version='(?!unknown)[^']+"
        )

        cursor.close()
        cnx.close()
        MySQLInstrumentor().uninstrument()

    def test_commenter_enabled_connection_proxy(self):
        cnx = mysql.connector.connect(
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DB_NAME,
        )
        instrumented_cnx = MySQLInstrumentor().instrument_connection(
            connection=cnx,
            enable_commenter=True,
        )
        cursor = instrumented_cnx.cursor()

        cursor.execute("SELECT 1;")
        cursor.fetchall()
        self.assertRegex(
            cursor.statement,
            r"SELECT 1 /\*db_driver='mysql\.connector[^']*',dbapi_level='\d\.\d',dbapi_threadsafety=\d,driver_paramstyle='[^']*',mysql_client_version='[^']*',traceparent='[^']*'\*/;",
        )
        self.assertRegex(
            cursor.statement, r"mysql_client_version='(?!unknown)[^']+"
        )

        cursor.close()
        MySQLInstrumentor().uninstrument_connection(instrumented_cnx)
        cnx.close()

    def test_commenter_enabled_unknown_mysql_client_version(self):
        MySQLInstrumentor().instrument(enable_commenter=True)
        cnx = mysql.connector.connect(
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DB_NAME,
        )
        cursor = cnx.cursor()

        # Temporarily remove _cmysql
        original_cmysql = None
        try:
            if hasattr(cursor._cnx, "_cmysql"):
                original_cmysql = cursor._cnx._cmysql
                delattr(cursor._cnx, "_cmysql")
        except AttributeError:
            pass

        cursor.execute("SELECT 1;")
        cursor.fetchall()

        self.assertRegex(
            cursor.statement,
            r"SELECT 1 /\*db_driver='mysql\.connector[^']*',dbapi_level='\d\.\d',dbapi_threadsafety=\d,driver_paramstyle='[^']*',mysql_client_version='unknown',traceparent='[^']*'\*/;",
        )
        self.assertIn("mysql_client_version='unknown'", cursor.statement)

        # Restore _cmysql
        if original_cmysql is not None:
            try:
                cursor._cnx._cmysql = original_cmysql
            except AttributeError:
                pass

        cursor.close()
        cnx.close()
        MySQLInstrumentor().uninstrument()
