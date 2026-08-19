FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proxy.py .
RUN test -s proxy.py && head -1 proxy.py && ! grep -q PLACEHOLDER proxy.py
EXPOSE 3333 8080
CMD ["python", "-u", "proxy.py"]
