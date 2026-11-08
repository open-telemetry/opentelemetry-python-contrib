# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from opentelemetry.vendor.checks import (
    DYNAMIC_IMPORTS,
    IMPORTS,
    LOGGER_NAMES,
    MODULE_NAMES,
    SIDE_EFFECTS,
    Finding,
    check_vendored_tree,
    find_issues,
)
from opentelemetry.vendor.errors import VendorError

NAMES = frozenset({"idna", "urllib3"})

# Imports used by the test sources; names are resolved through them.
HEADER = """\
import importlib
import logging
import os
import warnings
import warnings as w
from os import environ
import importlib.resources
import sys
import sys as _sys
from importlib import import_module
from importlib import import_module as im
from importlib.resources import as_file, files, read_text
from importlib.resources import path as get_path
"""
SOURCE_LINE = HEADER.count("\n") + 1


@pytest.mark.parametrize(
    ("source", "code"),
    [
        pytest.param("__import__(package)", "__import__(package)", id="import-variable"),
        pytest.param("__import__('urllib3')", "__import__('urllib3')", id="import-vendored-literal"),
        pytest.param("__import__(name='os')", "__import__(name='os')", id="import-keyword"),
        pytest.param(
            "importlib.import_module('idna.core')",
            "importlib.import_module('idna.core')",
            id="import-module-vendored-literal",
        ),
        pytest.param(
            "import_module(f'encodings.{x}')",
            "import_module(f'encodings.{x}')",
            id="import-module-f-string",
        ),
        pytest.param(
            "import_module('encod' 'ings')",
            "import_module('encod' 'ings')",
            id="import-module-concatenated",
        ),
        pytest.param("sys.modules['x'] = m", "sys.modules['x'] = m", id="sys-modules-assign"),
        pytest.param("a = sys.modules['x'] = m", "a = sys.modules['x'] = m", id="sys-modules-chained-assign"),
        pytest.param("sys.modules['x'], b = m, n", "sys.modules['x'], b = m, n", id="sys-modules-tuple-assign"),
        pytest.param("sys.modules['x']: T = m", "sys.modules['x']: T = m", id="sys-modules-ann-assign"),
        pytest.param("sys.modules['x'] |= m", "sys.modules['x'] |= m", id="sys-modules-aug-assign"),
        pytest.param("del sys.modules['x']", "del sys.modules['x']", id="sys-modules-del"),
        pytest.param("del a, sys.modules['x']", "del a, sys.modules['x']", id="sys-modules-del-tuple"),
        pytest.param("sys.modules.update({})", "sys.modules.update({})", id="sys-modules-update"),
        pytest.param("sys.modules.setdefault('x', m)", "sys.modules.setdefault('x', m)", id="sys-modules-setdefault"),
        pytest.param("sys.modules.pop('x')", "sys.modules.pop('x')", id="sys-modules-pop"),
        pytest.param(
            "sys.modules[\n    'x'\n] = m",
            "sys.modules[ 'x' ] = m",
            id="multiline-collapsed",
        ),
        pytest.param("im(package)", "im(package)", id="import-module-alias"),
        pytest.param("_sys.modules['x'] = m", "_sys.modules['x'] = m", id="sys-modules-alias"),
        pytest.param("_sys.modules.pop('x')", "_sys.modules.pop('x')", id="sys-modules-alias-pop"),
        pytest.param("files('urllib3')", "files('urllib3')", id="files-vendored-literal"),
        pytest.param(
            "importlib.resources.files('idna.core')",
            "importlib.resources.files('idna.core')",
            id="files-attribute",
        ),
        pytest.param(
            "as_file(files('urllib3').joinpath('x'))",
            "files('urllib3')",
            id="as-file-wrapping-files",
        ),
        pytest.param("files(package)", "files(package)", id="files-variable"),
        pytest.param("get_path('urllib3', 'x')", "get_path('urllib3', 'x')", id="legacy-path-alias"),
        pytest.param("read_text(name, 'x')", "read_text(name, 'x')", id="legacy-read-text-variable"),
        pytest.param(
            "importlib.resources.is_resource(anchor='idna', name='x')",
            "importlib.resources.is_resource(anchor='idna', name='x')",
            id="legacy-keyword-anchor",
        ),
        pytest.param(
            "def f():\n    from importlib.resources import read_binary\n    return read_binary('idna', 'x')",
            "read_binary('idna', 'x')",
            id="legacy-local-import",
        ),
    ],
)
def test_find_issues_dynamic_imports(tmp_path: Path, source: str, code: str) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(f"{HEADER}{source}\n")

    [finding] = find_issues(tmp_path, NAMES)

    assert finding.kind == DYNAMIC_IMPORTS
    assert finding.path == "pkg/mod.py"
    assert finding.line >= SOURCE_LINE
    assert finding.code == code


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("__import__('os')", id="import-stdlib-literal"),
        pytest.param("__import__('urllib3x')", id="import-prefix-collision"),
        pytest.param("importlib.import_module('.sub', __package__)", id="import-module-relative"),
        pytest.param("import_module('encodings.utf_8')", id="import-module-stdlib-literal"),
        pytest.param("m = sys.modules[name]", id="sys-modules-read"),
        pytest.param("for m in list(sys.modules): pass", id="sys-modules-iterate"),
        pytest.param("sys.modules.get('x')", id="sys-modules-get"),
        pytest.param("cache['x'] = m", id="other-subscript"),
        pytest.param('"""__import__(package)"""\n# sys.modules["x"] = m', id="docstring-and-comment"),
        pytest.param("files(__package__)", id="files-package"),
        pytest.param("files(__name__)", id="files-name"),
        pytest.param("files()", id="files-calling-module"),
        pytest.param("files('os')", id="files-stdlib-literal"),
        pytest.param("as_file(files(__package__).joinpath('x'))", id="as-file-package"),
        pytest.param("get_path(__package__, 'cacert.pem')", id="legacy-path-package"),
        pytest.param("self.read_text('urllib3')", id="method-named-like-resource-function"),
        pytest.param("import_module_x('urllib3')", id="other-function"),
        pytest.param("warnings.warn('x')", id="warnings-warn"),
        pytest.param("with warnings.catch_warnings(): pass", id="warnings-catch"),
        pytest.param("value = os.environ['x']", id="environ-read"),
        pytest.param("os.environ.get('x')", id="environ-get"),
        pytest.param("env = dict(os.environ)\nenv['x'] = '1'", id="environ-copy"),
        pytest.param("import urllib3x\nfrom . import urllib3\nfrom .urllib3 import a", id="non-vendored-imports"),
        pytest.param("from opentelemetry.agent._vendor import urllib3", id="namespaced-import"),
        pytest.param("logging.getLogger(__name__)", id="logger-dunder-name"),
        pytest.param("logging.getLogger(name)", id="logger-variable"),
        pytest.param("logging.getLogger('opentelemetry.agent._vendor.urllib3')", id="logger-namespaced"),
    ],
)
def test_find_issues_ignores(tmp_path: Path, source: str) -> None:
    (tmp_path / "mod.py").write_text(f"{HEADER}{source}\n")

    assert find_issues(tmp_path, NAMES) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("def files(name): pass\nfiles('urllib3')", id="local-function-named-files"),
        pytest.param("import_module('urllib3')\nsys.modules['x'] = m", id="names-not-imported"),
        pytest.param("simplefilter('ignore')\nenviron['x'] = '1'", id="side-effect-names-not-imported"),
    ],
)
def test_find_issues_ignores_unresolved_names(tmp_path: Path, source: str) -> None:
    (tmp_path / "mod.py").write_text(f"{source}\n")

    assert find_issues(tmp_path, NAMES) == []


