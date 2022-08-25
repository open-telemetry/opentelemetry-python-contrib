# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import grpc

from opentelemetry.instrumentation.grpc import grpcext


def _full_method(metadata):
    name = ""
    if isinstance(metadata, grpc.HandlerCallDetails):
        name = metadata.method
    # NOTE: replace here if there's better way to match cases to handle
    # grpcext._interceptor._UnaryClientInfo/_StreamClientInfo
    elif hasattr(metadata, "full_method"):
        name = metadata.full_method
    return name


def _split_full_method(metadata):
    name = _full_method(metadata)
    s, m = os.path.split(name)
    if s != "":
        s = os.path.normpath(s)
        s = s.lstrip("/")
    return (s, m)


def method_name(name):
    """Returns a filter function that return True if
    request's gRPC method name matches name.

    Args:
        name (str): method name to match

    Returns:
        A filter function that returns True if request's gRPC method
        name matches name
    """

    def fn(metadata):
        _, method = _split_full_method(metadata)
        return method == name

    return fn


def method_prefix(prefix):
    """Returns a filter function that return True if
    request's gRPC method name starts with prefix.

    Args:
        prefix (str): method prefix to match

    Returns:
        A filter function that returns True if request's gRPC method
        name starts with prefix
    """

    def fn(metadata):
        _, method = _split_full_method(metadata)
        return method.startswith(prefix)

    return fn


def full_method_name(name):
    """Returns a filter function that return True if
    request's gRPC full method name matches name.

    Args:
        name (str): full method name to match

    Returns:
        A filter function that returns True if request's gRPC full
        method name matches name
    """

    def fn(metadata):
        fm = _full_method(metadata)
        return fm == name

    return fn


def service_name(name):
    """Returns a filter function that return True if
    request's gRPC service name matches name.

    Args:
        name (str): service name to match

    Returns:
        A filter function that returns True if request's gRPC service
        name matches name
    """

    def fn(metadata):
        service, _ = _split_full_method(metadata)
        return service == name

    return fn


def service_prefix(prefix):
    """Returns a filter function that return True if
    request's gRPC service name starts with prefix.

    Args:
        prefix (str): method prefix to match

    Returns:
        A filter function that returns True if request's gRPC method
        name starts with prefix
    """

    def fn(metadata):
        service, _ = _split_full_method(metadata)
        return service.startswith(prefix)

    return fn


def health_check():
    """Returns a Filter that returns true if the request's
    service name is health check defined by gRPC Health Checking Protocol.
    https://github.com/grpc/grpc/blob/master/doc/health-checking.md
    """
    return service_prefix("grpc.health.v1.Health")


__all__ = [
    "method_name",
    "method_prefix",
    "full_method_name",
    "service_name",
    "service_prefix",
    "health_check",
]
