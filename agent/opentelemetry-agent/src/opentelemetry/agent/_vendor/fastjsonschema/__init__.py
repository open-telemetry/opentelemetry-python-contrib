#    ___
#    \./     DANGER: This project implements some code generation
# .--.O.--.          techniques involving string concatenation.
#  \/   \/           If you look at it, you might die.
#

r"""
Installation
************

.. code-block:: bash

    pip install fastjsonschema

Support only for Python 3.3 and higher.

About
*****

``fastjsonschema`` implements validation of JSON documents by JSON schema.
The library implements JSON schema drafts 04, 06, and 07. The main purpose is
to have a really fast implementation. See some numbers:

 * Probably the most popular, ``jsonschema``, can take up to 5 seconds for valid
   inputs and 1.2 seconds for invalid inputs.
 * Second most popular, ``json-spec``, is even worse with up to 7.2 and 1.7 seconds.
 * Last ``validictory``, now deprecated, is much better with 370 or 23 milliseconds,
   but it does not follow all standards, and it can be still slow for some purposes.

With this library you can gain big improvements as ``fastjsonschema`` takes
only about 25 milliseconds for valid inputs and 2 milliseconds for invalid ones.
Pretty amazing, right? :-)

Technically it works by generating the most stupid code on the fly, which is fast but
is hard to write by hand. The best efficiency is achieved when a validator is compiled
once and used many times, of course. It works similarly like regular expressions. But
you can also generate the code to a file, which is even slightly faster.

You can run the performance benchmarks on your computer or server with the included
script:

.. code-block:: bash

    $ make performance
    fast_compiled                  valid      ==>  0.0993900
    fast_compiled                  invalid    ==>  0.0041089
    fast_compiled_without_exc      valid      ==>  0.0465258
    fast_compiled_without_exc      invalid    ==>  0.0023688
    fast_file                      valid      ==>  0.0989483
    fast_file                      invalid    ==>  0.0041104
    fast_not_compiled              valid      ==> 11.9572681
    fast_not_compiled              invalid    ==>  2.9512092
    jsonschema                     valid      ==>  5.2233240
    jsonschema                     invalid    ==>  1.3227916
    jsonschema_compiled            valid      ==>  0.4447982
    jsonschema_compiled            invalid    ==>  0.0231333
    jsonspec                       valid      ==>  4.1450569
    jsonspec                       invalid    ==>  1.0485777
    validictory                    valid      ==>  0.2730411
    validictory                    invalid    ==>  0.0183669

This library follows and implements `JSON schema draft-04, draft-06, and draft-07
<http://json-schema.org>`_. Sometimes it's not perfectly clear, so I recommend also
check out this `understanding JSON schema <https://spacetelescope.github.io/understanding-json-schema>`_.

Note that there are some differences compared to JSON schema standard:

 * Regular expressions are full Python ones, not only what JSON schema allows. It's easier
   to allow everything, and also it's faster to compile without limits. So keep in mind that when
   you will use a more advanced regular expression, it may not work with other libraries or in
   other languages.
 * Because Python matches new line for a dollar in regular expressions (``a$`` matches ``a`` and ``a\\n``),
   instead of ``$`` is used ``\Z`` and all dollars in your regular expression are changed to ``\\Z``
   as well. When you want to use dollar as regular character, you have to escape it (``\$``).
 * JSON schema says you can use keyword ``default`` for providing default values. This implementation
   uses that and always returns transformed input data.

Usage
*****

.. code-block:: python

    import fastjsonschema

    point_schema = {
        "type": "object",
        "properties": {
            "x": {
                "type": "number",
            },
            "y": {
                "type": "number",
            },
        },
        "required": ["x", "y"],
        "additionalProperties": False,
    }

    point_validator = fastjsonschema.compile(point_schema)
    try:
        point_validator({"x": 1.0, "y": 2.0})
    except fastjsonschema.JsonSchemaException as e:
        print(f"Data failed validation: {e}")

API
***
"""
from collections.abc import Callable, Mapping
from functools import partial, update_wrapper
from typing import Any

