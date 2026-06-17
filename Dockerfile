FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY src/ ./src/
COPY web/ ./web/
COPY skills/ ./skills/
COPY dependencies/ ./dependencies/
COPY config.py .
RUN addgroup --system kchat && \
    adduser --system --ingroup kchat --no-create-home kchat && \
    chown -R kchat:kchat /app
USER kchat
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000"]
