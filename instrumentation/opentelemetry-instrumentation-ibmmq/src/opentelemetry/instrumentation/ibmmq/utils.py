# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
from collections.abc import Callable
from logging import getLogger
from typing import Any

from opentelemetry import context, trace
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)

# ibm.mq.queue_manager.id is not a ratified semantic convention yet.
# Gate it behind this env var, default off, same as the Java/.NET agents do
# for the identical attribute.
_EXPERIMENTAL_ENV_VAR = "OTEL_PYTHON_IBMMQ_EXPERIMENTAL_SPAN_ATTRIBUTES"
_ATTR_QMID = "ibm.mq.queue_manager.id"
_ATTR_BROWSE = "ibm.mq.browse"

# Read once at instrument() time, never per span.
_experimental_attributes_enabled = False

# Note on trace propagation: this module intentionally does none. IBM's own
# ibmmq/mqotel.py already injects/extracts trace context on the producer,
# sync consumer and async callback paths, on by default. Do not add
# propagation here, it would double up with what the client already does.

CallableWrapper = Callable[[Any, Any, tuple, dict], Any]


def configure_experimental_attributes() -> None:
    """Read the QMID experimental-attribute flag into module state.

    Called once from Instrumentor._instrument(), not from inside a span
    creation path.
    """
    global _experimental_attributes_enabled  # pylint: disable=global-statement
    raw = os.environ.get(_EXPERIMENTAL_ENV_VAR, "")
    _experimental_attributes_enabled = raw.strip().lower() in ("true", "1")


def _clean_name(name: Any) -> str | None:
    """Trim a raw MQ character field.

    Queue names read back after MQOPEN are NUL padded, not space padded,
    so a bare .strip() is not enough. Handles bytes or str, either padding
    style.
    """
    if name is None:
        return None
    if isinstance(name, bytes):
        name = name.decode(errors="replace")
    name = name.rstrip("\x00 ")
    return name or None


def _resolve_qmid(qmgr: Any, attribute: int) -> str | None:
    """Resolve the queue manager id via MQINQ.

    This is a network round trip (about 335 microseconds), so this must only
    ever be called once per connect, right after connect()/connect_with_options()
    returns (connect_tcp_client is not wrapped separately; both real clients
    have it delegate to connect_with_options). Never call this per message.
    """
    try:
        raw = qmgr.inquire(attribute)
        if isinstance(raw, bytes):
            raw = raw.decode(errors="replace")
        return raw.strip() or None
    except Exception as exc:  # pylint: disable=broad-except
        # A failed QMID inquire must never break the application's MQ call.
        _LOG.debug("failed to resolve IBM MQ queue manager id: %s", exc)
        return None


def _queue_manager(queue: Any) -> Any:
    """Return the QueueManager instance a Queue belongs to.

    ibmmq exposes this publicly, pymqi only has the name mangled private
    attribute.
    """
    get_qmgr = getattr(queue, "get_queue_manager", None)
    if get_qmgr is not None:
        try:
            return get_qmgr()
        # Load bearing: the real ibmmq accessor can raise on a queue that
        # was never opened, and that must never break the caller's MQ call.
        except Exception:  # pylint: disable=broad-except
            return None
    return getattr(queue, "_Queue__qMgr", None)


def _queue_name(queue: Any) -> str | None:
    """Return the queue's name, or None if it cannot be determined.

    Tries the public ibmmq accessor first, then falls back to pymqi's name
    mangled MQOD. _Queue__qDesc is None until the queue is actually opened.
    """
    get_name = getattr(queue, "get_name", None)
    if get_name is not None:
        try:
            name = get_name()
        # Load bearing: real ibmmq's Queue.get_name() does
        # self.__q_desc.ObjectName, which raises AttributeError when the
        # queue has never been opened. Must not break the caller's MQ call.
        except Exception:  # pylint: disable=broad-except
            name = None
        if name:
            return _clean_name(name)
    q_desc = getattr(queue, "_Queue__qDesc", None)
    if q_desc is None:
        return None
    return _clean_name(getattr(q_desc, "ObjectName", None))


