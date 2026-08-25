# ---- stage 1: build the dashboard ------------------------------------
FROM node:20-alpine AS webbuild
WORKDIR /web
COPY web/package.json ./
RUN npm install --no-fund --no-audit
COPY web/ ./
RUN npm run build

# ---- stage 2: runtime -------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ agent/
COPY api/ api/
COPY core/ core/
COPY data/ data/
COPY --from=webbuild /web/dist web/dist
ENV PORT=8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
