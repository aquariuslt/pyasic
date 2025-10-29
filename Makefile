install:
	pip install -U poetry
	poetry install --with=dev
lint:
	poetry run black --check .
format:
	poetry run black .
test:
	poetry run pytest -vv
unittest:
	poetry run python -m unittest discover
