FROM python:3.14-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY proxy.py version_rolling.py run.py ./
RUN python -m py_compile proxy.py version_rolling.py run.py \
    && ! grep -q 'PLACEHOLDER' proxy.py \
    && ! grep -q 'PLACEHOLDER' version_rolling.py \
    && ! grep -q 'PLACEHOLDER' run.py

EXPOSE 3333 8080

CMD ["python", "-u", "run.py"]
