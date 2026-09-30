FROM python:3.12-slim
WORKDIR /app
COPY integration_hardening/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY integration_hardening /app/integration_hardening
CMD ["uvicorn","integration_hardening.main:app","--host","0.0.0.0","--port","8080"]
