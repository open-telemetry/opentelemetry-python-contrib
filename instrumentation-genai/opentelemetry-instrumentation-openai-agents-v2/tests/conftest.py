from __future__ import annotations

import sys
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
GENAI_ROOT = TESTS_ROOT.parent
REPO_ROOT = GENAI_ROOT.parent
PROJECT_ROOT = REPO_ROOT.parent

for path in (
    PROJECT_ROOT / "opentelemetry-instrumentation" / "src",
    GENAI_ROOT / "src",
    PROJECT_ROOT / "util" / "opentelemetry-util-genai" / "src",
    REPO_ROOT / "openai_agents_lib",
    REPO_ROOT / "openai_lib",
    TESTS_ROOT / "stubs",
):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
