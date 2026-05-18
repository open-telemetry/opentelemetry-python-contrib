# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio

from .nonstreaming_base import NonStreamingTestCase


class TestGenerateContentAsyncNonstreaming(NonStreamingTestCase):
    def generate_content(self, *args, **kwargs):
        return asyncio.run(
            self.client.aio.models.generate_content(*args, **kwargs)  # pylint: disable=missing-kwoa
        )

    @property
    def expected_function_name(self):
        return "google.genai.AsyncModels.generate_content"
