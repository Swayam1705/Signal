.PHONY: install ingest dev backend frontend test benchmark evaluate build docker
install:
	python -m pip install -r requirements-dev.txt
	cd frontend && npm ci

ingest:
	python scripts/ingest.py --source fixture

backend:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

test:
	ruff check backend scripts tests
	pytest -q
	cd frontend && npm run lint && npm run build

benchmark:
	python scripts/benchmark.py --queries 100

evaluate:
	python scripts/evaluate.py

build:
	cd frontend && npm run build

docker:
	docker compose up --build
