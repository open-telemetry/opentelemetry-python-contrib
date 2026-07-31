# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


from .nonstreaming_base import NonStreamingTestCase


class TestGenerateContentSyncNonstreaming(NonStreamingTestCase):
    def generate_content(self, *args, **kwargs):
        return self.client.models.generate_content(*args, **kwargs)

    @property
    def expected_function_name(self):
        return "google.genai.Models.generate_content"
