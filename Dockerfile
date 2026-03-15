FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FOUNDRYGATE_DB_PATH=/var/lib/foundrygate/foundrygate.db

WORKDIR /app

RUN addgroup --system foundrygate \
    && adduser --system --ingroup foundrygate --home /app foundrygate \
    && mkdir -p /var/lib/foundrygate \
    && chown -R foundrygate:foundrygate /app /var/lib/foundrygate

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

USER foundrygate

EXPOSE 8090

CMD ["python", "-m", "foundrygate"]
