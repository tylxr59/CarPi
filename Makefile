.PHONY: test lint format check
PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

lint:
	$(PYTHON) -m compileall -q src tests
	@if command -v ruff >/dev/null; then ruff check src tests; else echo 'ruff unavailable; compileall ran'; fi

format:
	@if command -v ruff >/dev/null; then ruff format src tests; else echo 'ruff unavailable; format skipped'; fi

check: lint test
	@if command -v shellcheck >/dev/null; then shellcheck install.sh uninstall.sh scripts/*.sh; else echo 'shellcheck unavailable'; fi
