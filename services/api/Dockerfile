FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LOAD_DOTENV=false
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/api/requirements.txt /tmp/requirements.txt
COPY services/api/requirements-stack.txt /tmp/requirements-stack.txt
ARG INSTALL_OPTIONAL_STACK=false
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN if [ "$INSTALL_OPTIONAL_STACK" = "true" ]; then pip install --no-cache-dir -r /tmp/requirements-stack.txt; fi
COPY . /app/
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
