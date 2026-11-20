# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Global async-engine instrumentation is once-only, in either import order.

``sqlalchemy.ext.asyncio.engine`` binds ``create_engine`` when it is first
imported. If that first import happens after ``create_engine`` is wrapped,
``create_async_engine`` registers two ``EngineTracer``s. See #5338.
"""

import subprocess
import sys

CONNECTION_COUNT = "db.client.connection.count"
CONNECTION_STATE = "db.client.connection.state"
USED = "used"


def _used_connections(reader):
    data = reader.get_metrics_data()
    if data is None:
        return 0
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name != CONNECTION_COUNT:
                    continue
                for point in metric.data.data_points:
                    if point.attributes.get(CONNECTION_STATE) == USED:
                        return point.value
    return 0


def _run_case(import_async_first):
    # Imports stay inside this process entry point so each case can choose
    # whether sqlalchemy.ext.asyncio is loaded before instrument().
    if import_async_first:
        import sqlalchemy.ext.asyncio  # noqa: F401,PLC0415  # pylint: disable=unused-import,import-outside-toplevel

    from opentelemetry.instrumentation.sqlalchemy import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        SQLAlchemyInstrumentor,
    )
    from opentelemetry.instrumentation.sqlalchemy.engine import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        EngineTracer,
    )
    from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
    from opentelemetry.sdk.metrics.export import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        InMemoryMetricReader,
    )

    tracer_calls = []
    original_init = EngineTracer.__init__

    def _counting_init(self, *args, **kwargs):
        tracer_calls.append(1)
        return original_init(self, *args, **kwargs)

    EngineTracer.__init__ = _counting_init

    reader = InMemoryMetricReader()
    SQLAlchemyInstrumentor().instrument(meter_provider=MeterProvider(metric_readers=[reader]))

    import asyncio  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    import sqlalchemy.ext.asyncio as sqlalchemy_asyncio  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
    import sqlalchemy.ext.asyncio.engine as sqlalchemy_asyncio_engine  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    async def _exercise():
        engine = sqlalchemy_asyncio.create_async_engine("sqlite+aiosqlite:///:memory:")
        if len(tracer_calls) != 1:
            raise AssertionError(f"expected 1 EngineTracer, got {len(tracer_calls)}")
        async with engine.connect():
            used = _used_connections(reader)
            if used != 1:
                raise AssertionError(f"expected db.client.connection.count used=1, got {used}")

        tracer_calls.clear()
        engine_mod = sqlalchemy_asyncio_engine.create_async_engine("sqlite+aiosqlite:///:memory:")
        if len(tracer_calls) != 1:
            raise AssertionError(f"expected 1 EngineTracer from engine.create_async_engine, got {len(tracer_calls)}")

        engine_cfg = None
        if hasattr(sqlalchemy_asyncio, "async_engine_from_config"):
            tracer_calls.clear()
            engine_cfg = sqlalchemy_asyncio.async_engine_from_config({"sqlalchemy.url": "sqlite+aiosqlite:///:memory:"})
            if len(tracer_calls) != 1:
                raise AssertionError(f"expected 1 EngineTracer from async_engine_from_config, got {len(tracer_calls)}")

        # Keep the engines alive: removing a duplicated module-level listener
        # raises InvalidRequestError only while the target still exists.
        SQLAlchemyInstrumentor().uninstrument()
        tracer_calls.clear()
        engine_after = sqlalchemy_asyncio.create_async_engine("sqlite+aiosqlite:///:memory:")
        engine_mod_after = sqlalchemy_asyncio_engine.create_async_engine("sqlite+aiosqlite:///:memory:")
        if len(tracer_calls) != 0:
            raise AssertionError(f"expected no EngineTracer after uninstrument, got {len(tracer_calls)}")
        async with engine_after.connect():
            used_after = _used_connections(reader)
            if used_after != 0:
                raise AssertionError(f"expected used=0 after uninstrument, got {used_after}")
        await engine.dispose()
        await engine_mod.dispose()
        if engine_cfg is not None:
            await engine_cfg.dispose()
        await engine_after.dispose()
        await engine_mod_after.dispose()

    asyncio.run(_exercise())


def _run_missing_greenlet_case():
    sys.modules["greenlet"] = None

    import sqlalchemy  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    from opentelemetry.instrumentation.sqlalchemy import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        SQLAlchemyInstrumentor,
    )
    from opentelemetry.instrumentation.sqlalchemy.engine import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        EngineTracer,
    )

    tracer_calls = []
    original_init = EngineTracer.__init__

    def _counting_init(self, *args, **kwargs):
        tracer_calls.append(1)
        return original_init(self, *args, **kwargs)

    EngineTracer.__init__ = _counting_init

    SQLAlchemyInstrumentor().instrument()
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    if len(tracer_calls) != 1:
        raise AssertionError(f"expected 1 sync EngineTracer without greenlet, got {len(tracer_calls)}")

    SQLAlchemyInstrumentor().uninstrument()
    tracer_calls.clear()
    engine_after = sqlalchemy.create_engine("sqlite:///:memory:")
    if len(tracer_calls) != 0:
        raise AssertionError(f"expected 0 sync EngineTracers after uninstrument, got {len(tracer_calls)}")
    engine.dispose()
    engine_after.dispose()


def _spawn(mode):
    completed = subprocess.run(
        [sys.executable, __file__, mode],
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    assert completed.returncode == 0, output


def test_async_engine_instrumented_once_when_imported_after_instrument():
    _spawn("fresh")


def test_async_engine_instrumented_once_when_imported_before_instrument():
    _spawn("already")


def test_sync_engine_instrumented_when_greenlet_missing():
    _spawn("no-greenlet")


if __name__ == "__main__":
    if sys.argv[1] == "no-greenlet":
        _run_missing_greenlet_case()
    else:
        _run_case(import_async_first=sys.argv[1] == "already")
