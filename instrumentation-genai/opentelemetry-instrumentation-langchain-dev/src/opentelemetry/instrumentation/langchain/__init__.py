"""OpenTelemetry Langchain instrumentation"""

import logging
from typing import Any, Collection

from opentelemetry import context as context_api


from opentelemetry._events import get_event_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.langchain.callback_handler import (
    TraceloopCallbackHandler,
)
from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.utils import is_package_available
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from .semconv_ai import Meters, SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY
from opentelemetry.trace import get_tracer
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    EmbeddingInvocation as UtilEmbeddingInvocation,
    Error as UtilError,
)
from wrapt import wrap_function_wrapper

logger = logging.getLogger(__name__)

_instruments = ("langchain-core > 0.1.0", )

# Embedding patches configuration
EMBEDDING_PATCHES = [
    {
        "module": "langchain_openai.embeddings",
        "class_name": "OpenAIEmbeddings",
        "methods": ["embed_query", "embed_documents"],
    },
    {
        "module": "langchain_openai.embeddings",
        "class_name": "AzureOpenAIEmbeddings",
        "methods": ["embed_query", "embed_documents"],
    },
    {
        "module": "langchain_huggingface.embeddings",
        "class_name": "HuggingFaceEmbeddings",
        "methods": ["embed_query"],
    },
]


