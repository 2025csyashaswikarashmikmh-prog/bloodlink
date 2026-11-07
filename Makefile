.PHONY: up down logs ps test smoke images
up:        ## build and start all 5 containers
	docker compose up --build -d
down:      ## stop and remove containers + data
	docker compose down -v
ps:
	docker compose ps
images:
	docker images | grep -E "raktasetu|postgres|redis"
logs:
	docker compose logs -f backend
test:      ## run unit tests
	cd backend && pytest -q && cd ../ml-service && pytest -q
smoke:     ## end-to-end test against running stack
	./scripts/smoke_test.sh
