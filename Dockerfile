FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home resolvematch
COPY backend/ backend/
COPY agent-instructions.md ./
COPY --from=web /web/dist frontend/dist
RUN mkdir /app/.local && chown -R resolvematch:resolvematch /app
USER resolvematch
EXPOSE 8000
CMD ["python","-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]
