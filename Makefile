# ============================================================================
#  Furnishing MES — developer command shortcuts
# ============================================================================
#  Every target is a thin wrapper around docker compose. If `make` is not
#  available (plain Windows shells), run the underlying command shown in
#  docs/07-development-setup.md section 4.
# ============================================================================

MODULE  := furnishing_mes
COMPOSE := docker compose

# Database name, overridable:  make upgrade DB=other_db
DB ?= $(shell grep -E '^ODOO_DB=' .env 2>/dev/null | cut -d= -f2)
DB := $(if $(DB),$(DB),furnishing_mes)

# One-off odoo invocation in a throwaway container.
#
# `run` is used rather than `exec` for two reasons:
#   1. `exec` bypasses the image entrypoint, so the --db_* arguments are never
#      built (the PG* variables in docker-compose.yml cover that, but see 2).
#   2. `exec` would try to bind port 8069, which the running server already
#      holds. `run` does not publish ports, so there is no conflict — and HTTP
#      still works inside the container for HttpCase tests in later phases.
#
# Dependencies are started automatically, so these targets work even when the
# stack is down.
ODOO_RUN := $(COMPOSE) run --rm web odoo

.DEFAULT_GOAL := help
.PHONY: help up down init init-prod logs restart upgrade install test shell psql bash ps clean

help:  ## Show this help
	@echo "Furnishing MES — available targets:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Database: $(DB)"

up:  ## Start the stack
	$(COMPOSE) up -d
	@echo "Odoo starting. Follow with: make logs"

down:  ## Stop the stack (data is preserved)
	$(COMPOSE) down

init:  ## First-time setup: create the database and install the module (with demo data)
	$(ODOO_RUN) -d $(DB) -i $(MODULE) --stop-after-init
	$(COMPOSE) up -d
	@echo
	@echo "Ready. Open http://localhost:$${ODOO_PORT:-8069}"

init-prod:  ## Same as init, but WITHOUT demo data (production installs)
	$(ODOO_RUN) -d $(DB) -i $(MODULE) --without-demo=all --stop-after-init
	$(COMPOSE) up -d

logs:  ## Tail the Odoo log
	$(COMPOSE) logs -f web

restart:  ## Restart Odoo only (picks up Python changes with no schema change)
	$(COMPOSE) restart web

upgrade:  ## Apply module changes (XML, security, models)
	$(ODOO_RUN) -d $(DB) -u $(MODULE) --stop-after-init
	$(COMPOSE) restart web

install:  ## Install the module into an existing database
	$(ODOO_RUN) -d $(DB) -i $(MODULE) --stop-after-init
	$(COMPOSE) restart web

test:  ## Run the module's test suite
	$(ODOO_RUN) -d $(DB) -u $(MODULE) \
		--test-enable --test-tags /$(MODULE) \
		--log-level=test --stop-after-init

shell:  ## Open the Odoo interactive shell
	$(COMPOSE) run --rm web odoo shell -d $(DB)

psql:  ## Open a PostgreSQL prompt
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-odoo} -d $(DB)

bash:  ## Shell inside the Odoo container
	$(COMPOSE) exec web bash

ps:  ## Show container status
	$(COMPOSE) ps

clean:  ## DESTROY containers and volumes — all data is lost
	@printf 'This deletes the database and filestore. Type "yes" to continue: ' \
		&& read ans && [ "$$ans" = "yes" ] && $(COMPOSE) down -v \
		|| echo "Aborted."
