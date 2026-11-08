# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from opentelemetry.vendor.errors import VendorError
from opentelemetry.vendor.rewrite import RewriteResult, rewrite_imports, rewrite_source

NAMESPACE = "opentelemetry.agent._vendor"
NAMES = frozenset({"idna", "requests", "urllib3"})


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "from urllib3 import PoolManager\n",
            "from opentelemetry.agent._vendor.urllib3 import PoolManager\n",
            id="package",
        ),
        pytest.param(
            "from urllib3.util.retry import Retry\n",
            "from opentelemetry.agent._vendor.urllib3.util.retry import Retry\n",
            id="submodule",
        ),
        pytest.param(
            "from requests import Session as S, get\n",
            "from opentelemetry.agent._vendor.requests import Session as S, get\n",
            id="aliases",
        ),
        pytest.param(
            "from urllib3.exceptions import *\n",
            "from opentelemetry.agent._vendor.urllib3.exceptions import *\n",
            id="star",
        ),
        pytest.param(
            "from urllib3 import (  # comment\n    PoolManager,  # pool\n    Timeout,\n)\n",
            "from opentelemetry.agent._vendor.urllib3 import (  # comment\n    PoolManager,  # pool\n    Timeout,\n)\n",
            id="parenthesized-multiline",
        ),
        pytest.param(
            "def f():\n    from urllib3 import Timeout\n",
            "def f():\n    from opentelemetry.agent._vendor.urllib3 import Timeout\n",
            id="function",
        ),
        pytest.param(
            "try:\n    from urllib3 import a\nexcept ImportError:\n    pass\n",
            "try:\n    from opentelemetry.agent._vendor.urllib3 import a\nexcept ImportError:\n    pass\n",
            id="try",
        ),
        pytest.param(
            "if TYPE_CHECKING:\n    from requests import Session\n",
            "if TYPE_CHECKING:\n    from opentelemetry.agent._vendor.requests import Session\n",
            id="type-checking",
        ),
        pytest.param(
            "from os import path\nfrom urllib3 import a\n",
            "from os import path\nfrom opentelemetry.agent._vendor.urllib3 import a\n",
            id="mixed",
        ),
        pytest.param(
            "import urllib3\n",
            "from opentelemetry.agent._vendor import urllib3\n",
            id="import",
        ),
        pytest.param(
            "import urllib3 as u3\n",
            "from opentelemetry.agent._vendor import urllib3 as u3\n",
            id="import-as",
        ),
        pytest.param(
            "import urllib3.contrib.socks\n",
            "from opentelemetry.agent._vendor import urllib3\nimport opentelemetry.agent._vendor.urllib3.contrib.socks\n",
            id="import-submodule",
        ),
        pytest.param(
            "import urllib3.contrib.socks as socks\n",
            "from opentelemetry.agent._vendor.urllib3.contrib import socks as socks\n",
            id="import-submodule-as",
        ),
        pytest.param(
            "import urllib3, os\n",
            "from opentelemetry.agent._vendor import urllib3\nimport os\n",
            id="import-multiple",
        ),
        pytest.param(
            "import urllib3.util\nimport urllib3.exceptions\n",
            "from opentelemetry.agent._vendor import urllib3\n"
            "import opentelemetry.agent._vendor.urllib3.util\n"
            "from opentelemetry.agent._vendor import urllib3\n"
            "import opentelemetry.agent._vendor.urllib3.exceptions\n",
            id="import-submodules-repeat-binding",
        ),
        pytest.param(
            "def f():\n    import idna\n    return idna\n",
            "def f():\n    from opentelemetry.agent._vendor import idna\n    return idna\n",
            id="import-function",
        ),
        pytest.param(
            "def f():\n    try:\n        import idna\n    except ImportError:\n        pass\n",
            "def f():\n    try:\n        from opentelemetry.agent._vendor import idna\n    except ImportError:\n        pass\n",
            id="import-try",
        ),
        pytest.param(
            "try: import idna, urllib3.util\nexcept ImportError: pass\n",
            "try: from opentelemetry.agent._vendor import idna; from opentelemetry.agent._vendor import urllib3; "
            "import opentelemetry.agent._vendor.urllib3.util\nexcept ImportError: pass\n",
            id="import-one-line-suite",
        ),
        pytest.param(
            "import urllib3.util; x = 1\n",
            "from opentelemetry.agent._vendor import urllib3\nimport opentelemetry.agent._vendor.urllib3.util\nx = 1\n",
            id="import-semicolon-line-split",
        ),
        pytest.param(
            "x = 1\n\n# leading\nimport os, idna  # trailing\n",
            "x = 1\n\n# leading\nimport os\nfrom opentelemetry.agent._vendor import idna  # trailing\n",
            id="import-comments",
        ),
        pytest.param(
            "if True:\n    import urllib3.util  # trailing\n    y = 2\n",
            "if True:\n    from opentelemetry.agent._vendor import urllib3\n"
            "    import opentelemetry.agent._vendor.urllib3.util  # trailing\n    y = 2\n",
            id="import-indented-split",
        ),
    ],
)
def test_rewrite_source(source: str, expected: str) -> None:
    assert rewrite_source(source, NAMESPACE, NAMES) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("from . import util\n", id="relative-package"),
        pytest.param("from .urllib3 import a\n", id="relative-vendored-name"),
        pytest.param("from ..requests import a\n", id="relative-parent"),
        pytest.param("from os import path\n", id="unrelated"),
        pytest.param("from requestsx import a\n", id="prefix-collision"),
        pytest.param("from __future__ import annotations\n", id="future"),
        pytest.param("import os, sys\n", id="import-unrelated"),
        pytest.param("import requestsx\nimport requestsx.a\n", id="import-prefix-collision"),
        pytest.param("import opentelemetry.agent._vendor.urllib3.util\n", id="import-already-vendored"),
        pytest.param('"""\nimport urllib3\n"""\n# import urllib3\n', id="docstring-and-comment"),
        pytest.param("from opentelemetry.agent._vendor.urllib3 import a\n", id="already-vendored"),
    ],
)
def test_rewrite_source_unchanged(source: str) -> None:
    assert rewrite_source(source, NAMESPACE, NAMES) == source


