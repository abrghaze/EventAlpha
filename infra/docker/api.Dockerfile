FROM python:3.11-slim
WORKDIR /workspace
COPY pyproject.toml ./
COPY services/api ./services/api
COPY services/worker ./services/worker
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/workspace/services/api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
