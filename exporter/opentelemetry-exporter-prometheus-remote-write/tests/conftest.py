

import random
import pytest

import opentelemetry.test.metrictestutil as metric_util#import _generate_gauge, _generate_sum

from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    Histogram,
    HistogramDataPoint,
    Sum,
    Gauge,
    MetricExportResult,
    MetricsData,
    ResourceMetrics,
    ScopeMetrics,
    Metric,
)

from opentelemetry.exporter.prometheus_remote_write import (
    PrometheusRemoteWriteMetricsExporter,
)
@pytest.fixture
def prom_rw():
    return PrometheusRemoteWriteMetricsExporter("http://victoria:8428/api/v1/write")



@pytest.fixture
def generate_metrics_data(data):
    pass



@pytest.fixture
def metric_histogram():
    dp = HistogramDataPoint(
        attributes={"foo": "bar", "baz": 42},
        start_time_unix_nano=1641946016139533244,
        time_unix_nano=1641946016139533244,
        count=random.randint(1,10),
        sum=random.randint(42,420),
        bucket_counts=[1, 4],
        explicit_bounds=[10.0, 20.0],
        min=8,
        max=18,
    )
    data = Histogram(
        [dp],
        AggregationTemporality.CUMULATIVE,
    )
    return Metric(
        "test_histogram",
        "foo",
        "tu",
        data=data,
    )

@pytest.fixture
def metric(request):
    if request.param == "gauge":
        return metric_util._generate_gauge("test_gauge",random.randint(0,100))
    elif request.param == "sum":
        return metric_util._generate_sum("test_sum",random.randint(0,9_999_999_999))

