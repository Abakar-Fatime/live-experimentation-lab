.PHONY: install run app test all

install:
	pip install -r requirements.txt

run:            ## simulate data, run every analysis, build the knowledge base, evaluate the copilot
	python -m lab.pipeline

app:            ## start the API + dashboard on http://localhost:8000
	uvicorn lab.api:app --reload --port 8000

test:
	pytest -q

all: install run test
