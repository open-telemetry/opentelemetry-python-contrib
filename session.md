# PR 4500 Session Notes

## GenAI stream wrapper updates

- Converted `SyncStreamWrapper` and `AsyncStreamWrapper` in `opentelemetry.util.genai.stream` to use `wrapt.ObjectProxy`.
- Removed explicit `__getattr__` passthrough from the stream wrappers; `ObjectProxy` now handles normal attribute passthrough and magic-method passthrough.
- Added `_SyncStream` and `_AsyncStream` protocols to type the wrapped streams as iterable/async-iterable objects with `close()`.
- Kept wrapper-owned state on `_self_*` attributes, following `wrapt.ObjectProxy` conventions.
- Added a direct `wrapt >= 1.0.0, < 3.0.0` dependency to `opentelemetry-util-genai`.
- Renamed stream lifecycle hooks from `_stop_stream` / `_fail_stream` to `_on_stream_end` /
  `_on_stream_error` so subclass methods read as lifecycle callbacks rather than ownership of the
  underlying stream mechanics.

## OpenAI chat wrapper alignment

- Updated OpenAI v2 chat stream wrappers to store telemetry state on `_self_*` attributes so state is not forwarded to the wrapped OpenAI stream.
- Updated tests that monkeypatch stream close behavior to patch `response.__wrapped__`.
- Added stream wrapper tests for magic-method passthrough with `len(wrapper)`.

## PyPy `wrapt.ObjectProxy` metaclass conflict

GitHub failed on `pypy3-test-instrumentation-openai-v2-latest` while importing the OpenAI v2 test
conftest:

```text
TypeError: metaclass conflict: the metaclass of a derived class must be a
(non-strict) subclass of the metaclasses of all its bases
```

The failing class shape was:

```python
class SyncStreamWrapper(_ObjectProxy, ABC, Generic[ChunkT]):
    ...
```

`ABC` uses `ABCMeta` to enforce abstract methods. `wrapt.ObjectProxy` also has proxy-specific class
creation behavior, and on PyPy its metaclass is not automatically compatible with `ABCMeta`. Python
must choose one metaclass that can satisfy all base classes; PyPy could not derive one for
`ObjectProxy + ABC + Generic`, so import failed before pytest could run.

Java analogy: this is similar to extending framework base classes that require incompatible class
generation/proxy machinery. The class fails during class loading/proxy construction, not during
normal method execution.

The fix was to remove `ABC` as a direct base and define an explicit combined metaclass:

```python
class _StreamWrapperMeta(ABCMeta, type(_ObjectProxy)):
    """Metaclass compatible with wrapt's proxy type and ABC hooks."""
```

Then the wrappers use:

```python
class SyncStreamWrapper(
    _ObjectProxy,
    Generic[ChunkT],
    metaclass=_StreamWrapperMeta,
):
    ...
```

This keeps `@abstractmethod` behavior through `ABCMeta` and keeps `wrapt.ObjectProxy` behavior
through `type(_ObjectProxy)`, without asking Python/PyPy to infer a compatible metaclass.

The stream wrapper tests use:

```python
# pylint: disable=abstract-class-instantiated
```

Reason: pylint cannot infer that the test wrapper subclasses are concrete when the base class uses
the custom combined `ABCMeta + wrapt.ObjectProxy` metaclass. Runtime behavior is correct:
`__abstractmethods__` is empty for the test subclasses, and they instantiate normally. The disable is
therefore scoped to a pylint false positive in the stream tests.

## Verification run

- `pytest util/opentelemetry-util-genai/tests/test_stream.py -q`: `33 passed`.
- `pyright util/opentelemetry-util-genai/src/opentelemetry/util/genai/stream.py`: `0 errors`.
- Direct import with `PYTHONPATH=util/opentelemetry-util-genai/src`: passed.
- `tox -e lint-instrumentation-openai-v2`: passed.

Known existing warning: the OpenAI streaming slice still reports the legacy async close warning from `patch.py:614`.
