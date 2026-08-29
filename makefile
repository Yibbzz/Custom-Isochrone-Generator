# Default: no mirrord
MIRRORD ?=

# If MIRRORD=1, enable mirrord wrapper
ifeq ($(MIRRORD),1)
RUN_PREFIX = mirrord exec -f .mirrord/mirrord.json --
else
RUN_PREFIX =
endif

# Core command wrapper
PYTEST = python manage.py test

# ----------------------
# Tests
# ----------------------

test-unit:
	$(RUN_PREFIX) $(PYTEST) \
		myapp.tests.test_db_logic \
		myapp.tests.test_cleanup_commands \
		-v 2

test-integration:
	$(RUN_PREFIX) $(PYTEST) \
		myapp.tests.test_full_integration.FullUserFlowTest \
		-v 2 --keepdb

test-all: test-unit test-osm test-integration