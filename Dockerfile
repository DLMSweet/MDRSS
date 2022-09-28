FROM python:3.9.14-alpine3.15
WORKDIR /code
COPY requirements.txt /code
RUN apk add --update --no-cache --virtual .build-deps \
        libxml2 \
        g++ \
        libxml2-dev && \
    apk add libxslt-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del .build-deps
COPY . /code
CMD ["hypercorn", "md_rss:app", "-b", "0.0.0.0", "-w", "8", "--access-logfile", "-"]
