#FROM gcr.io/google.com/cloudsdktool/cloud-sdk:slim
FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:slim
#FROM python:3.9-slim

COPY .  /usr/src/app/openrelation-elections
WORKDIR  /usr/src/app/openrelation-elections

ENV MNT_DIR /usr/src/app/gcs
RUN addgroup user && adduser -h /home/user -D user -G user -s /bin/sh

RUN apt-get update \
    && apt-get install -y gcc libc-dev libxslt-dev libxml2 libpq-dev \
    && pip install --upgrade pip \
    && pip install -r requirements.txt

EXPOSE 8080
CMD ["/usr/local/bin/uwsgi", "--ini", "server.ini"]
