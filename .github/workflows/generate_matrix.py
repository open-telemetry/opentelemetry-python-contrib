from json import dumps

# matrix_values = [{"os": "ubuntu-latest"}]
python_versions = ["py38", "py312"]

# print(f"name=matrix::{dumps(matrix_values)}")
print(f"::set-output name=python_versions::{dumps(python_versions)}")
