# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=import-error

from .app_service import AzureAppServiceResourceDetector
from .functions import AzureFunctionsResourceDetector
from .version import __version__
from .vm import AzureVMResourceDetector

__all__ = [
    "AzureAppServiceResourceDetector",
    "AzureFunctionsResourceDetector",
    "AzureVMResourceDetector",
    "__version__",
]
