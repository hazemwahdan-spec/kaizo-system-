FROM python:3.12-slim
WORKDIR /app
COPY production_gate/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY production_gate /app/production_gate
CMD ["uvicorn","production_gate.main:app","--host","0.0.0.0","--port","8080"]
