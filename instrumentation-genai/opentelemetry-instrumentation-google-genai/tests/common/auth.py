# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import google.auth.credentials


class FakeCredentials(google.auth.credentials.AnonymousCredentials):
    def __init__(self):
        self.token = "a"
        self._quota_project_id = "a"

    def refresh(self, request):
        pass
