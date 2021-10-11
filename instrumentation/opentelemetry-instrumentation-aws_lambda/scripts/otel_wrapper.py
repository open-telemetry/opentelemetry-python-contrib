#!/usr/bin/env python3

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

"""
`otel_wrapper.py`

This file serves as a wrapper over the user's Lambda function.

Usage
-----
Patch the reserved `_HANDLER` Lambda environment variable to point to this
file's `otel_wrapper.lambda_handler` property. Do this having saved the original
`_HANDLER` in the `ORIG_HANDLER` environment variable. Doing this makes it so
that **on import of this file, the handler is instrumented**.

Instrumenting any earlier will cause the instrumentation to be lost because the
AWS Service uses `imp.load_module` to import the handler which RELOADS the
module. This is why AwsLambdaInstrumentor cannot be instrumented with the
`opentelemetry-instrument` script.

See more:
https://docs.python.org/3/library/imp.html#imp.load_module

"""

import os
from importlib import import_module

from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor

AwsLambdaInstrumentor().instrument()


def modify_module_name(module_name):
    """Returns a valid modified module to get imported"""
    return ".".join(module_name.split("/"))


class HandlerError(Exception):
    pass


path = os.environ.get("ORIG_HANDLER", None)
if path is None:
    raise HandlerError("ORIG_HANDLER is not defined.")
parts = path.rsplit(".", 1)
if len(parts) != 2:
    raise HandlerError("Value %s for ORIG_HANDLER has invalid format." % path)

(mod_name, handler_name) = parts
modified_mod_name = modify_module_name(mod_name)
handler_module = import_module(modified_mod_name)
lambda_handler = getattr(handler_module, handler_name)