def _put1_destination(args: tuple, kwargs: dict) -> str | None:
    """Resolve the destination queue name passed to QueueManager.put1.

    The first positional arg (or the q_desc/qDesc kwarg) is a str, bytes,
    or an OD object, depending on how the caller invoked put1.
    """
    q_desc = None
    if args:
        q_desc = args[0]
    elif "q_desc" in kwargs:
        q_desc = kwargs["q_desc"]
    elif "qDesc" in kwargs:
        q_desc = kwargs["qDesc"]
    if q_desc is None:
        return None
    if isinstance(q_desc, (str, bytes)):
        return _clean_name(q_desc)
    return _clean_name(getattr(q_desc, "ObjectName", None))


def _find_gmo(args: tuple, kwargs: dict) -> Any:
    """Find the MQGMO among the arguments to a Queue.get call.

    A browse is a GMO option bit on the same get() call, not a separate
    class, so duck type on the one attribute (Options) that identifies a
    GMO among the get() arguments (maxLength, m_desc, get_opts).
    """
    for candidate in (*args, *kwargs.values()):
        if hasattr(candidate, "Options"):
            return candidate
    return None


def _is_browse(gmo: Any, browse_mask: int) -> bool:
    if gmo is None:
        return False
    options = getattr(gmo, "Options", 0) or 0
    return bool(options & browse_mask)


def _span_name(destination: str | None, operation: str) -> str:
    if destination:
        return f"{destination} {operation}"
    return operation


def _name_after_open(span: Span, queue: Any, operation: str) -> None:
    """Re-read the queue's name after a put()/get() call that may have just
    opened it.

    Both clients open a queue lazily inside the first put() or get() if it
    was not already open, so the name is unreadable until that call
    returns. Only call this when the destination was still unknown before
    the call; otherwise the name was already known and this is a no-op.
    """
    destination = _queue_name(queue)
    if destination is not None:
        span.update_name(_span_name(destination, operation))
        span.set_attribute(messaging_attributes.MESSAGING_DESTINATION_NAME, destination)


def _enrich_span(
    span: Span,
    destination: str | None,
    operation: str,
    qmid: str | None,
    browse: bool = False,
) -> None:
    # MessagingSystemValues is a closed enum with no IBM MQ member, so a
    # literal string is intentional here.
    span.set_attribute(messaging_attributes.MESSAGING_SYSTEM, "ibm.mq")
    span.set_attribute(messaging_attributes.MESSAGING_OPERATION, operation)
    if destination is not None:
        span.set_attribute(messaging_attributes.MESSAGING_DESTINATION_NAME, destination)
    if _experimental_attributes_enabled:
        # Neither of these is a ratified convention yet, so both are off by
        # default and travel together behind the one flag.
        if qmid is not None:
            span.set_attribute(_ATTR_QMID, qmid)
        if browse:
            span.set_attribute(_ATTR_BROWSE, True)


def make_connect_wrapper(cmqc: Any) -> CallableWrapper:
    """Build the wrapper for connect and connect_with_options.

    connect_tcp_client is intentionally not wrapped by this factory: in both
    real clients it ends by calling self.connect_with_options(name, **kwargs),
    so wrapping both would perform the MQINQ resolve twice per TCP connect.

    Resolves QMID once, right after connect returns, and caches it on the
    QueueManager instance. Never cache this at module scope: one process can
    hold connections to several queue managers, and IBM refreshes the
    resolved identity after an automatic client reconnect, which can land on
    a different queue manager.
    """
    qmid_attribute = cmqc.MQCA_Q_MGR_IDENTIFIER

    def wrapper(wrapped: Callable, instance: Any, args: tuple, kwargs: dict) -> Any:
        result = wrapped(*args, **kwargs)
        if _experimental_attributes_enabled:
            # QMID is only ever read by the experimental attribute, so skip
            # the MQINQ network round trip entirely when it is off (default):
            # otherwise every connect pays for a value nobody consumes.
            instance._otel_qmid = _resolve_qmid(instance, qmid_attribute)
        return result

    return wrapper


