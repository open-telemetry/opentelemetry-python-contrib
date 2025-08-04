from typing import Collection
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from wrapt import wrap_function_wrapper

from opentelemetry.trace import get_tracer
from opentelemetry.instrumentation.utils import unwrap

# from opentelemetry.instrumentation.langchain_v2.version import __version__
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.langchain_v2.callback_handler import OpenTelemetryCallbackHandler
from opentelemetry.instrumentation.langchain_v2.async_callback_handler import OpenTelemetryAsyncCallbackHandler


__all__ = ["OpenTelemetryCallbackHandler"]

_instruments = ("langchain >= 0.1.0",)

class LangChainInstrumentor(BaseInstrumentor):
    
    def instrumentation_dependencies(cls) -> Collection[str]:
        return _instruments
    
    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)

        otelCallbackHandler = OpenTelemetryCallbackHandler(tracer)
        
        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otelCallbackHandler),
        )
    
    def _uninstrument(self, **kwargs):
        unwrap("langchain_core.callbacks", "BaseCallbackManager.__init__")
        if hasattr(self, "_wrapped"):
            for module, name in self._wrapped:
                unwrap(module, name)
        self.handler = None
    
class _BaseCallbackManagerInitWrapper:
    def __init__(self, callback_handler: "OpenTelemetryCallbackHandler"):
        self.callback_handler = callback_handler
        self._wrapped = []
        
    def __call__(
        self,
        wrapped,
        instance,
        args,
        kwargs,
    ) -> None:
        wrapped(*args, **kwargs)
        for handler in instance.inheritable_handlers:
            if isinstance(handler, OpenTelemetryCallbackHandler):
                return None
        else:
            instance.add_handler(self.callback_handler, True)