@pytest.mark.parametrize(
    ("source", "kind", "code"),
    [
        pytest.param("import urllib3", IMPORTS, "import urllib3", id="import"),
        pytest.param("import os, urllib3.util as u", IMPORTS, "import os, urllib3.util as u", id="import-multiple"),
        pytest.param("from idna import core", IMPORTS, "from idna import core", id="from-import"),
        pytest.param(
            "warnings.simplefilter('ignore', Warning)",
            SIDE_EFFECTS,
            "warnings.simplefilter('ignore', Warning)",
            id="simplefilter",
        ),
        pytest.param(
            "w.filterwarnings('ignore')", SIDE_EFFECTS, "w.filterwarnings('ignore')", id="filterwarnings-alias"
        ),
        pytest.param("warnings.resetwarnings()", SIDE_EFFECTS, "warnings.resetwarnings()", id="resetwarnings"),
        pytest.param("os.environ['x'] = '1'", SIDE_EFFECTS, "os.environ['x'] = '1'", id="environ-assign"),
        pytest.param("environ['x'] = '1'", SIDE_EFFECTS, "environ['x'] = '1'", id="environ-from-import"),
        pytest.param("del os.environ['x']", SIDE_EFFECTS, "del os.environ['x']", id="environ-del"),
        pytest.param("os.environ['x'] += '1'", SIDE_EFFECTS, "os.environ['x'] += '1'", id="environ-aug-assign"),
        pytest.param("os.environ.update(x='1')", SIDE_EFFECTS, "os.environ.update(x='1')", id="environ-update"),
        pytest.param("environ.pop('x')", SIDE_EFFECTS, "environ.pop('x')", id="environ-pop"),
        pytest.param("os.putenv('x', '1')", SIDE_EFFECTS, "os.putenv('x', '1')", id="putenv"),
        pytest.param("os.unsetenv('x')", SIDE_EFFECTS, "os.unsetenv('x')", id="unsetenv"),
        pytest.param(
            "logging.getLogger('urllib3.pool')",
            LOGGER_NAMES,
            "logging.getLogger('urllib3.pool')",
            id="vendored-logger-name",
        ),
    ],
)
def test_find_issues(tmp_path: Path, source: str, kind: str, code: str) -> None:
    (tmp_path / "mod.py").write_text(f"{HEADER}{source}\n")

    assert find_issues(tmp_path, NAMES) == [Finding(kind=kind, path="mod.py", line=SOURCE_LINE, code=code)]


