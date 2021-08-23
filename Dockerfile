FROM python:3.9.6-slim AS builder
ADD . /app
WORKDIR /app
RUN apt-get update && apt-get -y dist-upgrade
RUN apt-get install -y bash

RUN pip install -r requirements.txt

CMD ["/usr/local/bin/python", "/app/src/terraform_runner.py"]