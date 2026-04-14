web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4
worker: python -m app.pipeline.orchestrator