def make_put1_wrapper(tracer: Tracer) -> CallableWrapper:
    def wrapper(wrapped: Callable, instance: Any, args: tuple, kwargs: dict) -> Any:
        if not is_instrumentation_enabled():
            return wrapped(*args, **kwargs)
        destination = _put1_destination(args, kwargs)
        qmid = getattr(instance, "_otel_qmid", None)
        span = tracer.start_span(
            name=_span_name(destination, "publish"),
            kind=SpanKind.PRODUCER,
        )
        if span.is_recording():
            _enrich_span(span, destination, "publish", qmid)
        with trace.use_span(span, end_on_exit=True):
            return wrapped(*args, **kwargs)

    return wrapper


def make_queue_put_wrapper(tracer: Tracer) -> CallableWrapper:
    def wrapper(wrapped: Callable, instance: Any, args: tuple, kwargs: dict) -> Any:
        if not is_instrumentation_enabled():
            return wrapped(*args, **kwargs)
        destination = _queue_name(instance)
        qmgr = _queue_manager(instance)
        qmid = getattr(qmgr, "_otel_qmid", None)
        span = tracer.start_span(
            name=_span_name(destination, "publish"),
            kind=SpanKind.PRODUCER,
        )
        if span.is_recording():
            _enrich_span(span, destination, "publish", qmid)
        with trace.use_span(span, end_on_exit=True):
            result = wrapped(*args, **kwargs)
            if destination is None:
                # The queue may have just been opened lazily inside this
                # call; the name is unreadable before that.
                _name_after_open(span, instance, "publish")
            return result

    return wrapper


def make_queue_get_wrapper(tracer: Tracer, cmqc: Any) -> CallableWrapper:
    no_msg_reason = cmqc.MQRC_NO_MSG_AVAILABLE
    # Computed once here, not rebuilt on every get().
    browse_mask = cmqc.MQGMO_BROWSE_FIRST | cmqc.MQGMO_BROWSE_NEXT | cmqc.MQGMO_BROWSE_MSG_UNDER_CURSOR

    def wrapper(wrapped: Callable, instance: Any, args: tuple, kwargs: dict) -> Any:
        if not is_instrumentation_enabled():
            return wrapped(*args, **kwargs)

        # Both real clients call get_opts.unpack(rv[2]) after MQGET, which
        # overwrites the caller's MQGMO object in place. The browse bits
        # MUST be read before the wrapped call, or they can reflect a
        # cleared/changed state and mislabel the operation.
        browse = _is_browse(_find_gmo(args, kwargs), browse_mask)
        destination = _queue_name(instance)
        destination_was_none = destination is None
        qmgr = _queue_manager(instance)
        qmid = getattr(qmgr, "_otel_qmid", None)

        span = tracer.start_span(
            name=_span_name(destination, "receive"),
            kind=SpanKind.CONSUMER,
        )
        if span.is_recording():
            # An app that only browsed has not proven it consumes from this
            # queue manager, so the browse case stays distinguishable rather
            # than being folded into a plain receive.
            _enrich_span(span, destination, "receive", qmid, browse=browse)

        # IBM's own ibmmq/mqotel.py calls trace.get_current_span() and
        # attaches a link to it for the incoming message, from inside the
        # wrapped get() call. The consumer span must be current for the
        # duration of that call, or the link lands on whatever span happens
        # to already be current instead of this one.
        token = context.attach(trace.set_span_in_context(span))
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:
            reason = getattr(exc, "reason", None)
            if reason == no_msg_reason:
                # A consumer using MQGMO_WAIT is raised this on every idle
                # poll and treats it as normal, so this case must produce no
                # span at all. Deliberately never call span.end() here: an
                # unended span is never handed to a span processor's on_end,
                # and so is never exported. This is what gives zero spans
                # for an idle poll while still having had the span current
                # for the duration of the call.
                raise
            if destination_was_none:
                _name_after_open(span, instance, "receive")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.end()
            raise
        finally:
            context.detach(token)

        if destination_was_none:
            # The queue may have just been opened lazily inside this call;
            # the name is unreadable before that.
            _name_after_open(span, instance, "receive")
        span.end()
        return result

    return wrapper


# Marker set on our own callback wrapper so a re-registered CBD (same
# CallbackFunction re-armed by the caller) is never wrapped twice.
_CB_WRAPPED_MARKER = "_otel_ibmmq_wrapped"

# Whether the substituted MQCB callback is allowed to do span work. Default
# off, matching the module's own default-uninstrumented state.
_instrumented = False


