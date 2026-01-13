class ObjectProxy:
    """Minimal stand-in for wrapt.ObjectProxy used in tests."""

    def __init__(self, wrapped):
        self.__wrapped__ = wrapped

    def __getattr__(self, item):
        return getattr(self.__wrapped__, item)

    def __setattr__(self, key, value):
        if key == "__wrapped__":
            super().__setattr__(key, value)
        else:
            setattr(self.__wrapped__, key, value)

    def __call__(self, *args, **kwargs):
        return self.__wrapped__(*args, **kwargs)