from .draft04 import CodeGeneratorDraft04
from .draft06 import CodeGeneratorDraft06
from .draft07 import CodeGeneratorDraft07
from .draft2019 import CodeGeneratorDraft2019
from .exceptions import (
    JsonSchemaException,
    JsonSchemaValueException,
    JsonSchemaValuesException,
    JsonSchemaDefinitionException,
)
from .ref_resolver import RefResolver
from .version import VERSION

__all__ = (
    'VERSION',
    'JsonSchemaException',
    'JsonSchemaValueException',
    'JsonSchemaValuesException',
    'JsonSchemaDefinitionException',
    'validate',
    'compile',
    'compile_to_code',
)


Definition = dict[str, Any] | bool
Handlers = Mapping[str, Callable[[str], Any]]
Formats = Mapping[str, str | Callable[[Any], bool]]
Validator = Callable[..., Any]


def validate(
    definition: Definition,
    data: Any,
    handlers: Handlers = {},
    formats: Formats = {},
    use_default: bool = True,
    use_formats: bool = True,
    detailed_exceptions: bool = True,
    fast_fail: bool = True,
) -> Any:
    """
    Validation function for lazy programmers or for use cases when you need
    to call validation only once, so you do not have to compile it first.
    Use it only when you do not care about performance (even though it will
    be still faster than alternative implementations).

    .. code-block:: python

        import fastjsonschema

        fastjsonschema.validate({'type': 'string'}, 'hello')
        # same as: compile({'type': 'string'})('hello')

    Preferred is to use :any:`compile` function.

    The ``handlers`` parameter controls resolution of remote ``$ref`` URIs; see
    :any:`compile` for details and security considerations when schemas are not
    fully trusted.
    """
    return compile(definition, handlers, formats, use_default, use_formats, detailed_exceptions, fast_fail)(data)


#TODO: Change use_default to False when upgrading to version 3.
# pylint: disable=redefined-builtin,dangerous-default-value,exec-used
def compile(
    definition: Definition,
    handlers: Handlers = {},
    formats: Formats = {},
    use_default: bool = True,
    use_formats: bool = True,
    detailed_exceptions: bool = True,
    fast_fail: bool = True,
) -> Validator:
    """
    Generates validation function for validating JSON schema passed in ``definition``.
    Example:

    .. code-block:: python

        import fastjsonschema

        validate = fastjsonschema.compile({'type': 'string'})
        validate('hello')

    This implementation supports keyword ``default`` (can be turned off
    by passing `use_default=False`):

    .. code-block:: python

        validate = fastjsonschema.compile({
            'type': 'object',
            'properties': {
                'a': {'type': 'number', 'default': 42},
            },
        })

        data = validate({})
        assert data == {'a': 42}

    Supported implementations are draft-04, draft-06 and draft-07. Which version
    should be used is determined by `$draft` in your ``definition``. When not
    specified, the latest implementation is used (draft-07).

    .. code-block:: python

        validate = fastjsonschema.compile({
            '$schema': 'http://json-schema.org/draft-04/schema',
            'type': 'number',
        })

    You can pass mapping from URI scheme to function that should be used to
    retrieve remote references used in your ``definition`` in parameter
    ``handlers``. When no handler is registered for a scheme, the URI is
    fetched automatically via :mod:`urllib` (for example ``http``, ``https``,
    or ``file`` URLs).

    .. warning::

        Do not compile or validate untrusted schemas without custom
        ``handlers``. A schema containing ``$ref`` can trigger outbound HTTP
        requests to arbitrary URLs, including internal or loopback addresses
        (server-side request forgery). Provide ``handlers`` to restrict which
        URIs are resolved, or pre-resolve references before passing the schema
        to this library.

    .. code-block:: python

        def http_handler(uri):
            if not uri.startswith('https://schemas.example.com/'):
                raise ValueError('ref not allowed')
            import urllib.request
            with urllib.request.urlopen(uri) as response:
                return json.loads(response.read())

        validate = fastjsonschema.compile(definition, handlers={
            'http': http_handler,
            'https': http_handler,
        })

    Also, you can pass mapping for custom formats. Key is the name of your
    formatter and value can be regular expression, which will be compiled or
    callback returning `bool` (or you can raise your own exception).

    .. code-block:: python

        validate = fastjsonschema.compile(definition, formats={
            'foo': r'foo|bar',
            'bar': lambda value: value in ('foo', 'bar'),
        })

    Note that formats are automatically used as assertions. It can be turned
    off by passing `use_formats=False`. When disabled, custom formats are
    disabled as well. (Added in 2.19.0.)

    If you don't need detailed exceptions, you can turn the details off and gain
    additional performance by passing `detailed_exceptions=False`.

    By default, the execution stops with the first validation error. If you need
    to collect all the errors, turn this off by passing `fast_fail=False`.

    Exception :any:`JsonSchemaDefinitionException` is raised when generating the
    code fails (bad definition).

    Exception :any:`JsonSchemaValueException` is raised from generated function when
    validation fails (data do not follow the definition).

    Exception :any:`JsonSchemaValuesException` is raised from generated function when
    validation fails (data do not follow the definition) contatining all the errors
    (when fast_fail is set to `False`).
    """
    resolver, code_generator = _factory(
        definition,
        handlers,
        formats,
        use_default,
        use_formats,
        detailed_exceptions,
        fast_fail,
    )
    global_state = code_generator.global_state
    # Do not pass local state so it can recursively call itself.
    exec(code_generator.func_code, global_state)
    func = global_state[resolver.get_scope_name()]
    if formats:
        return update_wrapper(partial(func, custom_formats=formats), func)
    return func


