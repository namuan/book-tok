export PROJECTNAME=$(shell basename "$(PWD)")

.PHONY: $(shell grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk -F: '{print $$1}')

install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

install-prod: ## Install only production dependencies
	@echo "🚀 Installing production dependencies"
	@uv sync --no-dev

check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting with unsafe fixes"
	@uv run ruff check . --fix --unsafe-fixes
	@echo "🚀 Running ruff check"
	@uv run ruff check .
	@echo "🚀 Checking complexity"
	@uv run radon cc . -a -nb
	@echo "🚀 Checking quality metrics"
	@uv run skylos . --quality --danger
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@mob next

metrics: ## Check code quality: dead code, complexity, and maintainability (poe metrics equivalent)
	@echo "🚀 Checking code quality metrics"
	@uv run skylos . --quality
	@echo "🚀 Checking cyclomatic complexity"
	@uv run radon cc . -a -nb
	@echo "🚀 Checking maintainability index"
	@uv run radon mi . -nb

check-tool: ## Manually run a single pre-commit hook
	@echo "🚀 Running pre-commit hook: $(TOOL)"
	@uv run pre-commit run $(TOOL) --all-files

upgrade: ## Upgrade all dependencies to their latest versions
	@echo "🚀 Upgrading all dependencies"
	@uv lock --upgrade

test: ## Run all unit tests
	@echo "🚀 Running unit tests"
	@PYTHONPATH=. uv run pytest -v

test-single: ## Run a single test file (usage: make test-single TEST=test_config.py)
	@echo "🚀 Running single test: $(TEST)"
	@PYTHONPATH=. uv run pytest -v tests/$(TEST)

run: ## Run the application
	@echo "🚀 Running $(PROJECTNAME)"
	@uv run python -m spy_sma_alert_bot.main

deploy: clean ## Copies any changed file to the server
	ssh ${PROJECTNAME} -C 'bash -l -c "mkdir -vp ./${PROJECTNAME}"'
	rsync -avzr \
		.env \
		pyproject.toml \
		uv.lock \
		Makefile \
		scripts \
		spy_sma_alert_bot \
		${PROJECTNAME}:./${PROJECTNAME}

start: deploy ## Sets up a screen session on the server and start the app
	ssh ${PROJECTNAME} -C 'bash -l -c "./${PROJECTNAME}/scripts/setup_jobs.sh ${PROJECTNAME}"'

stop: deploy ## Stop any running screen session on the server
	ssh ${PROJECTNAME} -C 'bash -l -c "./${PROJECTNAME}/scripts/stop_jobs.sh ${PROJECTNAME}"'

ssh: ## SSH into the target VM
	ssh ${PROJECTNAME}

clean: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name "*.egg-info" -delete
	@rm -rf build/ dist/

context: clean ## Build context file from application sources
	llm-context-builder.py --extensions .py --ignored_dirs build dist generated venv .venv .idea .aider.tags.cache.v3 --print_contents --temp_file

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
