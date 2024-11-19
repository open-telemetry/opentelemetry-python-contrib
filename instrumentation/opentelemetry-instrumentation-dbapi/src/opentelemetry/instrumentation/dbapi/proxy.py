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


from abc import ABC, abstractmethod

import wrapt


class BaseTracedConnectionProxy(ABC, wrapt.ObjectProxy):
    # pylint: disable=unused-argument
    def __init__(self, connection, *args, **kwargs):
        wrapt.ObjectProxy.__init__(self, connection)

    def __getattribute__(self, name):
        if object.__getattribute__(self, name):
            return object.__getattribute__(self, name)

        return object.__getattribute__(
            object.__getattribute__(self, "_connection"), name
        )

    @abstractmethod
    def cursor(self, *args, **kwargs):
        """Returns instrumented database query cursor"""

    def __enter__(self):
        self.__wrapped__.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.__wrapped__.__exit__(*args, **kwargs)


# pylint: disable=abstract-method
class BaseTracedCursorProxy(ABC, wrapt.ObjectProxy):
    # pylint: disable=unused-argument
    @abstractmethod
    def __init__(self, cursor, *args, **kwargs):
        """Wrap db client cursor for tracing"""
        wrapt.ObjectProxy.__init__(self, cursor)
        self._cursor_tracer = None

    def callproc(self, *args, **kwargs):
        return self._cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.callproc, *args, **kwargs
        )

    def execute(self, *args, **kwargs):
        return self._cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.execute, *args, **kwargs
        )

    def executemany(self, *args, **kwargs):
        return self._cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.executemany, *args, **kwargs
        )

    def __enter__(self):
        self.__wrapped__.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.__wrapped__.__exit__(*args, **kwargs)
