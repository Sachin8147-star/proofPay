FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
# The verifier needs the host's Docker socket: run with -v /var/run/docker.sock:/var/run/docker.sock
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
