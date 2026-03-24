.PHONY: test lint format install clean audit

install:
	pip install -e ".[dev]"
	pip install faiss-cpu 2>/dev/null || true

test:
	python -m pytest engram/tests/ -v --tb=short -x \
		--ignore=engram/tests/test_ollama.py \
		--ignore=engram/tests/test_benchmarks.py

test-all:
	python -m pytest engram/tests/ -v

lint:
	ruff check engram/ --ignore E501,E402
	black --check engram/ --line-length 100

format:
	black engram/ --line-length 100
	ruff check engram/ --fix --ignore E501,E402

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

audit:
	python -m pytest engram/tests/ --tb=short -q \
		--ignore=engram/tests/test_ollama.py \
		--ignore=engram/tests/test_benchmarks.py
	ruff check engram/ --ignore E501,E402 --statistics