# pylint: disable=dangerous-default-value
def compile_to_code(
    definition: Definition,
    handlers: Handlers = {},
    formats: Formats = {},
    use_default: bool = True,
    use_formats: bool = True,
    detailed_exceptions: bool = True,
    fast_fail: bool = True,
) -> str:
    """
    Generates validation code for validating JSON schema passed in ``definition``.
    Example:

    .. code-block:: python

        import fastjsonschema

        code = fastjsonschema.compile_to_code({'type': 'string'})
        with open('your_file.py', 'w') as f:
            f.write(code)

    You can also use it as a script:

    .. code-block:: bash

        echo "{'type': 'string'}" | python3 -m fastjsonschema > your_file.py
        python3 -m fastjsonschema "{'type': 'string'}" > your_file.py

    Exception :any:`JsonSchemaDefinitionException` is raised when generating the
    code fails (bad definition).

    Remote ``$ref`` URIs are resolved the same way as in :any:`compile`; see its
    documentation for ``handlers`` and security considerations.
    """
    _, code_generator = _factory(
        definition,
        handlers,
        formats,
        use_default,
        use_formats,
        detailed_exceptions,
        fast_fail,
    )
    return (
        'VERSION = "' + VERSION + '"\n' +
        code_generator.global_state_code + '\n' +
        code_generator.func_code
    )


def _factory(
    definition: Definition,
    handlers: Handlers,
    formats: Formats = {},
    use_default: bool = True,
    use_formats: bool = True,
    detailed_exceptions: bool = True,
    fast_fail: bool = True,
) -> tuple[RefResolver, CodeGeneratorDraft04]:
    resolver = RefResolver.from_schema(definition, handlers=handlers, store={})
    code_generator = _get_code_generator_class(definition)(
        definition,
        resolver=resolver,
        formats=formats,
        use_default=use_default,
        use_formats=use_formats,
        detailed_exceptions=detailed_exceptions,
        fast_fail=fast_fail,
    )
    return resolver, code_generator


def _get_code_generator_class(schema: Definition) -> type[CodeGeneratorDraft04]:
    # Schema in from draft-06 can be just the boolean value.
    if isinstance(schema, dict):
        schema_version = schema.get('$schema', '')
        if 'draft-04' in schema_version:
            return CodeGeneratorDraft04
        if 'draft-06' in schema_version:
            return CodeGeneratorDraft06
        if 'draft-07' in schema_version:
            return CodeGeneratorDraft07
        if 'draft/2019' in schema_version or 'draft-2019' in schema_version:
            return CodeGeneratorDraft2019
    return CodeGeneratorDraft2019
