# Network-isolated sandbox image for Analyst queries (ADINTEL_SANDBOX=docker).
# Run with: docker run --rm -i --network none --read-only --cap-drop ALL ...
FROM python:3.12-slim
RUN pip install --no-cache-dir "pandas>=2.2" "numpy>=1.26" && useradd -r sandbox
USER sandbox