class LangchainInstrumentor(BaseInstrumentor):
    """An instrumentor for Langchain SDK."""

    def __init__(
        self,
        exception_logger=None,
        disable_trace_context_propagation=False,
        use_legacy_attributes: bool = True,
    ):
        super().__init__()
        Config.exception_logger = exception_logger
        Config.use_legacy_attributes = use_legacy_attributes
        self.disable_trace_context_propagation = disable_trace_context_propagation

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)

        # Add meter creation
        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(__name__, __version__, meter_provider)

        # Create duration histogram
        duration_histogram = meter.create_histogram(
            name=Meters.LLM_OPERATION_DURATION,
            unit="s",
            description="GenAI operation duration",
        )

        # Create token histogram
        token_histogram = meter.create_histogram(
            name=Meters.LLM_TOKEN_USAGE,
            unit="token",
            description="Measures number of input and output tokens used",
        )

        if not Config.use_legacy_attributes:
            event_logger_provider = kwargs.get("event_logger_provider")
            Config.event_logger = get_event_logger(
                __name__, __version__, event_logger_provider=event_logger_provider
            )

        telemetry_handler_kwargs: dict[str, Any] = {}
        if tracer_provider is not None:
            telemetry_handler_kwargs["tracer_provider"] = tracer_provider
        if meter_provider is not None:
            telemetry_handler_kwargs["meter_provider"] = meter_provider

        traceloopCallbackHandler = TraceloopCallbackHandler(
            tracer,
            duration_histogram,
            token_histogram,
            telemetry_handler_kwargs=telemetry_handler_kwargs or None,
        )
        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(traceloopCallbackHandler),
        )

        if not self.disable_trace_context_propagation:
            self._wrap_openai_functions_for_tracing(traceloopCallbackHandler)

        # Initialize telemetry handler for embeddings
        self._telemetry_handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        self._wrap_embedding_functions()

    def _wrap_openai_functions_for_tracing(self, traceloopCallbackHandler):
        openai_tracing_wrapper = _OpenAITracingWrapper(traceloopCallbackHandler)

        if is_package_available("langchain_community"):
            # Wrap langchain_community.llms.openai.BaseOpenAI
            wrap_function_wrapper(
                module="langchain_community.llms.openai",
                name="BaseOpenAI._generate",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_community.llms.openai",
                name="BaseOpenAI._agenerate",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_community.llms.openai",
                name="BaseOpenAI._stream",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_community.llms.openai",
                name="BaseOpenAI._astream",
                wrapper=openai_tracing_wrapper,
            )

        if is_package_available("langchain_openai"):
            # Wrap langchain_openai.llms.base.BaseOpenAI
            wrap_function_wrapper(
                module="langchain_openai.llms.base",
                name="BaseOpenAI._generate",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_openai.llms.base",
                name="BaseOpenAI._agenerate",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_openai.llms.base",
                name="BaseOpenAI._stream",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_openai.llms.base",
                name="BaseOpenAI._astream",
                wrapper=openai_tracing_wrapper,
            )

            # langchain_openai.chat_models.base.BaseOpenAI
            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._generate",
                wrapper=openai_tracing_wrapper,
            )

            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._agenerate",
                wrapper=openai_tracing_wrapper,
            )

            # Doesn't work :(
            # wrap_function_wrapper(
            #     module="langchain_openai.chat_models.base",
            #     name="BaseChatOpenAI._stream",
            #     wrapper=openai_tracing_wrapper,
            # )
            # wrap_function_wrapper(
            #     module="langchain_openai.chat_models.base",
            #     name="BaseChatOpenAI._astream",
            #     wrapper=openai_tracing_wrapper,
            # )

    def _wrap_embedding_functions(self):
        """Wrap embedding methods for telemetry capture."""

        def _start_embedding(instance, texts):
            """Start an embedding invocation."""
            # Detect model name
            request_model = (
                getattr(instance, "model", None)
                or getattr(instance, "model_name", None)
                or getattr(instance, "_model", None)
                or "unknown-model"
            )

            # Detect provider from class name
            provider = None
            class_name = instance.__class__.__name__
            if "OpenAI" in class_name:
                provider = "openai"
            elif "Azure" in class_name:
                provider = "azure"
            elif "Bedrock" in class_name:
                provider = "aws"
            elif "Vertex" in class_name or "Google" in class_name:
                provider = "google"
            elif "Cohere" in class_name:
                provider = "cohere"
            elif "HuggingFace" in class_name:
                provider = "huggingface"
            elif "Ollama" in class_name:
                provider = "ollama"

            # Create embedding invocation
            embedding = UtilEmbeddingInvocation(
                operation_name="embedding",
                request_model=request_model,
                input_texts=texts if isinstance(texts, list) else [texts],
                provider=provider,
                attributes={"framework": "langchain"},
            )

            self._telemetry_handler.start_embedding(embedding)
            return embedding

        def _finish_embedding(embedding, result):
            """Finish an embedding invocation."""
            # Try to extract dimension count from result
            try:
                if isinstance(result, list) and result:
                    # result is list of embeddings (vectors)
                    if isinstance(result[0], list):
                        embedding.dimension_count = len(result[0])
                    elif isinstance(result[0], (int, float)):
                        # Single embedding vector
                        embedding.dimension_count = len(result)
            except Exception:
                pass

            self._telemetry_handler.stop_embedding(embedding)

        def _embed_documents_wrapper(wrapped, instance, args, kwargs):
            """Wrapper for embed_documents method."""
            texts = args[0] if args else kwargs.get("texts", [])
            embedding = _start_embedding(instance, texts)
            try:
                result = wrapped(*args, **kwargs)
                _finish_embedding(embedding, result)
                return result
            except Exception as e:
                self._telemetry_handler.fail_embedding(
                    embedding, UtilError(message=str(e), type=type(e))
                )
                raise

        def _embed_query_wrapper(wrapped, instance, args, kwargs):
            """Wrapper for embed_query method."""
            text = args[0] if args else kwargs.get("text", "")
            embedding = _start_embedding(instance, [text])
            try:
                result = wrapped(*args, **kwargs)
                _finish_embedding(
                    embedding,
                    [result] if not isinstance(result, list) else result,
                )
                return result
            except Exception as e:
                self._telemetry_handler.fail_embedding(
                    embedding, UtilError(message=str(e), type=type(e))
                )
                raise

        # Apply wrappers for each embedding patch
        for patch in EMBEDDING_PATCHES:
            module = patch["module"]
            class_name = patch["class_name"]
            methods = patch["methods"]

            for method in methods:
                try:
                    if method == "embed_documents":
                        wrapper = _embed_documents_wrapper
                    elif method == "embed_query":
                        wrapper = _embed_query_wrapper
                    else:
                        continue

                    wrap_function_wrapper(
                        module=module,
                        name=f"{class_name}.{method}",
                        wrapper=wrapper,
                    )
                except Exception:  # pragma: no cover
                    pass

    def _uninstrument(self, **kwargs):
        unwrap("langchain_core.callbacks", "BaseCallbackManager.__init__")
        if not self.disable_trace_context_propagation:
            if is_package_available("langchain_community"):
                unwrap("langchain_community.llms.openai", "BaseOpenAI._generate")
                unwrap("langchain_community.llms.openai", "BaseOpenAI._agenerate")
                unwrap("langchain_community.llms.openai", "BaseOpenAI._stream")
                unwrap("langchain_community.llms.openai", "BaseOpenAI._astream")
            if is_package_available("langchain_openai"):
                unwrap("langchain_openai.llms.base", "BaseOpenAI._generate")
                unwrap("langchain_openai.llms.base", "BaseOpenAI._agenerate")
                unwrap("langchain_openai.llms.base", "BaseOpenAI._stream")
                unwrap("langchain_openai.llms.base", "BaseOpenAI._astream")
                unwrap("langchain_openai.chat_models.base", "BaseOpenAI._generate")
                unwrap("langchain_openai.chat_models.base", "BaseOpenAI._agenerate")
                # unwrap("langchain_openai.chat_models.base", "BaseOpenAI._stream")
                # unwrap("langchain_openai.chat_models.base", "BaseOpenAI._astream")

        # Unwrap embedding methods
        for patch in EMBEDDING_PATCHES:
            module = patch["module"]
            class_name = patch["class_name"]
            methods = patch["methods"]

            for method in methods:
                try:
                    unwrap(module, f"{class_name}.{method}")
                except Exception:  # pragma: no cover
                    pass


