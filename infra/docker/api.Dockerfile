FROM python:3.11-slim
WORKDIR /workspace
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY services/api ./services/api
ENV PYTHONPATH=/workspace/services/api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
