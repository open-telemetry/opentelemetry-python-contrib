# Copyright 2020, OpenTelemetry Authors
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

import psycopg2

from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.test.test_base import TestBase

POSTGRES_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))
POSTGRES_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "postgres")
POSTGRES_USER = os.getenv("POSTGRESQL_USER", "postgres")


class TestFunctionalPsycopg(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._connection = None
        cls._cursor = None
        cls._tracer = cls.tracer_provider.get_tracer(__name__)
        Psycopg2Instrumentor().instrument(enable_commenter=True)
        cls._connection = psycopg2.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
        )
        cls._connection.set_session(autocommit=True)
        cls._cursor = cls._connection.cursor()

    @classmethod
    def tearDownClass(cls):
        if cls._cursor:
            cls._cursor.close()
        if cls._connection:
            cls._connection.close()
        Psycopg2Instrumentor().uninstrument()

    def test_commenter_enabled(self):
        self._cursor.execute(
            "SELECT  1;"
        )
        self.assertRegex(
            self._cursor.query.decode('ascii'),
            r"SELECT  1; /\*traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/",
        )
