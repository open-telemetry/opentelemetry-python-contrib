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
* ``external-imports``: absolute imports of modules that are neither vendored nor in the
  standard library, which load the application's copy (or fail). Expected in instrumentation
  code, which patches the application's libraries.

Findings of every kind except ``imports`` can be allowed per file (or ``fnmatch`` pattern) after review.
Names are resolved through imports, so aliases such as ``import sys as _sys`` are
recognized.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
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
NATIVE_MODULE_NAMES = "native-module-names"
EXTERNAL_IMPORTS = "external-imports"
ALLOWABLE_KINDS = (DYNAMIC_IMPORTS, LOGGER_NAMES, MODULE_NAMES, SIDE_EFFECTS, EXTERNAL_IMPORTS, NATIVE_MODULE_NAMES)
"""Finding kinds that can be allowed per file in ``[tool.opentelemetry-vendor.allow]``."""
_KINDS = (IMPORTS, *ALLOWABLE_KINDS)
SOURCE_KINDS = (IMPORTS, DYNAMIC_IMPORTS, LOGGER_NAMES, MODULE_NAMES, SIDE_EFFECTS, EXTERNAL_IMPORTS)
"""Kinds found by ``find_issues`` in Python sources (checked by ``sync``)."""
EXTENSION_SUFFIXES = (".so", ".pyd")
# Dotted names in a binary: module names in native code are NUL-terminated C string literals.
_DOTTED_NAME_BYTES = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
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
# Standard library modules of Python 3.10+ missing from some versions' sys.stdlib_module_names:
# added after 3.10 or removed since (PEP 594), so the check doesn't depend on the running Python.
_VERSIONED_STDLIB_MODULES = frozenset(
    {
        "annotationlib",
        "compression",
        "tomllib",
        "aifc",
        "asynchat",
        "asyncore",
        "audioop",
        "cgi",
        "cgitb",
        "chunk",
        "crypt",
        "distutils",
        "imghdr",
        "imp",
        "lib2to3",
        "mailcap",
        "msilib",
        "nis",
        "nntplib",
        "ossaudiodev",
        "pipes",
        "smtpd",
        "sndhdr",
        "spwd",
        "sunau",
        "telnetlib",
        "uu",
        "xdrlib",
    }
)
_STDLIB_MODULES = sys.stdlib_module_names | _VERSIONED_STDLIB_MODULES
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

    def __init__(self, module: cst.Module, path: str, names: Collection[str], namespace: str) -> None:
        super().__init__()
        self.module = module
        self.path = path
        self.names = names
        self.namespace = namespace
        self.found: list[Finding] = []

    def visit_Import(self, node: cst.Import) -> None:
        modules = [alias_name(alias) for alias in node.names]
        if any(is_vendored(module, self.names, self.namespace) for module in modules):
            self._add(IMPORTS, node)
        if any(self._is_external(module) for module in modules):
            self._add(EXTERNAL_IMPORTS, node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.relative or node.module is None:
            return
        module = get_full_name_for_node(node.module)
        if module is not None and is_vendored(module, self.names, self.namespace):
            self._add(IMPORTS, node)
        if module is not None and self._is_external(module):
            self._add(EXTERNAL_IMPORTS, node)

    def _is_external(self, module: str) -> bool:
        top_level = module.split(".", 1)[0]
        return not (
            top_level in self.names
            or top_level in _STDLIB_MODULES
            or top_level == "__future__"
            or module == self.namespace
            or module.startswith(f"{self.namespace}.")
        )

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
        return module.startswith(".") or not is_vendored(module, self.names, self.namespace)

    def _is_vendored_literal(self, node: cst.Call, position: int) -> bool:
        """Whether the positional argument at ``position`` is a string literal naming a vendored module."""
        if len(node.args) <= position or node.args[position].keyword is not None:
            return False
        argument = node.args[position].value
        if not isinstance(argument, cst.SimpleString):
            return False
        value = argument.evaluated_value
        return isinstance(value, str) and not value.startswith(".") and is_vendored(value, self.names, self.namespace)

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


def find_issues(destination: Path, names: Collection[str], namespace: str) -> list[Finding]:
    """Find code escaping the vendor ``namespace`` in every ``.py`` file under ``destination``."""
    found: list[Finding] = []
    for path in sorted(destination.rglob("*.py")):
        wrapper = MetadataWrapper(parse_file(path))
        checker = _TreeChecker(wrapper.module, path.relative_to(destination).as_posix(), names, namespace)
        wrapper.visit(checker)
        found.extend(checker.found)
    return found


def find_native_issues(
    destination: Path, names: Collection[str], namespace: str, extensions: Collection[Path]
) -> list[Finding]:
    """Find un-namespaced vendored module names compiled into native ``extensions``.

    A string is flagged when it is a vendored *leaf* module path (e.g. ``google.protobuf.message``,
    ``google._upb._message``), or starts with one followed by ``.`` (e.g. the type name
    ``google._upb._message.Message``). Names under ``namespace`` are namespaced already. Package paths alone (``google.protobuf``) aren't flagged:
    they also occur as protobuf package names in embedded descriptors. Findings report the
    byte offset as their line.
    """
    leaves = _leaf_module_paths(destination, names)
    found: list[Finding] = []
    for extension in sorted(extensions):
        relative = extension.relative_to(destination).as_posix()
        for match in _DOTTED_NAME_BYTES.finditer(extension.read_bytes()):
            name = match.group().decode()
            if name.startswith(f"{namespace}."):
                continue
            parts = name.split(".")
            if any(".".join(parts[:end]) in leaves for end in range(2, len(parts) + 1)):
                found.append(Finding(kind=NATIVE_MODULE_NAMES, path=relative, line=match.start(), code=name))
    return found


def _leaf_module_paths(destination: Path, names: Collection[str]) -> set[str]:
    """Dotted paths of the (un-namespaced) vendored modules that aren't packages."""
    leaves = set()
    for path in destination.rglob("*"):
        if path.suffix not in (".py", *EXTENSION_SUFFIXES) or path.name.startswith("__init__."):
            continue
        parts = path.relative_to(destination).parts
        if parts[0] not in names and parts[0].split(".", 1)[0] not in names:
            continue
        module = path.name.split(".", 1)[0]
        leaves.add(".".join((*parts[:-1], module)))
    return leaves


def check_vendored_tree(
    destination: Path, names: Collection[str], namespace: str, allow: Mapping[str, Collection[str]]
) -> list[Finding]:
    """Check the Python sources; see ``check_findings``."""
    return check_findings(find_issues(destination, names, namespace), allow, SOURCE_KINDS)


def check_findings(
    found: Collection[Finding], allow: Mapping[str, Collection[str]], kinds: Collection[str]
) -> list[Finding]:
    """Raise ``VendorError`` for findings outside the ``allow``-ed files of their kind, or for unused entries.

    ``allow`` maps a kind from ``ALLOWABLE_KINDS`` to destination-relative file paths or ``fnmatch``
    patterns (``*`` also matches ``/``); only
    entries of the checked ``kinds`` must match something. Returns the allowed findings.
    """
    allowed = [
        finding
        for finding in found
        if finding.kind in ALLOWABLE_KINDS
        and any(fnmatchcase(finding.path, entry) for entry in allow.get(finding.kind, ()))
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
        if kind not in kinds:
            continue
        paths = {finding.path for finding in found if finding.kind == kind}
        for entry in entries:
            if not any(fnmatchcase(path, entry) for path in paths):
                raise VendorError(f"{ALLOW_TABLE} {kind} entry {entry!r} matched nothing")
    return allowed
