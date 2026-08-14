FROM node:22-slim AS ui-builder
# Mirror the repo layout so vite's build.outDir ('../../tracebi/web/ui/dist',
# relative to web/ui/) lands where the Python package expects it.
WORKDIR /src/web/ui
COPY web/ui/package*.json ./
RUN npm ci
COPY web/ui/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY . .
COPY --from=ui-builder /src/tracebi/web/ui/dist tracebi/web/ui/dist
RUN pip install --no-cache-dir '.[reports,pipeline,lineage,sql,postgres,duckdb,web]'
CMD python -m uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
