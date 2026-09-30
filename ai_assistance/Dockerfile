FROM python:3.12-slim
WORKDIR /app
COPY ai_assistance/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY ai_assistance /app/ai_assistance
CMD ["uvicorn","ai_assistance.main:app","--host","0.0.0.0","--port","8080"]
