"""Provides utilities for automatic content-type detection."""


# Helper used to handle the possibility of optional 'magic' dependency
# being unavailable for guessing the MIME type of raw bytes.
class _FallBackModule(object):
    """Class that is shaped like the portion of 'magic' we need."""

    def from_buffer(self, raw_bytes, mime=True):
        """Fallback, subpar implementation of 'from_buffer'."""
        return "application/octet-stream"


# Set up '_module' to either use 'magic' or the fallback.
_module = _FallBackModule()
try:
    import magic

    _module = magic
except ImportError:
    pass


def detect_content_type(raw_bytes: bytes) -> str:
    """Attempts to infer the content type of the specified data."""
    return _module.from_buffer(raw_bytes, mime=True)
