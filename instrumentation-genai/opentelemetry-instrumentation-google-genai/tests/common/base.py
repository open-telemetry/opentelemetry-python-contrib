import google.genai
import unittest

from .otel_mocker import OTelMocker
from .requests_mocker import RequestsMocker
from .instrumentation_context import InstrumentationContext


class TestCase(unittest.TestCase):

    def setUp(self):
        self._otel = OTelMocker()
        self._otel.install()
        self._requests = RequestsMocker()
        self._requests.install()
        self._instrumentation_context = InstrumentationContext()
        self._instrumentation_context.install()
        self._client = google.genai.Client(api_key='test-api-key')

    @property
    def client(self):
        return self._client

    @property
    def requests(self):
        return self._requests

    @property
    def otel(self):
        return self._otel

    def tearDown(self):
        self._instrumentation_context.uninstall()
        self._requests.uninstall()
        self._otel.uninstall()
