FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FAIGATE_DB_PATH=/var/lib/faigate/faigate.db

WORKDIR /app

RUN addgroup --system faigate \
    && adduser --system --ingroup faigate --home /app faigate \
    && mkdir -p /var/lib/faigate \
    && chown -R faigate:faigate /app /var/lib/faigate

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

USER faigate

EXPOSE 8090

CMD ["python", "-m", "faigate"]
