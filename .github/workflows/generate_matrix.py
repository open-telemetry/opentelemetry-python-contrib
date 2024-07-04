from json import dumps

matrix_values = [{"os": "ubuntu-latest"}]

print(f"name=matrix::{dumps(matrix_values)}")
