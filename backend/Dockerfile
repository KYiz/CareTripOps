FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY supplier_sim ./supplier_sim
COPY tests ./tests
COPY evals ./evals
COPY pytest.ini ./
# Migrations run separately (the Compose `migrate` service), so any number of API replicas can start safely.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
