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

from typing import Dict, Sequence
from urllib.parse import urlparse, urlunparse

from wrapt import ObjectProxy

from opentelemetry.trace import StatusCode


def extract_attributes_from_object(
    obj: any, attributes: Sequence[str], existing: Dict[str, str] = None
) -> Dict[str, str]:
    extracted = {}
    if existing:
        extracted.update(existing)
    for attr in attributes:
        value = getattr(obj, attr, None)
        if value is not None:
            extracted[attr] = str(value)
    return extracted


def http_status_to_status_code(
    status: int, allow_redirect: bool = True
) -> StatusCode:
    """Converts an HTTP status code to an OpenTelemetry canonical status code

    Args:
        status (int): HTTP status code
    """
    # See: https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#status
    if status < 100:
        return StatusCode.ERROR
    if status <= 299:
        return StatusCode.UNSET
    if status <= 399 and allow_redirect:
        return StatusCode.UNSET
    return StatusCode.ERROR


def unwrap(obj, attr: str):
    """Given a function that was wrapped by wrapt.wrap_function_wrapper, unwrap it

    Args:
        obj: Object that holds a reference to the wrapped function
        attr (str): Name of the wrapped function
    """
    func = getattr(obj, attr, None)
    if func and isinstance(func, ObjectProxy) and hasattr(func, "__wrapped__"):
        setattr(obj, attr, func.__wrapped__)


def remove_url_credentials(url: str) -> str:
    """Given a string url, remove the username and password only if it is a valid url"""

    def validate_url(url):
        try:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc])
        except ValueError:  # invalid url was passed
            return False

    if validate_url(url):
        parsed_url = urlparse(url)
        netloc = (
            (":".join(((parsed_url.hostname or ""), str(parsed_url.port))))
            if parsed_url.port
            else (parsed_url.hostname or "")
        )
        return urlunparse(
            (
                parsed_url.scheme,
                netloc,
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )
    return url