def set_instrumented(value: bool) -> None:
    """Arm or disarm every substituted MQCB callback at once.

    This has to be a module level flag, not a closure variable captured by
    make_cb_wrapper/traced_callback. ibmmq's own mqcallback.py stashes
    cbd.CallbackFunction into its own module level dict (_stashedCBD) at
    MQCB register time, so the callback this module substitutes stays armed
    inside the IBM client even after Instrumentor.uninstrument() unwraps
    Queue.cb/QueueManager.cb. There is no hook back into an already
    registered callback's closure at that point, so the substituted callback
    has to consult a flag it can still see after the fact instead.
    """
    global _instrumented  # pylint: disable=global-statement
    _instrumented = value


def make_cb_wrapper(tracer: Tracer, cmqc: Any) -> CallableWrapper:
    """Build the wrapper for Queue.cb and QueueManager.cb (ibmmq only).

    MQCB has no pymqi equivalent. ibmmq documents the user callback as taking
    the keyword arguments queue_manager, queue, md, gmo, msg and cbc, so both
    the control block and the queue are read by name at delivery time. That
    also covers QueueManager.cb, where the queue is not known until a message
    actually arrives.
    """
    register_op = cmqc.MQOP_REGISTER
    msg_removed = cmqc.MQCBCT_MSG_REMOVED
    msg_not_removed = cmqc.MQCBCT_MSG_NOT_REMOVED
    no_msg_reason = cmqc.MQRC_NO_MSG_AVAILABLE

    def wrapper(wrapped: Callable, instance: Any, args: tuple, kwargs: dict) -> Any:
        if not is_instrumentation_enabled():
            return wrapped(*args, **kwargs)

        operation = kwargs.get("operation")
        if operation is None and args:
            operation = args[0]
        cbd = kwargs.get("cbd")
        if cbd is None and len(args) > 1:
            cbd = args[1]
        if operation != register_op or cbd is None:
            return wrapped(*args, **kwargs)

        original_callback = cbd.CallbackFunction
        if getattr(original_callback, _CB_WRAPPED_MARKER, False):
            return wrapped(*args, **kwargs)

        def traced_callback(*cb_args: Any, **cb_kwargs: Any) -> Any:
            # The original callback must run exactly once on every path, so
            # track whether the fallback below still needs to invoke it.
            called = False

            def call_original() -> Any:
                nonlocal called
                called = True
                return original_callback(*cb_args, **cb_kwargs)

            # All span work lives inside this try/except: a failure here must
            # never stop the application's message from being delivered.
            try:
                if not _instrumented:
                    # The class methods were unwrapped by uninstrument(), but
                    # this callback stays armed inside the IBM client (see
                    # set_instrumented's docstring). Fall straight through.
                    return call_original()

                # MQCB also delivers START_CALL, STOP_CALL, REGISTER_CALL,
                # DEREGISTER_CALL and EVENT_CALL, plus MQRC_NO_MSG_AVAILABLE
                # when a wait expires. None of those is a message, so no span.
                cbc = cb_kwargs.get("cbc")
                call_type = getattr(cbc, "CallType", None)
                if call_type not in (msg_removed, msg_not_removed) or (getattr(cbc, "Reason", None) == no_msg_reason):
                    return call_original()

                queue = cb_kwargs.get("queue")
                destination = _queue_name(queue) if queue is not None else None
                qmgr = cb_kwargs.get("queue_manager")
                qmid = getattr(qmgr, "_otel_qmid", None)
                span = tracer.start_span(
                    name=_span_name(destination, "receive"),
                    kind=SpanKind.CONSUMER,
                )
                if span.is_recording():
                    _enrich_span(span, destination, "receive", qmid)
                with trace.use_span(span, end_on_exit=True):
                    return call_original()
            except Exception as exc:  # pylint: disable=broad-except
                if called:
                    # original_callback itself raised; it already ran
                    # exactly once, so propagate instead of calling it again.
                    raise
                _LOG.debug("ibmmq instrumentation failed for async callback delivery: %s", exc)
                return original_callback(*cb_args, **cb_kwargs)

        setattr(traced_callback, _CB_WRAPPED_MARKER, True)
        cbd.CallbackFunction = traced_callback
        return wrapped(*args, **kwargs)

    return wrapper
