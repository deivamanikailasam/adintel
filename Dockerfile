# AdIntel backend image (api-service, agent-worker, executor-service, scheduler share one image;
# the command and ADINTEL_PROCESS_ROLE select the role). Models are NOT in the image: locally they run
# on the host with mlx-lm (Apple Silicon), in production on Bedrock/SageMaker.
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN groupadd -r adintel && useradd -r -g adintel -d /app adintel
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[ml,aws]"   # aws: boto3 for the Object Lock audit archive (MinIO locally)
COPY config ./config
COPY prompts ./prompts
COPY evals ./evals
USER adintel
EXPOSE 8000 9464
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health') if __import__('os').environ.get('ADINTEL_PROCESS_ROLE','api')=='api' else None"
CMD ["uvicorn", "adintel.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers"]
