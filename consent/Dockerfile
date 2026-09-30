FROM python:3.12-slim
WORKDIR /app
COPY consent/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY consent /app/consent
CMD ["uvicorn","consent.main:app","--host","0.0.0.0","--port","8080"]
