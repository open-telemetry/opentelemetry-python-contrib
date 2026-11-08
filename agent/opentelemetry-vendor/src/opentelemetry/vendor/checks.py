# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Check the final vendored tree (after rewriting and patching) for code that escapes the vendor namespace.

Each finding has a kind:

* ``imports``: an absolute import of a vendored package left over, e.g. added by a
  patch. Always an error.
* ``dynamic-imports``: ``__import__``, ``importlib.import_module``,
  ``importlib.resources`` lookups and ``sys.modules`` writes that can load or
  register modules by their top-level (non-vendored) names.
* ``logger-names``: ``logging.getLogger`` calls with a vendored-name literal left
  over, e.g. added by a patch; they log to the application's logger.
* ``module-names``: protobuf builder calls (in generated ``*_pb2`` code) with a
  vendored module-name literal left over; the generated classes' ``__module__``
  would point at the application's package.
* ``side-effects``: changes to process-global state shared with the application:
  warning filters and environment variables.

Findings of every kind except ``imports`` can be allowed per file after review.
Names are resolved through imports, so aliases such as ``import sys as _sys`` are
recognized.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
from libcst.helpers import get_full_name_for_node
from libcst.metadata import MetadataWrapper, PositionProvider, QualifiedNameProvider

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.rewrite import BUILD_TOP_DESCRIPTORS, alias_name, is_vendored, parse_file

IMPORTS = "imports"
DYNAMIC_IMPORTS = "dynamic-imports"
LOGGER_NAMES = "logger-names"
MODULE_NAMES = "module-names"
SIDE_EFFECTS = "side-effects"
ALLOWABLE_KINDS = (DYNAMIC_IMPORTS, LOGGER_NAMES, MODULE_NAMES, SIDE_EFFECTS)
"""Finding kinds that can be allowed per file in ``[tool.opentelemetry-vendor.allow]``."""
_KINDS = (IMPORTS, *ALLOWABLE_KINDS)
ALLOW_TABLE = "[tool.opentelemetry-vendor.allow]"

_IMPORT_FUNCTIONS = frozenset({"builtins.__import__", "importlib.import_module"})
# importlib.resources functions taking a package (anchor) as their first argument.
_RESOURCE_FUNCTIONS = frozenset(
    f"importlib.resources.{name}"
    for name in ("files", "path", "read_text", "read_binary", "open_text", "open_binary", "contents", "is_resource")
)
# Names that resolve to the calling (vendored) module at runtime.
_SELF_ANCHORS = frozenset({"__name__", "__package__"})
_MAPPING_MUTATORS = ("update", "setdefault", "pop", "popitem", "clear")
_SYS_MODULES = "sys.modules"
_SYS_MODULES_MUTATORS = frozenset(f"{_SYS_MODULES}.{method}" for method in _MAPPING_MUTATORS)
_GET_LOGGER = "logging.getLogger"
_OS_ENVIRON = "os.environ"
_SIDE_EFFECT_FUNCTIONS = frozenset(
    {
        "warnings.simplefilter",
        "warnings.filterwarnings",
        "warnings.resetwarnings",
        "os.putenv",
        "os.unsetenv",
        *(f"{_OS_ENVIRON}.{method}" for method in _MAPPING_MUTATORS),
    }
)


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    """POSIX path relative to the vendor destination."""
    line: int
    code: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.code}"


