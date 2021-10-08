export PATH := /snap/bin:$(PATH)

# TARGETS
lint: ## Run linter
	@tox -e lint

clean: ## Remove .tox and build dirs
	rm -rf .tox/
	rm -rf venv/
	rm -rf *.charm
	rm operator-nextcloud/version
	find . -iname "*.whl" -delete

build: version  ## Build nextcloud charm
	@charmcraft -v pack --project-dir operator-nextcloud

.PHONY: version
version: ## Generate version file
	@git describe --tags --dirty --always > operator-nextcloud/version

# Display target comments in 'make help'
help: 
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# SETTINGS
# Use one shell for all commands in a target recipe
.ONESHELL:
# Set default goal
.DEFAULT_GOAL := help
# Use bash shell in Make instead of sh 
SHELL := /bin/bash
