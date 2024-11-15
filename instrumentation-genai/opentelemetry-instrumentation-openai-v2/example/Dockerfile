# Use an alpine image to make the runtime smaller
FROM docker.io/python:3.12.7-alpine3.20
RUN python -m pip install --upgrade pip

COPY /requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY main.py /

CMD [ "opentelemetry-instrument", "python", "main.py" ]
