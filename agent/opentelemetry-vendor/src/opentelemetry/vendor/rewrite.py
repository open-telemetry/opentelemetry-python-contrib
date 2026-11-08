# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Rewrite imports, logger names and module names of vendored packages to point into the vendor namespace."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
from libcst.helpers import get_full_name_for_node
from libcst.metadata import MetadataWrapper, QualifiedNameProvider

from opentelemetry.vendor.errors import VendorError

_GET_LOGGER = "logging.getLogger"
BUILD_TOP_DESCRIPTORS = "google.protobuf.internal.builder.BuildTopDescriptorsAndMessages"
"""Called by protoc-generated ``*_pb2`` modules with their module name, which becomes the classes' ``__module__``."""
# Callee -> (position of the module-name argument, RewriteResult counter).
_MODULE_NAME_ARGUMENTS = {_GET_LOGGER: (0, "loggers"), BUILD_TOP_DESCRIPTORS: (1, "modules")}
_DOTTED_NAME = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")


@dataclass(frozen=True)
class RewriteResult:
    files: int
    """Number of files with at least one rewritten import."""
    imports: int
    """Number of rewritten imported module names."""
    loggers: int = 0
    """Number of rewritten logger-name string literals."""
    modules: int = 0
    """Number of rewritten module-name string literals (protobuf generated code)."""


class _ImportTransformer(cst.CSTTransformer):
    """Move absolute imports of vendored ``names`` under ``namespace``.

    ``from X import Y`` becomes ``from namespace.X import Y``. Plain imports keep
    binding the same local name: ``import X`` becomes ``from namespace import X``,
    ``import X.Y as Z`` becomes ``from namespace.X import Y as Z`` and ``import X.Y``
    becomes ``from namespace import X`` plus ``import namespace.X.Y`` to load the
    submodule. A line containing an expanded import is split into one statement per line.

    Logger names are namespaced too, so vendored code doesn't log to (or configure) the
    application's loggers: a vendored-name string literal passed to ``logging.getLogger``
    or used as a parameter default (e.g. ``name: str = "X"``) becomes ``"namespace.X"``.
    So are the module names protoc-generated code passes to protobuf's builder, which
    become the generated classes' ``__module__`` (used by pickle, for example).
    """

    METADATA_DEPENDENCIES = (QualifiedNameProvider,)

    def __init__(self, namespace: str, names: Collection[str]) -> None:
        super().__init__()
        self.namespace = namespace
        self.names = names
        self.count = 0
        self.loggers = 0
        self.modules = 0
        self._expanded = False

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        qualified_names = {name.name for name in self.get_metadata(QualifiedNameProvider, original_node.func, set())}
        for function, (position, counter) in _MODULE_NAME_ARGUMENTS.items():
            if function not in qualified_names or len(updated_node.args) <= position:
                continue
            arguments = list(updated_node.args)
            argument = arguments[position]
            if argument.keyword is not None or not isinstance(argument.value, cst.SimpleString):
                return updated_node
            namespaced = self._namespaced_module_name(argument.value)
            if namespaced is None:
                return updated_node
            setattr(self, counter, getattr(self, counter) + 1)
            arguments[position] = argument.with_changes(value=namespaced)
            return updated_node.with_changes(args=arguments)
        return updated_node

    def leave_Param(self, original_node: cst.Param, updated_node: cst.Param) -> cst.Param:
        if not isinstance(updated_node.default, cst.SimpleString):
            return updated_node
        namespaced = self._namespaced_module_name(updated_node.default)
        if namespaced is None:
            return updated_node
        self.loggers += 1
        return updated_node.with_changes(default=namespaced)

    def _namespaced_module_name(self, node: cst.SimpleString) -> cst.SimpleString | None:
        value = node.evaluated_value
        if not isinstance(value, str) or not _DOTTED_NAME.fullmatch(value) or not is_vendored(value, self.names):
            return None
        return node.with_changes(value=f"{node.prefix}{node.quote}{self.namespace}.{value}{node.quote}")

    def leave_ImportFrom(self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom) -> cst.ImportFrom:
        if updated_node.relative or updated_node.module is None:
            return updated_node
        module = get_full_name_for_node(updated_node.module)
        if module is None or not is_vendored(module, self.names):
            return updated_node
        self.count += 1
        return updated_node.with_changes(module=_dotted_name(f"{self.namespace}.{module}"))

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.BaseSmallStatement | cst.FlattenSentinel[cst.BaseSmallStatement]:
        if not any(is_vendored(alias_name(alias), self.names) for alias in updated_node.names):
            return updated_node
        statements: list[cst.BaseSmallStatement] = []
        for alias in updated_node.names:
            name = alias_name(alias)
            if is_vendored(name, self.names):
                statements.extend(self._rewrite_alias(name, alias.asname))
                self.count += 1
            else:
                statements.append(cst.Import(names=[alias.with_changes(comma=cst.MaybeSentinel.DEFAULT)]))
        statements[-1] = statements[-1].with_changes(semicolon=updated_node.semicolon)
        if len(statements) == 1:
            return statements[0]
        self._expanded = True
        return cst.FlattenSentinel(statements)

    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> None:
        self._expanded = False

    def leave_SimpleStatementLine(
        self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine
    ) -> cst.SimpleStatementLine | cst.FlattenSentinel[cst.SimpleStatementLine]:
        if not self._expanded:
            return updated_node
        lines = [
            cst.SimpleStatementLine(body=[statement.with_changes(semicolon=cst.MaybeSentinel.DEFAULT)])
            for statement in updated_node.body
        ]
        lines[0] = lines[0].with_changes(leading_lines=updated_node.leading_lines)
        lines[-1] = lines[-1].with_changes(trailing_whitespace=updated_node.trailing_whitespace)
        return cst.FlattenSentinel(lines)

    def _rewrite_alias(self, name: str, asname: cst.AsName | None) -> list[cst.BaseSmallStatement]:
        package, _, attribute = name.rpartition(".")
        if asname is not None:
            # import X as Z -> from ns import X as Z; import X.Y as Z -> from ns.X import Y as Z
            module = f"{self.namespace}.{package}" if package else self.namespace
            return [_import_from(module, attribute, asname)]
        top_level = name.split(".", 1)[0]
        statements: list[cst.BaseSmallStatement] = [_import_from(self.namespace, top_level, None)]
        if package:
            # Binding X alone does not load the X.Y submodule.
            statements.append(cst.Import(names=[cst.ImportAlias(name=_dotted_name(f"{self.namespace}.{name}"))]))
        return statements


