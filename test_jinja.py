from jinja2 import Environment

template = """      package:
        type: choice
        options:
{% for option in release_options %}
        - {{ option }}
{% endfor %}
{% raw %}        description: 'Package to be released'
{% endraw %}
"""
env = Environment(trim_blocks=True, lstrip_blocks=True)
print(repr(env.from_string(template).render(release_options=["a", "b"])))
