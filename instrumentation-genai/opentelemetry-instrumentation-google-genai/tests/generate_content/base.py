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

import unittest
import unittest.mock

from google.genai.models import AsyncModels, Models

from ..common.base import TestCase as CommonTestCaseBase
from .util import convert_to_response, create_response


# Helper used in "_install_mocks" below.
def _wrap_output(mock_generate_content):
    def _wrapped(*args, **kwargs):
        return convert_to_response(mock_generate_content(*args, **kwargs))

    return _wrapped


# Helper used in "_install_mocks" below.
def _wrap_output_stream(mock_generate_content_stream):
    def _wrapped(*args, **kwargs):
        for output in mock_generate_content_stream(*args, **kwargs):
            yield convert_to_response(output)

    return _wrapped


# Helper used in "_install_mocks" below.
def _async_wrapper(mock_generate_content):
    async def _wrapped(*args, **kwargs):
        return mock_generate_content(*args, **kwargs)

    return _wrapped


# Helper used in "_install_mocks" below.
def _async_stream_wrapper(mock_generate_content_stream):
    async def _wrapped(*args, **kwargs):
        async def _internal_generator():
            for result in mock_generate_content_stream(*args, **kwargs):
                yield result

        return _internal_generator()

    return _wrapped


class TestCase(CommonTestCaseBase):
    # The "setUp" function is defined by "unittest.TestCase" and thus
    # this name must be used. Uncertain why pylint doesn't seem to
    # recognize that this is a unit test class for which this is inherited.
    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        if self.__class__ == TestCase:
            raise unittest.SkipTest("Skipping testcase base.")
        self._generate_content_mock = None
        self._generate_content_stream_mock = None
        self._original_generate_content = Models.generate_content
        self._original_generate_content_stream = Models.generate_content_stream
        self._original_async_generate_content = AsyncModels.generate_content
        self._original_async_generate_content_stream = (
            AsyncModels.generate_content_stream
        )
        self._responses = []
        self._response_index = 0

    @property
    def mock_generate_content(self):
        if self._generate_content_mock is None:
            self._create_and_install_mocks()
        return self._generate_content_mock

    @property
    def mock_generate_content_stream(self):
        if self._generate_content_stream_mock is None:
            self._create_and_install_mocks()
        return self._generate_content_stream_mock

    def configure_valid_response(self, **kwargs):
        self._create_and_install_mocks()
        response = create_response(**kwargs)
        self._responses.append(response)

    def configure_exception(self, e, **kwargs):
        self._create_and_install_mocks(e)

    def _create_and_install_mocks_with(self):
        if self._generate_content_mock is not None:
            return
        self.reset_client()
        self.reset_instrumentation()
        self._generate_content_mock = self._create_nonstream_mock()
        self._generate_content_stream_mock = self._create_stream_mock()
        self._install_mocks()

    def _create_and_install_mocks(self, e=None):
        if self._generate_content_mock is not None:
            return
        self.reset_client()
        self.reset_instrumentation()
        self._generate_content_mock = self._create_nonstream_mock(e)
        self._generate_content_stream_mock = self._create_stream_mock(e)
        self._install_mocks()

    def _create_nonstream_mock(self, e=None):
        mock = unittest.mock.MagicMock()

        def _default_impl(*args, **kwargs):
            if not self._responses:
                return create_response(text="Some response")
            index = self._response_index % len(self._responses)
            result = self._responses[index]
            self._response_index += 1
            return result

        if not e:
            mock.side_effect = _default_impl
        else:
            mock.side_effect = e
        return mock

    def _create_stream_mock(self, e=None):
        mock = unittest.mock.MagicMock()

        def _default_impl(*args, **kwargs):
            for response in self._responses:
                yield response

        if not e:
            mock.side_effect = _default_impl
        else:
            mock.side_effect = e
        return mock

    def _install_mocks(self):
        output_wrapped = _wrap_output(self._generate_content_mock)
        output_wrapped_stream = _wrap_output_stream(
            self._generate_content_stream_mock
        )
        Models.generate_content = output_wrapped
        Models.generate_content_stream = output_wrapped_stream
        AsyncModels.generate_content = _async_wrapper(output_wrapped)
        AsyncModels.generate_content_stream = _async_stream_wrapper(
            output_wrapped_stream
        )

    def tearDown(self):
        super().tearDown()
        if self._generate_content_mock is None:
            assert Models.generate_content == self._original_generate_content
            assert (
                Models.generate_content_stream
                == self._original_generate_content_stream
            )
            assert (
                AsyncModels.generate_content
                == self._original_async_generate_content
            )
            assert (
                AsyncModels.generate_content_stream
                == self._original_async_generate_content_stream
            )
        Models.generate_content = self._original_generate_content
        Models.generate_content_stream = self._original_generate_content_stream
        AsyncModels.generate_content = self._original_async_generate_content
        AsyncModels.generate_content_stream = (
            self._original_async_generate_content_stream
        )
