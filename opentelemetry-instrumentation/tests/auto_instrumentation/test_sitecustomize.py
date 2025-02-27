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
# type: ignore

from unittest import TestCase
from unittest.mock import patch


class TestSiteCustomize(TestCase):
    # pylint:disable=import-outside-toplevel,unused-import,no-self-use
    @patch("opentelemetry.instrumentation.auto_instrumentation.initialize")
    def test_sitecustomize_side_effects(self, initialize_mock):
        initialize_mock.assert_not_called()

        import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # NOQA

        initialize_mock.assert_called_once()
