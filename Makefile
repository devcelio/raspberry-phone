.PHONY: test run diagnose deploy

test:
	PYTHONPATH=src .venv/bin/python -m pytest

run:
	PYTHONPATH=src .venv/bin/python -m raspberry_phone

diagnose:
	./scripts/diagnose_pi.sh

deploy:
	./scripts/deploy.sh
