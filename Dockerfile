FROM python:3.11.1-slim AS builder
ADD . /app
WORKDIR /app
RUN apt-get update && apt-get -y dist-upgrade
RUN apt-get install -y curl gnupg software-properties-common lsb-release git
RUN curl -fsSL https://apt.releases.hashicorp.com/gpg | apt-key add -
RUN apt-add-repository "deb [arch=$(dpkg --print-architecture)] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
RUN apt-get update
RUN apt-get install -y bash terraform

RUN pip install -r requirements.txt

CMD ["/usr/local/bin/python", "/app/src/terraform_runner.py"]