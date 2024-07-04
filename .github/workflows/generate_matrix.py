from json import dumps

matrix_values = [{"os": "sdfadsf"}]

print(f"::set-output name=matrix::{dumps(matrix_values)}")
