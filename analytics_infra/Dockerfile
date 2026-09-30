FROM python:3.12-slim
WORKDIR /app
COPY analytics_infra/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY analytics_infra /app/analytics_infra
CMD ["uvicorn","analytics_infra.main:app","--host","0.0.0.0","--port","8080"]
