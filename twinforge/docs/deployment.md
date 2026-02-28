# Deployment

## Prerequisites
- Docker & Docker Compose
- Python 3.11+

## Steps
1. `make setup` - Create .env and generate secrets
2. `make build` - Build all Docker images
3. `make up` - Start all services
4. `make logs` - Monitor logs
5. `make test` - Run tests
6. `make down` - Stop services
7. `make clean` - Remove containers and volumes