class _TreeChecker(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider, QualifiedNameProvider)

    def __init__(self, module: cst.Module, path: str, names: Collection[str]) -> None:
        super().__init__()
        self.module = module
        self.path = path
        self.names = names
        self.found: list[Finding] = []

    def visit_Import(self, node: cst.Import) -> None:
        if any(is_vendored(alias_name(alias), self.names) for alias in node.names):
            self._add(IMPORTS, node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.relative or node.module is None:
            return
        module = get_full_name_for_node(node.module)
        if module is not None and is_vendored(module, self.names):
            self._add(IMPORTS, node)

    def visit_Call(self, node: cst.Call) -> None:
        functions = self._qualified_names(node.func)
        if (
            functions & _SYS_MODULES_MUTATORS
            or (functions & _IMPORT_FUNCTIONS and not self._is_safe_literal(node))
            or (functions & _RESOURCE_FUNCTIONS and not self._is_safe_resource_anchor(node))
        ):
            self._add(DYNAMIC_IMPORTS, node)
        if _GET_LOGGER in functions and self._is_vendored_literal(node, 0):
            self._add(LOGGER_NAMES, node)
        # Also matches the builder after its import was rewritten into the vendor namespace.
        if any(
            function == BUILD_TOP_DESCRIPTORS or function.endswith(f".{BUILD_TOP_DESCRIPTORS}")
            for function in functions
        ) and self._is_vendored_literal(node, 1):
            self._add(MODULE_NAMES, node)
        if functions & _SIDE_EFFECT_FUNCTIONS:
            self._add(SIDE_EFFECTS, node)

    def visit_Assign(self, node: cst.Assign) -> None:
        self._check_targets(node, [target.target for target in node.targets])

    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:
        self._check_targets(node, [node.target])

    def visit_AugAssign(self, node: cst.AugAssign) -> None:
        self._check_targets(node, [node.target])

    def visit_Del(self, node: cst.Del) -> None:
        self._check_targets(node, [node.target])

    def _check_targets(self, node: cst.CSTNode, targets: Collection[cst.BaseExpression]) -> None:
        if any(self._writes_mapping(target, _SYS_MODULES) for target in targets):
            self._add(DYNAMIC_IMPORTS, node)
        if any(self._writes_mapping(target, _OS_ENVIRON) for target in targets):
            self._add(SIDE_EFFECTS, node)

    def _qualified_names(self, node: cst.CSTNode) -> set[str]:
        return {name.name for name in self.get_metadata(QualifiedNameProvider, node, set())}

    def _writes_mapping(self, target: cst.BaseExpression, mapping: str) -> bool:
        if isinstance(target, (cst.Tuple, cst.List)):
            return any(self._writes_mapping(element.value, mapping) for element in target.elements)
        return isinstance(target, cst.Subscript) and mapping in self._qualified_names(target.value)

    def _is_safe_literal(self, node: cst.Call) -> bool:
        """Whether the first argument is a string literal of a relative or non-vendored module."""
        if not node.args or node.args[0].keyword is not None:
            return False
        argument = node.args[0].value
        if not isinstance(argument, cst.SimpleString):
            return False
        module = argument.evaluated_value
        if not isinstance(module, str):
            return False
        return module.startswith(".") or not is_vendored(module, self.names)

    def _is_vendored_literal(self, node: cst.Call, position: int) -> bool:
        """Whether the positional argument at ``position`` is a string literal naming a vendored module."""
        if len(node.args) <= position or node.args[position].keyword is not None:
            return False
        argument = node.args[position].value
        if not isinstance(argument, cst.SimpleString):
            return False
        value = argument.evaluated_value
        return isinstance(value, str) and not value.startswith(".") and is_vendored(value, self.names)

    def _is_safe_resource_anchor(self, node: cst.Call) -> bool:
        """Whether the anchor is omitted, the calling module, or a non-vendored string literal."""
        if not node.args or node.args[0].keyword is not None:
            return not node.args
        argument = node.args[0].value
        if isinstance(argument, cst.Name) and argument.value in _SELF_ANCHORS:
            return True
        return self._is_safe_literal(node)

    def _add(self, kind: str, node: cst.CSTNode) -> None:
        line = self.get_metadata(PositionProvider, node).start.line
        code = " ".join(self.module.code_for_node(node).split())
        self.found.append(Finding(kind=kind, path=self.path, line=line, code=code))


def find_issues(destination: Path, names: Collection[str]) -> list[Finding]:
    """Find code escaping the vendor namespace in every ``.py`` file under ``destination``."""
    found: list[Finding] = []
    for path in sorted(destination.rglob("*.py")):
        wrapper = MetadataWrapper(parse_file(path))
        checker = _TreeChecker(wrapper.module, path.relative_to(destination).as_posix(), names)
        wrapper.visit(checker)
        found.extend(checker.found)
    return found


def check_vendored_tree(
    destination: Path, names: Collection[str], allow: Mapping[str, Collection[str]]
) -> list[Finding]:
    """Raise ``VendorError`` for findings outside the ``allow``-ed files of their kind, or for unused entries.

    ``allow`` maps a kind from ``ALLOWABLE_KINDS`` to destination-relative file paths.
    Returns the allowed findings.
    """
    found = find_issues(destination, names)
    allowed = [
        finding for finding in found if finding.kind in ALLOWABLE_KINDS and finding.path in allow.get(finding.kind, ())
    ]
    unallowed = [finding for finding in found if finding not in allowed]
    if unallowed:
        sections = []
        for kind in _KINDS:
            lines = [f"    {finding}" for finding in unallowed if finding.kind == kind]
            if not lines:
                continue
            hint = (
                "imports of vendored packages must be rewritten; check the patches"
                if kind == IMPORTS
                else f"patch them or add the file to {ALLOW_TABLE} {kind}"
            )
            sections.append(f"  {kind} ({hint}):\n" + "\n".join(lines))
        raise VendorError("vendored code escapes the vendor namespace:\n" + "\n".join(sections))
    for kind, entries in allow.items():
        paths = {finding.path for finding in found if finding.kind == kind}
        for entry in entries:
            if entry not in paths:
                raise VendorError(f"{ALLOW_TABLE} {kind} entry {entry!r} matched nothing")
    return allowed
