FROM python:3.12-slim
WORKDIR /app
COPY e2e_acceptance/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY e2e_acceptance /app/e2e_acceptance
CMD ["uvicorn","e2e_acceptance.main:app","--host","0.0.0.0","--port","8080"]
