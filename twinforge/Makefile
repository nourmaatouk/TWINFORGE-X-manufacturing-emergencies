.PHONY: help setup build up down logs test clean

help:
	@echo "TWINFORGE - Manufacturing Digital Twin Platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup      - Generate secrets and setup environment"
	@echo "  make build      - Build all Docker images"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View logs from all services"
	@echo "  make test       - Run all tests"
	@echo "  make clean      - Clean up containers and volumes"

setup:
	@echo "Setting up TWINFORGE..."
	./scripts/setup.sh
	./scripts/generate-secrets.sh

build:
	@echo "Building Docker images..."
	docker-compose build

up:
	@echo "Starting TWINFORGE services..."
	docker-compose up -d

down:
	@echo "Stopping TWINFORGE services..."
	docker-compose down

logs:
	docker-compose logs -f

test:
	@echo "Running tests..."
	./scripts/run-tests.sh

clean:
	@echo "Cleaning up..."
	docker-compose down -v
	docker system prune -f