def rewrite_source(source: str, namespace: str, names: Collection[str]) -> str:
    """Return ``source`` with imports and logger names of vendored ``names`` moved under ``namespace``."""
    return MetadataWrapper(cst.parse_module(source)).visit(_ImportTransformer(namespace, names)).code


def rewrite_imports(destination: Path, namespace: str, names: Collection[str]) -> RewriteResult:
    """Rewrite imports and logger names of vendored ``names`` in every ``.py`` file under ``destination``.

    Raises ``VendorError`` if a file cannot be parsed. Leftover vendored imports are
    reported by ``opentelemetry.vendor.checks``, which runs after patches.
    """
    files = 0
    imports = 0
    loggers = 0
    modules = 0
    for path in sorted(destination.rglob("*.py")):
        transformer = _ImportTransformer(namespace, names)
        rewritten = MetadataWrapper(parse_file(path)).visit(transformer)
        if transformer.count or transformer.loggers or transformer.modules:
            path.write_bytes(rewritten.bytes)
            files += 1
            imports += transformer.count
            loggers += transformer.loggers
            modules += transformer.modules
    return RewriteResult(files=files, imports=imports, loggers=loggers, modules=modules)


def parse_file(path: Path) -> cst.Module:
    try:
        return cst.parse_module(path.read_bytes())
    except cst.ParserSyntaxError as exc:
        raise VendorError(f"cannot parse {path}: {exc}") from exc


def is_vendored(name: str, names: Collection[str]) -> bool:
    """Whether dotted module ``name`` belongs to one of the vendored top-level ``names``."""
    return name.split(".", 1)[0] in names


def alias_name(alias: cst.ImportAlias) -> str:
    """The dotted module name of an ``import`` statement alias."""
    # ImportAlias names in `import` statements are always Name or Attribute nodes.
    return get_full_name_for_node(alias.name) or ""


def _import_from(module: str, name: str, asname: cst.AsName | None) -> cst.ImportFrom:
    return cst.ImportFrom(module=_dotted_name(module), names=[cst.ImportAlias(name=cst.Name(name), asname=asname)])


def _dotted_name(name: str) -> cst.Attribute | cst.Name:
    first, *rest = name.split(".")
    node: cst.Attribute | cst.Name = cst.Name(first)
    for part in rest:
        node = cst.Attribute(value=node, attr=cst.Name(part))
    return node
