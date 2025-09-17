SHELL := /bin/bash

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
STREAMLIT := $(VENV)/bin/streamlit
DB ?= money_diary.db

.PHONY: help venv install db-init db-reset gui test quality clean

help:
	@echo "Available targets:"
	@echo "  make venv        # Create Python virtualenv"
	@echo "  make install     # Install requirements into virtualenv"
	@echo "  make db-init     # Initialize SQLite schema (creates $(DB))"
	@echo "  make db-reset    # Reset DB (drops and re-initializes $(DB))"
	@echo "  make gui         # Launch Streamlit GUI"
	@echo "  make test        # Run SQL regression tests"
	@echo "  make quality     # Run quality checks (tests, linters)"
	@echo "  make clean       # Remove virtualenv and DB"

venv:
	python3 -m venv $(VENV)

install: venv requirements.txt
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Initialize DB once (non-destructive if file exists)
db-init:
	sqlite3 $(DB) < schema.sql

# Warning: removes existing DB file
db-reset:
	rm -f $(DB)
	sqlite3 $(DB) < schema.sql

gui: install
	$(STREAMLIT) run app/streamlit_app.py

test:
	./scripts/test.sh

quality: test

clean:
	rm -rf $(VENV)
	rm -f $(DB)
