# 3p
import redis

from ddtrace.ext import redis as redisx
from ddtrace.pin import Pin
from ddtrace.utils.wrappers import unwrap
from ddtrace.vendor import wrapt
from opentelemetry import trace

from .util import _extract_conn_attributes, format_command_args
from .version import __version__


def patch():
    """Patch the instrumented methods

    This duplicated doesn't look nice. The nicer alternative is to use an ObjectProxy on top
    of Redis and StrictRedis. However, it means that any "import redis.Redis" won't be instrumented.
    """
    if getattr(redis, "_datadog_patch", False):
        return
    setattr(redis, "_datadog_patch", True)

    _w = wrapt.wrap_function_wrapper

    if redis.VERSION < (3, 0, 0):
        _w("redis", "StrictRedis.execute_command", traced_execute_command)
        _w("redis", "StrictRedis.pipeline", traced_pipeline)
        _w("redis", "Redis.pipeline", traced_pipeline)
        _w("redis.client", "BasePipeline.execute", traced_execute_pipeline)
        _w(
            "redis.client",
            "BasePipeline.immediate_execute_command",
            traced_execute_command,
        )
    else:
        _w("redis", "Redis.execute_command", traced_execute_command)
        _w("redis", "Redis.pipeline", traced_pipeline)
        _w("redis.client", "Pipeline.execute", traced_execute_pipeline)
        _w(
            "redis.client",
            "Pipeline.immediate_execute_command",
            traced_execute_command,
        )
    Pin(service=redisx.DEFAULT_SERVICE, app=redisx.APP).onto(redis.StrictRedis)


def unpatch():
    if getattr(redis, "_datadog_patch", False):
        setattr(redis, "_datadog_patch", False)

        if redis.VERSION < (3, 0, 0):
            unwrap(redis.StrictRedis, "execute_command")
            unwrap(redis.StrictRedis, "pipeline")
            unwrap(redis.Redis, "pipeline")
            unwrap(redis.client.BasePipeline, "execute")
            unwrap(redis.client.BasePipeline, "immediate_execute_command")
        else:
            unwrap(redis.Redis, "execute_command")
            unwrap(redis.Redis, "pipeline")
            unwrap(redis.client.Pipeline, "execute")
            unwrap(redis.client.Pipeline, "immediate_execute_command")


#
# tracing functions
#
def traced_execute_command(func, instance, args, kwargs):
    tracer = trace.get_tracer(__name__, __version__)
    pin = Pin.get_from(instance)
    # if not pin or not pin.enabled():
    #     return func(*args, **kwargs)

    with tracer.start_as_current_span(redisx.CMD) as span:
        span.set_attribute("service", pin.service)
        query = format_command_args(args)
        span.set_attribute(redisx.RAWCMD, query)
        for key, value in _get_attributes(instance).items():
            span.set_attribute(key, value)
        # TODO: set metric
        # s.set_metric(redisx.ARGS_LEN, len(args))
        return func(*args, **kwargs)


def traced_pipeline(func, instance, args, kwargs):
    pipeline = func(*args, **kwargs)
    pin = Pin.get_from(instance)
    if pin:
        pin.onto(pipeline)
    return pipeline


def traced_execute_pipeline(func, instance, args, kwargs):
    tracer = trace.get_tracer(__name__, __version__)
    pin = Pin.get_from(instance)
    # if not pin or not pin.enabled():
    #     return func(*args, **kwargs)

    # FIXME[matt] done in the agent. worth it?
    cmds = [format_command_args(c) for c, _ in instance.command_stack]
    resource = "\n".join(cmds)

    with tracer.start_as_current_span(redisx.CMD) as span:
        span.set_attribute("service", pin.service)
        span.set_attribute(redisx.RAWCMD, resource)
        for key, value in _get_attributes(instance).items():
            span.set_attribute(key, value)
        # TODO: set metric
        # s.set_metric(redisx.PIPELINE_LEN, len(instance.command_stack))
        return func(*args, **kwargs)


def _get_attributes(conn):
    return _extract_conn_attributes(conn.connection_pool.connection_kwargs)
