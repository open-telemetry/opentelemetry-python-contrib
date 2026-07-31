# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import psycopg
import psycopg2
from test_psycopg_functional import (
    POSTGRES_DB_NAME,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)

from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.test.test_base import TestBase


class TestFunctionalPsycopg2(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        Psycopg2Instrumentor().instrument(enable_commenter=True)
        self._connection = psycopg2.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
        )
        self._connection.set_session(autocommit=True)
        self._cursor = self._connection.cursor()

    def tearDown(self):
        self._cursor.close()
        self._connection.close()
        Psycopg2Instrumentor().uninstrument()
        super().tearDown()

    def test_commenter_enabled(self):
        self._cursor.execute("SELECT  1;")
        self.assertRegex(
            self._cursor.query.decode("ascii"),
            r"SELECT  1 /\*db_driver='psycopg2(.*)',dbapi_level='\d.\d',dbapi_threadsafety=\d,driver_paramstyle=(.*),libpq_version=\d*,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )


class TestFunctionalPsycopg(TestBase):
    def setUp(self):
        super().setUp()
        PsycopgInstrumentor().instrument(enable_commenter=True)

    def tearDown(self):
        PsycopgInstrumentor().uninstrument()
        super().tearDown()

    def test_commenter_enabled_root_module(self):
        connection = psycopg.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
        )
        cursor = connection.cursor()
        cursor.execute("SELECT  1;")
        self.assertRegex(
            cursor._query.query.decode("ascii"),
            r"SELECT  1 /\*db_driver='psycopg(.*)',dbapi_level='\d.\d',dbapi_threadsafety=\d,driver_paramstyle=(.*),libpq_version=\d*,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

        cursor.close()
        connection.close()

    def test_commenter_enabled_not_root_module(self):
        connection = psycopg.Connection.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
        )
        cursor = connection.cursor()
        cursor.execute("SELECT  1;")
        self.assertRegex(
            cursor._query.query.decode("ascii"),
            r"SELECT  1 /\*db_driver='Connection%%3Aunknown',dbapi_level='\d.\d',dbapi_threadsafety='unknown',driver_paramstyle='unknown',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

        cursor.close()
        connection.close()
