.PHONY: up down reseed logs ps psql

# Start everything (build images, run in background).
up:
	docker compose up --build -d

# Stop and remove containers AND the data volume (full reset).
down:
	docker compose down -v

# Wipe and reload the dataset in-place (keeps the volume/container).
reseed:
	docker compose run --rm seed python -m src.seed --force

# Follow logs from all services.
logs:
	docker compose logs -f

# Show service status.
ps:
	docker compose ps

# Open a psql shell against the running database.
psql:
	docker compose exec postgres psql -U postgres -d postgres
