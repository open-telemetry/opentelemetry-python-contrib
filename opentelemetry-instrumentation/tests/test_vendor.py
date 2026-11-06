# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Checks on the vendored tree, not on what the vendored code does.

The vendored project has its own test suite and it does not run here. What is
specific to this repository is the property that vendoring exists to create:
that the published distribution needs no third-party dependency to import and
use the code under ``_vendor``.
"""

from ast import AST, If, Import, ImportFrom, iter_child_nodes, parse, walk
from importlib.metadata import requires
from pathlib import Path
from sys import stdlib_module_names

from opentelemetry.instrumentation import _vendor

_VENDOR_ROOT = Path(_vendor.__file__).parent


def test_the_vendored_tree_imports_nothing_it_does_not_ship() -> None:
    """Every runtime import under ``_vendor`` resolves without an install.

    An absolute import of a project that is not itself vendored resolves
    against the application's environment rather than against this tree, which
    reintroduces the undeclared dependency the tree exists to avoid. Nothing in
    the generated output announces such an import, so it is searched for here.

    Imports reached only under ``typing.TYPE_CHECKING`` are excluded because a
    type checker evaluates them and the interpreter never does.
    """
    imported: set[str] = set()

    for source_file in sorted(_VENDOR_ROOT.rglob("*.py")):
        pending: list[AST] = [parse(source_file.read_text(encoding="utf-8"))]
        while pending:
            node: AST = pending.pop()
            if isinstance(node, If) and any(
                getattr(inner, "id", None) == "TYPE_CHECKING" or getattr(inner, "attr", None) == "TYPE_CHECKING"
                for inner in walk(node.test)
            ):
                pending.extend(node.orelse)
                continue
            if isinstance(node, Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ImportFrom) and node.level == 0 and node.module is not None:
                imported.add(node.module.split(".")[0])
            pending.extend(iter_child_nodes(node))

    unexpected: set[str] = imported - stdlib_module_names - {"opentelemetry"}

    assert not unexpected, (
        f"the vendored tree imports {sorted(unexpected)} at runtime; each of "
        f"those must be vendored too or the distribution depends on it without "
        f"declaring it"
    )


def test_packaging_is_not_a_runtime_dependency() -> None:
    """The vendored copy replaces the dependency rather than joining it."""
    declared: list[str] = requires("opentelemetry-instrumentation") or []

    assert not [requirement for requirement in declared if requirement.lower().startswith("packaging")]
