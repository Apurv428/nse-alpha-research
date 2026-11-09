# Thin wrapper over the `qr` CLI (the CLI is the primary interface; make is optional on Windows).
.PHONY: setup test lint-oos report all
setup:
	uv sync --python 3.11
test:
	uv run pytest -q
report:
	cd report && latexmk -pdf -interaction=nonstopmode main.tex
all: setup test
	@echo "Pipeline stages are wired in as each day lands (see PROGRESS.md)."
