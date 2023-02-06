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

from typing import Optional, Sequence

import sqlalchemy
from sqlalchemy.pool import QueuePool

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics._internal.point import Metric
from opentelemetry.sdk.metrics.export import (
    DataPointT,
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.test.test_base import TestBase


class TestSqlalchemyMetricsInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
        )

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

    def get_sorted_metrics(self):
        resource_metrics = (
            self.memory_metrics_reader.get_metrics_data().resource_metrics
        )

        all_metrics = []
        for metrics in resource_metrics:
            for scope_metrics in metrics.scope_metrics:
                all_metrics.extend(scope_metrics.metrics)

        return self.sorted_metrics(all_metrics)

    @staticmethod
    def sorted_metrics(metrics):
        """
        Sorts metrics by metric name.
        """
        return sorted(
            metrics,
            key=lambda m: m.name,
        )

    def assert_metric_expected(
        self,
        metric: Metric,
        expected_data_points: Sequence[DataPointT],
        est_value_delta: Optional[float] = 0,
    ):
        self.assertEqual(
            len(expected_data_points), len(metric.data.data_points)
        )
        for expected_data_point in expected_data_points:
            self.assert_data_point_expected(
                expected_data_point, metric.data.data_points, est_value_delta
            )

    # pylint: disable=unidiomatic-typecheck
    @staticmethod
    def is_data_points_equal(
        expected_data_point: DataPointT,
        data_point: DataPointT,
        est_value_delta: Optional[float] = 0,
    ):
        if type(expected_data_point) != type(data_point) or not isinstance(
            expected_data_point, (HistogramDataPoint, NumberDataPoint)
        ):
            return False

        values_diff = None
        if isinstance(data_point, HistogramDataPoint):
            values_diff = abs(expected_data_point.sum - data_point.sum)
        elif isinstance(data_point, NumberDataPoint):
            values_diff = abs(expected_data_point.value - data_point.value)

        return (
            values_diff <= est_value_delta
            and expected_data_point.attributes == dict(data_point.attributes)
        )

    def assert_data_point_expected(
        self,
        expected_data_point: DataPointT,
        data_points: Sequence[DataPointT],
        est_value_delta: Optional[float] = 0,
    ):
        is_data_point_exist = False
        for data_point in data_points:
            if self.is_data_points_equal(
                expected_data_point, data_point, est_value_delta
            ):
                is_data_point_exist = True
                break

        self.assertTrue(
            is_data_point_exist,
            msg=f"Data point {expected_data_point} does not exist",
        )

    @staticmethod
    def create_number_data_point(value, attributes):
        return NumberDataPoint(
            value=value,
            attributes=attributes,
            start_time_unix_nano=0,
            time_unix_nano=0,
        )

    def assert_pool_idle_used_expected(self, pool_name, idle, used):
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 1)
        self.assert_metric_expected(
            metrics[0],
            [
                self.create_number_data_point(
                    value=idle,
                    attributes={"pool.name": pool_name, "state": "idle"},
                ),
                self.create_number_data_point(
                    value=used,
                    attributes={"pool.name": pool_name, "state": "used"},
                ),
            ],
        )

    def test_metrics_one_connection(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 0)

        with engine.connect():
            self.assert_pool_idle_used_expected(
                pool_name=pool_name, idle=0, used=1
            )

        # After the connection is closed
        self.assert_pool_idle_used_expected(
            pool_name=pool_name, idle=1, used=0
        )

    def test_metrics_without_pool_name(self):
        pool_name = ""
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
        )

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 0)

        with engine.connect():
            self.assert_pool_idle_used_expected(
                pool_name=pool_name, idle=0, used=1
            )

        # After the connection is closed
        self.assert_pool_idle_used_expected(
            pool_name=pool_name, idle=1, used=0
        )

    def test_metrics_two_connections(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 0)

        with engine.connect():
            with engine.connect():
                self.assert_pool_idle_used_expected(pool_name, idle=0, used=2)

            # After the first connection is closed
            self.assert_pool_idle_used_expected(pool_name, idle=1, used=1)

        # After the two connections are closed
        self.assert_pool_idle_used_expected(pool_name, idle=2, used=0)

    def test_metrics_connections(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 0)

        with engine.connect():
            with engine.connect():
                self.assert_pool_idle_used_expected(
                    pool_name=pool_name, idle=0, used=2
                )

            # After the first connection is closed
            self.assert_pool_idle_used_expected(
                pool_name=pool_name, idle=1, used=1
            )

            # Resume from idle to used
            with engine.connect():
                self.assert_pool_idle_used_expected(
                    pool_name=pool_name, idle=0, used=2
                )

        # After the two connections are closed
        self.assert_pool_idle_used_expected(
            pool_name=pool_name, idle=2, used=0
        )

    def test_metric_uninstrument(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
        )

        engine.connect()

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 0)
