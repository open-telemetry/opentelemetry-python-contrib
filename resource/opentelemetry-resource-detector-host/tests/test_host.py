# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opentelemetry.resource.detector.host import (
    HostIdResourceDetector,
    _get_machine_id,
)
from opentelemetry.semconv.resource import ResourceAttributes


class HostIdResourceDetectorTest(unittest.TestCase):
    def test_detects_primary_machine_id_path(self):
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "machine-id"
            fallback = Path(directory) / "dbus-machine-id"
            primary.write_text("primary-id\n", encoding="utf-8")
            fallback.write_text("fallback-id\n", encoding="utf-8")

            with patch(
                "opentelemetry.resource.detector.host._MACHINE_ID_PATHS",
                (primary, fallback),
            ):
                resource = HostIdResourceDetector().detect()

        self.assertEqual(resource.attributes[ResourceAttributes.HOST_ID], "primary-id")

    def test_falls_back_when_primary_path_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "machine-id"
            fallback = Path(directory) / "dbus-machine-id"
            primary.write_text("\n", encoding="utf-8")
            fallback.write_text("fallback-id\n", encoding="utf-8")

            self.assertEqual(_get_machine_id((primary, fallback)), "fallback-id")

    def test_returns_empty_resource_when_files_are_unavailable(self):
        missing = Path("this-path-does-not-exist")
        with patch(
            "opentelemetry.resource.detector.host._MACHINE_ID_PATHS",
            (missing,),
        ):
            resource = HostIdResourceDetector().detect()

        self.assertNotIn(ResourceAttributes.HOST_ID, resource.attributes)


if __name__ == "__main__":
    unittest.main()
