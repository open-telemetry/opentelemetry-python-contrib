from json import dumps

# matrix_values = [{"os": "ubuntu-latest"}]
matrix_values = [{"os": ["ubuntu-latest", "windows-2019"]}]

# print(f"name=matrix::{dumps(matrix_values)}")
print(f"::set-output name=matrix::{dumps(matrix_values)}")
