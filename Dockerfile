FROM node:22-slim AS ui-builder
WORKDIR /ui
COPY web/ui/package*.json ./
RUN npm ci
COPY web/ui/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY . .
COPY --from=ui-builder /ui/dist web/ui/dist
RUN pip install --no-cache-dir '.[reports,dashboard,pipeline,lineage,sql,web]'
CMD python -m uvicorn web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
