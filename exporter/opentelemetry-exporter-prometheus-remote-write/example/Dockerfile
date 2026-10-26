FROM python:3.10@sha256:c10791e6f69086d5216f7b5d3b839929c454e24305867ed9bc5152f0355b5423

RUN apt-get update -y && apt-get install libsnappy-dev -y

WORKDIR /code
COPY . .

RUN pip install --no-deps -e .
RUN pip install --require-hashes -r ./example/requirements.txt

CMD ["python", "./example/sampleapp.py"]
