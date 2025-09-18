SHELL := /bin/bash

UV := uv
DB ?= money_diary.db

.PHONY: help install db-init db-reset gui lint test quality clean

help:
	@echo "Available targets:"
	@echo "  make install     # Install requirements into virtualenv"
	@echo "  make db-init     # Initialize SQLite schema (creates $(DB))"
	@echo "  make db-reset    # Reset DB (drops and re-initializes $(DB))"
	@echo "  make gui         # Launch Streamlit GUI"
	@echo "  make lint        # Run ruff lint"
	@echo "  make test        # Run SQL regression tests"
	@echo "  make quality     # Run quality checks (tests, linters)"
	@echo "  make clean       # Remove virtualenv and DB"

install: requirements.txt
	$(UV) python install 3.12
	$(UV) venv --python 3.12
	$(UV) pip install -r requirements.txt

# Initialize DB once (non-destructive if file exists)
db-init:
	sqlite3 $(DB) < schema.sql

# Warning: removes existing DB file
db-reset:
	rm -f $(DB)
	sqlite3 $(DB) < schema.sql

gui: install
	$(UV) run streamlit run app/streamlit_app.py

lint: install
	$(UV) run ruff check app
	$(UV) run ruff check scripts

test:
	$(UV) run ./scripts/test.sh

quality: lint test

clean:
	rm -rf .venv
	rm -f $(DB)