def test_check_vendored_tree_allowed(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "packages.py").write_text(
        "import sys, warnings\n__import__(package)\nsys.modules[k] = m\nwarnings.simplefilter('ignore')\n"
    )
    (tmp_path / "clean.py").write_text("import os\n")

    allowed = check_vendored_tree(
        tmp_path, NAMES, {DYNAMIC_IMPORTS: ["pkg/packages.py"], SIDE_EFFECTS: ["pkg/packages.py"]}
    )

    assert [(finding.kind, str(finding)) for finding in allowed] == [
        (DYNAMIC_IMPORTS, "pkg/packages.py:2: __import__(package)"),
        (DYNAMIC_IMPORTS, "pkg/packages.py:3: sys.modules[k] = m"),
        (SIDE_EFFECTS, "pkg/packages.py:4: warnings.simplefilter('ignore')"),
    ]


def test_check_vendored_tree_allow_is_per_kind(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os, sys\nsys.modules['x'] = m\nos.environ['x'] = '1'\n")

    with pytest.raises(VendorError) as exc_info:
        check_vendored_tree(tmp_path, NAMES, {DYNAMIC_IMPORTS: ["a.py"]})

    assert str(exc_info.value) == (
        "vendored code escapes the vendor namespace:\n"
        "  side-effects (patch them or add the file to [tool.opentelemetry-vendor.allow] side-effects):\n"
        "    a.py:3: os.environ['x'] = '1'"
    )


def test_check_vendored_tree_unallowed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("__import__(package)\nimport urllib3\n")
    (tmp_path / "b.py").write_text("import importlib\nimportlib.import_module(name)\n")

    with pytest.raises(VendorError) as exc_info:
        check_vendored_tree(tmp_path, NAMES, {IMPORTS: ["a.py"]})

    assert str(exc_info.value) == (
        "vendored code escapes the vendor namespace:\n"
        "  imports (imports of vendored packages must be rewritten; check the patches):\n"
        "    a.py:2: import urllib3\n"
        "  dynamic-imports (patch them or add the file to [tool.opentelemetry-vendor.allow] dynamic-imports):\n"
        "    a.py:1: __import__(package)\n"
        "    b.py:2: importlib.import_module(name)"
    )


def test_check_vendored_tree_unused_entry(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import sys\nsys.modules['x'] = m\n")

    with pytest.raises(
        VendorError, match=r"\[tool.opentelemetry-vendor.allow\] side-effects entry 'a.py' matched nothing"
    ):
        check_vendored_tree(tmp_path, NAMES, {DYNAMIC_IMPORTS: ["a.py"], SIDE_EFFECTS: ["a.py"]})


def test_check_vendored_tree_unparsable_file(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("__import__(\n")

    with pytest.raises(VendorError, match=r"cannot parse .*broken\.py"):
        check_vendored_tree(tmp_path, NAMES, {})


@pytest.mark.parametrize(
    ("builder_import", "module_name", "flagged"),
    [
        pytest.param("from google.protobuf.internal import builder", "google.protobuf.any_pb2", True, id="leftover"),
        pytest.param(
            "from opentelemetry.agent._vendor.google.protobuf.internal import builder",
            "google.protobuf.any_pb2",
            True,
            id="leftover-after-import-rewrite",
        ),
        pytest.param(
            "from opentelemetry.agent._vendor.google.protobuf.internal import builder",
            "opentelemetry.agent._vendor.google.protobuf.any_pb2",
            False,
            id="namespaced",
        ),
    ],
)
def test_find_issues_protobuf_module_names(
    tmp_path: Path, builder_import: str, module_name: str, flagged: bool
) -> None:
    call = f"builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, {module_name!r}, _globals)"
    (tmp_path / "x_pb2.py").write_text(f"{builder_import}\n{call}\n")

    findings = [finding for finding in find_issues(tmp_path, NAMES | {"google"}) if finding.kind != IMPORTS]

    assert findings == ([Finding(kind=MODULE_NAMES, path="x_pb2.py", line=2, code=call)] if flagged else [])
