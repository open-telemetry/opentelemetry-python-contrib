# Ensure the local src/ path for opentelemetry.util.genai development version is importable
import sys
from pathlib import Path

plugin_src = Path(__file__).resolve().parents[1] / "src"
dev_src = (
    Path(__file__).resolve().parents[2]
    / "opentelemetry-util-genai-dev"
    / "src"
)

for candidate in (dev_src, plugin_src):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
