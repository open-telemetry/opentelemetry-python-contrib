import asyncio
import os

import aiopg

from opentelemetry.instrumentation.aiopg import AiopgInstrumentor
from opentelemetry.test.test_base import TestBase

POSTGRES_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))
POSTGRES_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "opentelemetry-tests")
POSTGRES_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "testpassword")
POSTGRES_USER = os.getenv("POSTGRESQL_USER", "testuser")


def async_call(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class TestFunctionalAsyncPG(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._connection = None
        cls._cursor = None
        cls._tracer = cls.tracer_provider.get_tracer(__name__)
        AiopgInstrumentor().instrument(tracer_provider=cls.tracer_provider)
        cls._dsn = (
            f"dbname='{POSTGRES_DB_NAME}' user='{POSTGRES_USER}' password='{POSTGRES_PASSWORD}'"
            f" host='{POSTGRES_HOST}' port='{POSTGRES_PORT}'"
        )

    @classmethod
    def tearDownClass(cls):
        AiopgInstrumentor().uninstrument()

    def test_instrumented_pool_with_multiple_acquires(self, *_, **__):
        async def double_asquire():
            pool = await aiopg.create_pool(dsn=self._dsn)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = "SELECT 1"
                    await cursor.execute(query)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    query = "SELECT 1"
                    await cursor.execute(query)

        async_call(double_asquire())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
