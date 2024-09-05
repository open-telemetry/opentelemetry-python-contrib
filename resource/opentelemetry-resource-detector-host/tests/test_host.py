from unittest.mock import mock_open, patch

from opentelemetry import trace as trace_api
from opentelemetry.resource.detector.host import HostResourceDetector
from opentelemetry.sdk.resources import get_aggregated_resources
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.test.test_base import TestBase
class HostResourceDetectorTest(TestBase):
    def test_host_resource_detector(self):
        detector = HostResourceDetector()
        actual = detector.detect()
        self.assertTrue(actual.attributes.get(ResourceAttributes.HOST_NAME))
        self.assertTrue(actual.attributes.get(ResourceAttributes.HOST_ARCH))

    def test_host_resource_as_span_attribute(self):
        tracer_provider, exporter = self.create_tracer_provider(
            resource=get_aggregated_resources([HostResourceDetector()])
        )
        tracer = tracer_provider.get_tracer(__name__)

        with tracer.start_as_current_span(
                "test", kind=trace_api.SpanKind.SERVER
        ) as _:
            pass

        span_list = exporter.get_finished_spans()
        self.assertTrue(span_list[0].resource.attributes.get(ResourceAttributes.HOST_NAME))
        self.assertTrue(span_list[0].resource.attributes.get(ResourceAttributes.HOST_ARCH))

