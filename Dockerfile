FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RSCRIPT_BIN=Rscript

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gfortran \
        libcurl4-openssl-dev \
        libfontconfig1-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libgdal-dev \
        libgeos-dev \
        libharfbuzz-dev \
        libjpeg-dev \
        libpng-dev \
        libpq-dev \
        libproj-dev \
        libssl-dev \
        libtiff-dev \
        libxml2-dev \
        r-base \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        tesseract-ocr-ita \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

RUN Rscript -e "install.packages(c('jsonlite', 'r3PG'), repos='https://cloud.r-project.org')"

COPY . .

EXPOSE 8005

CMD ["sh", "scripts/docker_start.sh"]
