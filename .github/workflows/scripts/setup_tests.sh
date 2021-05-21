# TESTS="$(python ./scripts/eachdist.py list --instrumentation)"
TESTS="$(ls instrumentation/)"

TESTS=(${TESTS//|/ })
#MATRIX="[{\"test\":\"exporter\"},{\"test\":\"sdkextension\"},{\"test\":\"propagator\"}"
MATRIX="[\"exporter\",\"sdkextension\",\"propagator\""
curr=""
for i in "${!TESTS[@]}"; do
    curr="${cut -d'-' -f2- <<<TESTS[$i]}"
    MATRIX+=",\"$curr\""
done
#MATRIX+="]}"
MATRIX+="]"
echo "::set-output name=matrix::$MATRIX"