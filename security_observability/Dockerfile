FROM python:3.12-slim
WORKDIR /app
COPY security_observability/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY security_observability /app/security_observability
CMD ["uvicorn","security_observability.main:app","--host","0.0.0.0","--port","8080"]
