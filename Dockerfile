FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir '.[reports,dashboard,pipeline,lineage,sql]'

CMD python -m uvicorn web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
