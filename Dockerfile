FROM gcr.io/google.com/cloudsdktool/cloud-sdk:560.0.0-slim

WORKDIR /usr/src/app/openrelation-elections

ENV MNT_DIR /usr/src/app/gcs
RUN addgroup user && adduser -h /home/user -D user -G user -s /bin/sh

# 先裝系統套件和 Python
COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y gcc libc-dev libxslt-dev libxml2 libpq-dev libsqlite3-dev python3.11-venv \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["/opt/venv/bin/uwsgi", "--ini", "server.ini"]
