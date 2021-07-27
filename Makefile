export PATH := /snap/bin:$(PATH)

# TARGETS
lint: ## Run linter
	@tox -e lint

clean: ## Remove .tox and build dirs
	rm -rf .tox/
	rm -rf venv/
	rm -rf *.charm

build: build-lib ## Build nextcloud charm
	@charmcraft build --from charm-nextcloud

## Build nextcloud private charm
build-private: build-lib
	@charmcraft build --from charm-nextcloud-private

build-lib:
	cd lib && python3 setup.py bdist_wheel

push-nextcloud-to-edge: ## Push charms to edge s3
	@./scripts/push_charm.sh edge

# Display target comments in 'make help'
help: 
	grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# SETTINGS
# Use one shell for all commands in a target recipe
.ONESHELL:
# Set default goal
.DEFAULT_GOAL := help
# Use bash shell in Make instead of sh 
SHELL := /bin/bash
