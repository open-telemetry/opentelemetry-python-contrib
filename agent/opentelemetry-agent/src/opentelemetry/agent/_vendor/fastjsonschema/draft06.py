import decimal
from .draft04 import CodeGeneratorDraft04, JSON_TYPE_TO_PYTHON_TYPE
from .exceptions import JsonSchemaDefinitionException
from .generator import VALIDATION_EXCEPTIONS, enforce_list


class CodeGeneratorDraft06(CodeGeneratorDraft04):
    FORMAT_REGEXS = dict(CodeGeneratorDraft04.FORMAT_REGEXS, **{
        'json-pointer': r'^(/(([^/~])|(~[01]))*)*\Z',
        'uri-reference': r'^(\w+:(\/?\/?))?[^#\\\s]*(#[^\\\s]*)?\Z',
        'uri-template': (
            r'^(?:(?:[^\x00-\x20\"\'<>%\\^`{|}]|%[0-9a-f]{2})|'
            r'\{[+#./;?&=,!@|]?(?:[a-z0-9_]|%[0-9a-f]{2})+'
            r'(?::[1-9][0-9]{0,3}|\*)?(?:,(?:[a-z0-9_]|%[0-9a-f]{2})+'
            r'(?::[1-9][0-9]{0,3}|\*)?)*\})*\Z'
        ),
    })

    def __init__(
        self,
        definition,
        resolver=None,
        formats={},
        use_default=True,
        use_formats=True,
        detailed_exceptions=True,
        fast_fail=True,
    ):
        super().__init__(definition, resolver, formats, use_default, use_formats, detailed_exceptions, fast_fail)
        self._json_keywords_to_function.update((
            ('exclusiveMinimum', self.generate_exclusive_minimum),
            ('exclusiveMaximum', self.generate_exclusive_maximum),
            ('propertyNames', self.generate_property_names),
            ('contains', self.generate_contains),
            ('const', self.generate_const),
        ))

    def _generate_func_code_block(self, definition):
        if isinstance(definition, bool):
            return self.generate_boolean_schema()
        elif '$ref' in definition:
            # needed because ref overrides any sibling keywords
            return self.generate_ref()
        return self.run_generate_functions(definition)

    def generate_boolean_schema(self):
        """
        Means that schema can be specified by boolean.
        True means everything is valid, False everything is invalid.
        """
        if self._definition is True:
            self.l('pass')
        if self._definition is False:
            self.exc('{name} must not be there')

    def generate_type(self):
        """
        Validation of type. Can be one type or list of types.

        Since draft 06 a float without fractional part is an integer.

        .. code-block:: python

            {'type': 'string'}
            {'type': ['string', 'number']}
        """
        types = enforce_list(self._definition['type'])
        try:
            python_types = ', '.join(JSON_TYPE_TO_PYTHON_TYPE[t] for t in types)
        except KeyError as exc:
            raise JsonSchemaDefinitionException('Unknown type') from exc

        extra = ''

        if 'integer' in types:
            extra += ' and not (isinstance({variable}, float) and {variable}.is_integer())'.format(
                variable=self._variable,
            )

        if ('number' in types or 'integer' in types) and 'boolean' not in types:
            extra += ' or isinstance({variable}, bool)'.format(variable=self._variable)

        with self.l('if not isinstance({variable}, ({})){}:', python_types, extra):
            self.exc('{name} must be {}', ' or '.join(types), rule='type')

    def generate_minimum(self):
        """
        Since draft 06 exclusiveMinimum is a number validated on its own,
        so minimum is always inclusive.
        """
        with self.l('if isinstance({variable}, (int, float, Decimal)) and not isinstance({variable}, bool):'):
            if not isinstance(self._definition['minimum'], (int, float, decimal.Decimal)):
                raise JsonSchemaDefinitionException('minimum must be a number')
            with self.l('if {variable} < {minimum}:'):
                self.exc('{name} must be bigger than or equal to {minimum}', rule='minimum')

    def generate_maximum(self):
        """
        Since draft 06 exclusiveMaximum is a number validated on its own,
        so maximum is always inclusive.
        """
        with self.l('if isinstance({variable}, (int, float, Decimal)) and not isinstance({variable}, bool):'):
            if not isinstance(self._definition['maximum'], (int, float, decimal.Decimal)):
                raise JsonSchemaDefinitionException('maximum must be a number')
            with self.l('if {variable} > {maximum}:'):
                self.exc('{name} must be smaller than or equal to {maximum}', rule='maximum')

    def generate_exclusive_minimum(self):
        with self.l('if isinstance({variable}, (int, float, Decimal)) and not isinstance({variable}, bool):'):
            if not isinstance(self._definition['exclusiveMinimum'], (int, float, decimal.Decimal)):
                raise JsonSchemaDefinitionException('exclusiveMinimum must be an integer, a float or a decimal')
            with self.l('if {variable} <= {exclusiveMinimum}:'):
                self.exc('{name} must be bigger than {exclusiveMinimum}', rule='exclusiveMinimum')

    def generate_exclusive_maximum(self):
        with self.l('if isinstance({variable}, (int, float, Decimal)) and not isinstance({variable}, bool):'):
            if not isinstance(self._definition['exclusiveMaximum'], (int, float, decimal.Decimal)):
                raise JsonSchemaDefinitionException('exclusiveMaximum must be an integer, a float or a decimal')
            with self.l('if {variable} >= {exclusiveMaximum}:'):
                self.exc('{name} must be smaller than {exclusiveMaximum}', rule='exclusiveMaximum')

    def generate_property_names(self):
        """
        Means that keys of object must to follow this definition.

        .. code-block:: python

            {
                'propertyNames': {
                    'maxLength': 3,
                },
            }

        Valid keys of object for this definition are foo, bar, ... but not foobar for example.
        """
        property_names_definition = self._definition.get('propertyNames', {})
        if property_names_definition is True:
            pass
        elif property_names_definition is False:
            self.create_variable_is_dict()
            with self.l('if {variable}_is_dict and {variable}:'):
                self.exc('{name} must not be there', rule='propertyNames')
        else:
            self.create_variable_is_dict()
            with self.l('if {variable}_is_dict:'):
                self.create_variable_with_length()
                with self.l('if {variable}_len != 0:'):
                    self.l('{variable}_property_names = True')
                    with self.l('for {variable}_key in {variable}:'):
                        with self.l('try:'):
                            code_len = len(self._code)
                            with self.trial_validation():
                                self.generate_func_code_block(
                                    property_names_definition,
                                    '{}_key'.format(self._variable),
                                    self._variable_name,
                                    clear_variables=True,
                                )
                            if len(self._code) == code_len:
                                self.l('pass')
                        with self.l('except {}:', VALIDATION_EXCEPTIONS):
                            self.l('{variable}_property_names = False')
                    with self.l('if not {variable}_property_names:'):
                        self.exc('{name} must be named by propertyName definition', rule='propertyNames')

    def generate_contains(self):
        """
        Means that array must contain at least one defined item.

        .. code-block:: python

            {
                'contains': {
                    'type': 'number',
                },
            }

        Valid array is any with at least one number.
        """
        self.create_variable_is_list()
        with self.l('if {variable}_is_list:'):
            contains_definition = self._definition['contains']

            if contains_definition is False:
                self.exc('{name} is always invalid', rule='contains')
            elif contains_definition is True:
                with self.l('if not {variable}:'):
                    self.exc('{name} must not be empty', rule='contains')
            else:
                self.l('{variable}_contains = False')
                with self.l('for {variable}_key in {variable}:'):
                    with self.l('try:'):
                        with self.trial_validation():
                            self.generate_func_code_block(
                                contains_definition,
                                '{}_key'.format(self._variable),
                                self._variable_name,
                                clear_variables=True,
                            )
                        self.l('{variable}_contains = True')
                        self.l('break')
                    self.l('except {}: pass', VALIDATION_EXCEPTIONS)

                with self.l('if not {variable}_contains:'):
                    self.exc('{name} must contain one of contains definition', rule='contains')

    def generate_const(self):
        """
        Means that value is valid when is equeal to const definition.

        .. code-block:: python

            {
                'const': 42,
            }

        Only valid value is 42 in this example.
        """
        const = self._definition['const']
        match = self._enum_value_matches(self._variable, const)
        with self.l('if not ({}):', match):
            self.exc('{name} must be same as const definition: {definition_rule}', rule='const')