def test_rewrite_imports(tmp_path: Path) -> None:
    (tmp_path / "urllib3" / "util").mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "urllib3" / "__init__.py").write_text("from .util import a\n")
    (tmp_path / "urllib3" / "util" / "retry.py").write_bytes(
        b"# -*- coding: latin-1 -*-\r\nfrom urllib3 import a\r\nfrom urllib3.exceptions import b\r\ns = '\xe9'\r\n"
    )
    (tmp_path / "requests.py").write_text("from urllib3 import c\n")
    (tmp_path / "notes.txt").write_text("from urllib3 import d\n")

    result = rewrite_imports(tmp_path, NAMESPACE, NAMES)

    assert result == RewriteResult(files=2, imports=3)
    assert (tmp_path / "urllib3" / "util" / "retry.py").read_bytes() == (
        b"# -*- coding: latin-1 -*-\r\n"
        b"from opentelemetry.agent._vendor.urllib3 import a\r\n"
        b"from opentelemetry.agent._vendor.urllib3.exceptions import b\r\n"
        b"s = '\xe9'\r\n"
    )
    assert (tmp_path / "requests.py").read_text() == "from opentelemetry.agent._vendor.urllib3 import c\n"
    assert (tmp_path / "urllib3" / "__init__.py").read_text() == "from .util import a\n"
    assert (tmp_path / "notes.txt").read_text() == "from urllib3 import d\n"


