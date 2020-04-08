import requests

from ddtrace.vendor.wrapt import wrap_function_wrapper as _w

from ddtrace import config

from ddtrace.pin import Pin
from ddtrace.utils.formats import asbool, get_env
from ddtrace.utils.wrappers import unwrap as _u
from .constants import DEFAULT_SERVICE
from .connection import _wrap_send

# requests default settings
config._add('requests', {
    'service_name': get_env('requests', 'service_name', DEFAULT_SERVICE),
    'distributed_tracing': asbool(get_env('requests', 'distributed_tracing', True)),
    'split_by_domain': asbool(get_env('requests', 'split_by_domain', False)),
})


def patch():
    """Activate http calls tracing"""
    if getattr(requests, '__datadog_patch', False):
        return
    setattr(requests, '__datadog_patch', True)

    _w('requests', 'Session.send', _wrap_send)
    Pin(
        service=config.requests['service_name'],
        app='requests',
        _config=config.requests,
    ).onto(requests.Session)

def unpatch():
    """Disable traced sessions"""
    if not getattr(requests, '__datadog_patch', False):
        return
    setattr(requests, '__datadog_patch', False)

    _u(requests.Session, 'send')
