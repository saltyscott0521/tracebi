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
# Bake the flagship demo: run the three-phase workflow once so the served
# project has a warehouse and a rendered report on first boot.
RUN cd examples/portfolio_project && python run_workflow.py
# Serve the example project — its models/ and reports/ are what discovery
# finds. docker-compose additionally sets TRACEBI_APP for the bundled demo.
WORKDIR /app/examples/portfolio_project
CMD python -m uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
