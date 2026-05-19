install:
	pip install -U poetry
	poetry install --with=dev
lint:
	poetry run black --check .
format:
	poetry run black .
test:
	poetry run pytest -vv
doctest:
	poetry run pytest --doctest-modules pyasic/data/pools.py pyasic/config/mining/presets.py -vv
unittest:
	poetry run python -m unittest discover
