# pylint: disable=import-outside-toplevel

"""
JSON Schema URI resolution scopes and dereferencing

https://tools.ietf.org/id/draft-zyp-json-schema-04.html#rfc.section.7

Code adapted from https://github.com/Julian/jsonschema
"""

import contextlib
import json
import re
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import Any
from urllib import parse as urlparse
from urllib.parse import unquote

from .exceptions import JsonSchemaDefinitionException

MAX_SCHEMA_WALK_DEPTH = min(500, sys.getrecursionlimit() // 2)


def get_id(schema: dict[str, Any]) -> str:
    """
    Originally ID was `id` and since v7 it's `$id`.
    """
    return schema.get('$id', schema.get('id', ''))


def resolve_path(schema: Any, fragment: str) -> Any:
    """
    Return definition from path.

    Path is unescaped according https://tools.ietf.org/html/rfc6901
    """
    fragment = fragment.lstrip('/')
    parts = unquote(fragment).split('/') if fragment else []
    for part in parts:
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(schema, list):
            schema = schema[int(part)]
        elif part in schema:
            schema = schema[part]
        else:
            raise JsonSchemaDefinitionException('Unresolvable ref: {}'.format(part))
    return schema


def normalize(uri: str) -> str:
    return urlparse.urlsplit(uri).geturl()


def resolve_remote(uri: str, handlers: Mapping[str, Callable[[str], Any]]) -> Any:
    """
    Resolve a remote ``uri``.

    .. note::

        urllib library is used to fetch requests from the remote ``uri``
        if handlers does notdefine otherwise.
    """
    scheme = urlparse.urlsplit(uri).scheme
    if scheme in handlers:
        result = handlers[scheme](uri)
    else:
        from urllib.request import urlopen

        with urlopen(uri) as response:
            encoding = response.info().get_content_charset() or 'utf-8'
            try:
                result = json.loads(response.read().decode(encoding),)
            except ValueError as exc:
                raise JsonSchemaDefinitionException('{} failed to decode'.format(uri)) from exc
    return result


class RefResolver:
    """
    Resolve JSON References.
    """

    # pylint: disable=dangerous-default-value,too-many-arguments
    def __init__(
        self,
        base_uri: str,
        schema: dict[str, Any] | bool,
        store: dict[str, Any] = {},
        cache: bool = True,
        handlers: Mapping[str, Callable[[str], Any]] = {},
    ) -> None:
        """
        `base_uri` is URI of the referring document from the `schema`.
        `store` is an dictionary that will be used to cache the fetched schemas
        (if `cache=True`).

        Please notice that you can have caching problems when compiling schemas
        with colliding `$ref`. To force overwriting use `cache=False` or
        explicitly pass the `store` argument (with a brand new dictionary)
        """
        self.base_uri = base_uri
        self.resolution_scope = base_uri
        self.schema = schema
        self.store = store
        self.cache = cache
        self.handlers = handlers
        self._walked_uris: set[str] = set()
        self.walk(schema)
        self._walked_uris.add(normalize(base_uri) if base_uri else '')

    @classmethod
    def from_schema(
        cls,
        schema: dict[str, Any] | bool,
        handlers: Mapping[str, Callable[[str], Any]] = {},
        **kwargs: Any,
    ) -> 'RefResolver':
        """
        Construct a resolver from a JSON schema object.
        """
        return cls(
            get_id(schema) if isinstance(schema, dict) else '',
            schema,
            handlers=handlers,
            **kwargs
        )

    @contextlib.contextmanager
    def in_scope(self, scope: str) -> Iterator[None]:
        """
        Context manager to handle current scope.
        """
        old_scope = self.resolution_scope
        self.resolution_scope = urlparse.urljoin(old_scope, scope)
        try:
            yield
        finally:
            self.resolution_scope = old_scope

    @contextlib.contextmanager
    def resolving(self, ref: str) -> Iterator[Any]:
        """
        Context manager which resolves a JSON ``ref`` and enters the
        resolution scope of this ref.
        """
        new_uri = urlparse.urljoin(self.resolution_scope, ref)
        uri, fragment = urlparse.urldefrag(new_uri)

        document_uri = uri or self.base_uri

        if uri and normalize(uri) in self.store:
            schema = self.store[normalize(uri)]
        elif not uri or uri == self.base_uri:
            schema = self.schema
        else:
            schema = resolve_remote(uri, self.handlers)
            if self.cache:
                self.store[normalize(uri)] = schema

        old_base_uri, old_schema = self.base_uri, self.schema
        self.base_uri, self.schema = document_uri, schema
        try:
            with self.in_scope(document_uri):
                self._ensure_walked(document_uri, schema)
                if fragment and not fragment.startswith('/'):
                    plain_name = normalize(urlparse.urljoin(document_uri, '#' + fragment))
                    if plain_name in self.store:
                        yield self.store[plain_name]
                        return
                    raise JsonSchemaDefinitionException('Unresolvable ref: {}'.format(fragment))
                yield resolve_path(schema, fragment)
        finally:
            self.base_uri, self.schema = old_base_uri, old_schema

    def _ensure_walked(self, uri: str, schema: Any) -> None:
        normalized = normalize(uri) if uri else ''
        if normalized in self._walked_uris:
            return
        self.walk(schema, rewrite_refs=False)
        self._walked_uris.add(normalized)

    def get_uri(self) -> str:
        return normalize(self.resolution_scope)

    def get_scope_name(self) -> str:
        """
        Get current scope and return it as a valid function name.
        """
        name = 'validate_' + unquote(self.resolution_scope).replace('~1', '_').replace('~0', '_').replace('"', '')
        name = re.sub(r'($[^a-zA-Z]|[^a-zA-Z0-9])', '_', name)
        name = name.lower().rstrip('_')
        return name

    def walk(self, node: dict[str, Any] | bool, depth: int = 0, rewrite_refs: bool = True) -> None:
        """
        Walk thru schema and dereferencing ``id`` and ``$ref`` instances
        """
        if depth >= MAX_SCHEMA_WALK_DEPTH:
            raise JsonSchemaDefinitionException(
                'Schema is too deeply nested (maximum depth is {})'.format(MAX_SCHEMA_WALK_DEPTH)
            )

        if isinstance(node, bool):
            pass
        elif '$ref' in node and isinstance(node['$ref'], str):
            if rewrite_refs:
                ref = node['$ref']
                node['$ref'] = urlparse.urljoin(self.resolution_scope, ref)
        elif ('$id' in node or 'id' in node) and isinstance(get_id(node), str):
            with self.in_scope(get_id(node)):
                self.store[normalize(self.resolution_scope)] = node
                for _, item in node.items():
                    if isinstance(item, dict):
                        self.walk(item, depth + 1, rewrite_refs)
        else:
            for _, item in node.items():
                if isinstance(item, dict):
                    self.walk(item, depth + 1, rewrite_refs)
