import sys
from pathlib import Path

plugin_src = Path(__file__).resolve().parents[1] / "src"
dev_src = (
    Path(__file__).resolve().parents[2]
    / "opentelemetry-util-genai-dev"
    / "src"
)

for candidate in (dev_src, plugin_src):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
