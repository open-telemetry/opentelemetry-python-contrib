# pylint: disable=protected-access

def indent(func):
    """
    Decorator for allowing to use method as normal method or with
    context manager for auto-indenting code blocks.
    """
    def wrapper(self, line, *args, optimize=True, **kwds):
        last_line = self._indent_last_line
        line = func(self, line, *args, **kwds)
        # When two blocks have the same condition (such as value has to be dict),
        # do the check only once and keep it under one block.
        merged = optimize and last_line == line
        if merged:
            self._code.pop()
        self._indent_last_line = line
        return Indent(self, line, merged=merged)
    return wrapper


class Indent:
    def __init__(self, instance, line, merged=False):
        self.instance = instance
        self.line = line
        self.merged = merged

    def __enter__(self):
        self.instance._indent += 1
        # A merged block is a continuation of the block just closed, so it keeps
        # its scope; otherwise this is a new scope and variables defined in it
        # are not visible to sibling blocks.
        if self.merged and self.instance._last_closed_scope is not None:
            scope = self.instance._last_closed_scope
        else:
            self.instance._scope_counter += 1
            scope = self.instance._scope_counter
        self.instance._scope_stack.append(scope)

    def __exit__(self, type_, value, traceback):
        self.instance._indent -= 1
        self.instance._last_closed_scope = self.instance._scope_stack.pop()
        self.instance._indent_last_line = self.line