def test_rewrite_imports_leaves_unchanged_files_untouched(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("from os import path\n")
    mtime = path.stat().st_mtime_ns

    result = rewrite_imports(tmp_path, NAMESPACE, NAMES)

    assert result == RewriteResult(files=0, imports=0)
    assert path.stat().st_mtime_ns == mtime


def test_rewrite_imports_counts_module_names(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("import urllib3, idna, os\nfrom urllib3 import a, b\n")

    result = rewrite_imports(tmp_path, NAMESPACE, NAMES)

    assert result == RewriteResult(files=1, imports=3)


def test_rewrite_imports_reports_unparsable_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("from urllib3 import (\n")

    with pytest.raises(VendorError, match="cannot parse .*broken.py"):
        rewrite_imports(tmp_path, NAMESPACE, NAMES)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            'import logging\nlogger = logging.getLogger("urllib3")\n',
            'import logging\nlogger = logging.getLogger("opentelemetry.agent._vendor.urllib3")\n',
            id="get-logger",
        ),
        pytest.param(
            "import logging\nlogging.getLogger('idna.core').addHandler(h)\n",
            "import logging\nlogging.getLogger('opentelemetry.agent._vendor.idna.core').addHandler(h)\n",
            id="get-logger-submodule-quote-style",
        ),
        pytest.param(
            'from logging import getLogger as gl\ngl("requests", x)\n',
            'from logging import getLogger as gl\ngl("opentelemetry.agent._vendor.requests", x)\n',
            id="get-logger-alias",
        ),
        pytest.param(
            'def f(name: str = "urllib3", level=1):\n    pass\n',
            'def f(name: str = "opentelemetry.agent._vendor.urllib3", level=1):\n    pass\n',
            id="parameter-default",
        ),
    ],
)
def test_rewrite_source_logger_names(source: str, expected: str) -> None:
    assert rewrite_source(source, NAMESPACE, NAMES) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("import logging\nlogging.getLogger(__name__)\n", id="dunder-name"),
        pytest.param('import logging\nlogging.getLogger("urllib3x")\n', id="prefix-collision"),
        pytest.param('import logging\nlogging.getLogger("urllib3 pool")\n', id="not-a-dotted-name"),
        pytest.param('import logging\nlogging.getLogger(b"urllib3")\n', id="bytes"),
        pytest.param('import logging\nlogging.getLogger(name="urllib3")\n', id="keyword"),
        pytest.param('getLogger("urllib3")\n', id="get-logger-not-imported"),
        pytest.param('print("urllib3")\nx = {"urllib3": 1}\n', id="other-strings"),
        pytest.param('def f(x="urllib3 is great"):\n    pass\n', id="parameter-default-sentence"),
        pytest.param('"""urllib3 docs"""\n', id="docstring"),
    ],
)
def test_rewrite_source_logger_names_unchanged(source: str) -> None:
    assert rewrite_source(source, NAMESPACE, NAMES) == source


def test_rewrite_imports_counts_logger_names(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        'import logging\nimport urllib3\nlogging.getLogger("urllib3")\ndef f(name="idna"): pass\n'
    )
    (tmp_path / "loggers_only.py").write_text('import logging\nlogging.getLogger("requests")\n')

    result = rewrite_imports(tmp_path, NAMESPACE, NAMES)

    assert result == RewriteResult(files=2, imports=1, loggers=3)


PB2_HEADER = "from google.protobuf.internal import builder as _builder\n"


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        pytest.param(
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'google.protobuf.any_pb2', _globals)",
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'opentelemetry.agent._vendor.google.protobuf.any_pb2', _globals)",
            id="generated-module-name",
        ),
        pytest.param(
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'my_protos.trace_pb2', _globals)",
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'my_protos.trace_pb2', _globals)",
            id="non-vendored-module",
        ),
        pytest.param(
            "_builder.BuildTopDescriptorsAndMessages('google.protobuf', DESCRIPTOR, _globals)",
            "_builder.BuildTopDescriptorsAndMessages('google.protobuf', DESCRIPTOR, _globals)",
            id="first-argument",
        ),
        pytest.param(
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, module_name, _globals)",
            "_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, module_name, _globals)",
            id="variable",
        ),
    ],
)
def test_rewrite_source_protobuf_module_names(call: str, expected: str) -> None:
    names = NAMES | {"google"}
    expected_header = "from opentelemetry.agent._vendor.google.protobuf.internal import builder as _builder\n"

    assert rewrite_source(f"{PB2_HEADER}{call}\n", NAMESPACE, names) == f"{expected_header}{expected}\n"


def test_rewrite_source_protobuf_builder_not_imported() -> None:
    source = "def BuildTopDescriptorsAndMessages(*args): pass\nBuildTopDescriptorsAndMessages(D, 'google.x_pb2', g)\n"

    assert rewrite_source(source, NAMESPACE, NAMES | {"google"}) == source


def test_rewrite_imports_counts_protobuf_module_names(tmp_path: Path) -> None:
    (tmp_path / "any_pb2.py").write_text(
        f"{PB2_HEADER}_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'google.protobuf.any_pb2', _globals)\n"
    )

    result = rewrite_imports(tmp_path, NAMESPACE, NAMES | {"google"})

    assert result == RewriteResult(files=1, imports=1, modules=1)
