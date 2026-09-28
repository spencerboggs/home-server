FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app
COPY --from=ui /ui/dist /app/static
EXPOSE 8000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
