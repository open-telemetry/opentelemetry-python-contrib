# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Vendored semantic convention definitions at the Development stability level."""

from typing import Final

URL_TEMPLATE: Final = "url.template"
"""
The low-cardinality template of an [absolute path reference](https://www.rfc-editor.org/rfc/rfc3986#section-4.2).
"""

HTTP_REQUEST_BODY_SIZE: Final = "http.request.body.size"
"""
The size of the request payload body in bytes. This is the number of bytes transferred excluding headers and is often, but not always, present as the [Content-Length](https://www.rfc-editor.org/rfc/rfc9110.html#field.content-length) header. For requests using transport encoding, this should be the compressed size.
"""

HTTP_REQUEST_SIZE: Final = "http.request.size"
"""
The total size of the request in bytes. This should be the total number of bytes sent over the wire, including the request line (HTTP/1.1), framing (HTTP/2 and HTTP/3), headers, and request body if any.
"""

HTTP_RESPONSE_BODY_SIZE: Final = "http.response.body.size"
"""
The size of the response payload body in bytes. This is the number of bytes transferred excluding headers and is often, but not always, present as the [Content-Length](https://www.rfc-editor.org/rfc/rfc9110.html#field.content-length) header. For requests using transport encoding, this should be the compressed size.
"""

HTTP_RESPONSE_SIZE: Final = "http.response.size"
"""
The total size of the response in bytes. This should be the total number of bytes sent over the wire, including the status line (HTTP/1.1), framing (HTTP/2 and HTTP/3), headers, and response body and trailers if any.
"""

USER_AGENT_SYNTHETIC_TYPE: Final = "user_agent.synthetic.type"
"""
Specifies the category of synthetic traffic, such as tests or bots.
"""

HTTP_REQUEST_BODY_CONTENT: Final = "http.request.body.content"
"""
The content of the HTTP request body, with any content coding indicated by [Content-Encoding](https://www.rfc-editor.org/rfc/rfc9110.html#field.content-encoding) removed, captured as a string when the request content is textual or as byte array otherwise.
"""

HTTP_RESPONSE_BODY_CONTENT: Final = "http.response.body.content"
"""
The content of the HTTP response body, with any content coding indicated by [Content-Encoding](https://www.rfc-editor.org/rfc/rfc9110.html#field.content-encoding) removed, captured as a string when the response content is textual or as byte array otherwise.
"""
