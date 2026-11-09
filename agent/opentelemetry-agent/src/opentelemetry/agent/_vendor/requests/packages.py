# The upstream module imports urllib3, idna and chardet by their top-level names and
# registers them as `requests.packages.*` in the global sys.modules. In the vendored copy
# that would load (and alias) the application's own packages, so the backwards
# compatibility aliases are disabled.
