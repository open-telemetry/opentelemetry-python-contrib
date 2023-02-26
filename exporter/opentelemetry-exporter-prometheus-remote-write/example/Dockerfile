FROM python:3.8

RUN apt-get update -y && apt-get install libsnappy-dev -y

WORKDIR /code
COPY . .

RUN pip install -e .
RUN pip install -r ./example/requirements.txt

CMD ["python", "./example/sampleapp.py"]
