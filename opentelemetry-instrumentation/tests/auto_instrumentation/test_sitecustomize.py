from os import environ
from unittest import TestCase
from unittest.mock import patch

class TestSiteCustomize(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.load_configurators = patch(
            "opentelemetry.instrumentation.auto_instrumentation._load._load_configurators"
        )
        cls.load_instrumentors = patch(
            "opentelemetry.instrumentation.auto_instrumentation._load._load_instrumentors"
        )

        cls.load_configurators.start()
        cls.load_instrumentors.start()

    @classmethod
    def tearDownClass(cls):
        cls.load_configurators.stop()
        cls.load_instrumentors.stop()

    def test_unset(self):
        if environ.get("PYTHONPATH"):
            del environ["PYTHONPATH"]  # enforce remove key/value from environ
        from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
        self.assertEqual(environ.get("PYTHONPATH"), None)

    @patch.dict("os.environ", {"PYTHONPATH": ""})
    def test_empty(self):
        from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
        self.assertEqual(environ["PYTHONPATH"], "")

    @patch.dict("os.environ", {"PYTHONPATH": "abc"})
    def test_set(self):
        from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
        self.assertEqual(environ["PYTHONPATH"], "abc")