# Backwards-compatible alias for older import casing
LangChainInstrumentor = LangchainInstrumentor


class _BaseCallbackManagerInitWrapper:
    def __init__(self, callback_handler: "TraceloopCallbackHandler"):
        self._callback_handler = callback_handler

    def __call__(
        self,
        wrapped,
        instance,
        args,
        kwargs,
    ) -> None:
        wrapped(*args, **kwargs)
        for handler in instance.inheritable_handlers:
            if isinstance(handler, type(self._callback_handler)):
                break
        else:
            # Add a property to the handler which indicates the CallbackManager instance.
            # Since the CallbackHandler only propagates context for sync callbacks,
            # we need a way to determine the type of CallbackManager being wrapped.
            self._callback_handler._callback_manager = instance
            instance.add_handler(self._callback_handler, True)


# This class wraps a function call to inject tracing information (trace headers) into
# OpenAI client requests. It assumes the following:
# 1. The wrapped function includes a `run_manager` keyword argument that contains a `run_id`.
#    The `run_id` is used to look up a corresponding tracing span from the callback manager.
# 2. The `kwargs` passed to the wrapped function are forwarded to the OpenAI client. This
#    allows us to add extra headers (including tracing headers) to the OpenAI request by
#    modifying the `extra_headers` argument in `kwargs`.
class _OpenAITracingWrapper:
    def __init__(self, callback_manager: "TraceloopCallbackHandler"):
        self._callback_manager = callback_manager

    def __call__(
        self,
        wrapped,
        instance,
        args,
        kwargs,
    ) -> None:
        run_manager = kwargs.get("run_manager")

        ### FIXME: this was disabled to allow migration to util-genai and needs to be fixed
        # if run_manager:
        #     run_id = run_manager.run_id
        #     span_holder = self._callback_manager.spans[run_id]
        #
        #     extra_headers = kwargs.get("extra_headers", {})
        #
        #     # Inject tracing context into the extra headers
        #     ctx = set_span_in_context(span_holder.span)
        #     TraceContextTextMapPropagator().inject(extra_headers, context=ctx)
        #
        #     # Update kwargs to include the modified headers
        #     kwargs["extra_headers"] = extra_headers

        # In legacy chains like LLMChain, suppressing model instrumentations
        # within create_llm_span doesn't work, so this should helps as a fallback
        try:
            context_api.attach(
                context_api.set_value(SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY, True)
            )
        except Exception:
            # If context setting fails, continue without suppression
            # This is not critical for core functionality
            pass

        return wrapped(*args, **kwargs)
