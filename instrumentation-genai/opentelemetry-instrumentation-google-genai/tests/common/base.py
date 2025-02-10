import os
import google.genai
import unittest

from .otel_mocker import OTelMocker
from .requests_mocker import RequestsMocker
from .instrumentation_context import InstrumentationContext


class _FakeCredentials(google.auth.credentials.AnonymousCredentials):

    def refresh(self, request):
        pass



class TestCase(unittest.TestCase):

    def setUp(self):
        self._otel = OTelMocker()
        self._otel.install()
        self._requests = RequestsMocker()
        self._requests.install()
        self._instrumentation_context = InstrumentationContext()
        self._instrumentation_context.install()
        self._api_key = 'test-api-key'
        self._project = 'test-project'
        self._location = 'test-location'
        self._client = None
        self._uses_vertex = False
        self._credentials = _FakeCredentials()

    @property
    def client(self):
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @property
    def requests(self):
        return self._requests

    @property
    def otel(self):
        return self._otel

    def set_use_vertex(self, use_vertex):
        self._uses_vertex = use_vertex

    def _create_client(self):
        if self._uses_vertex:
            os.environ['GOOGLE_API_KEY'] = self._api_key
            return google.genai.Client(
                vertexai=True,
                project=self._project,
                location=self._location,
                credentials=self._credentials)
        return google.genai.Client(api_key=self._api_key)

    def tearDown(self):
        self._instrumentation_context.uninstall()
        self._requests.uninstall()
        self._otel.uninstall()
