start:
  PYVIEW_SECRET=`openssl rand -base64 16` poetry run uvicorn examples.app:app --reload

UVICORN := `poetry run which uvicorn`

profile:
  poetry run scalene -- {{UVICORN}} pyview.main:app

test:
  poetry run pytest -vvvs

code:
  poetry run code -n .

docs:
  poetry run mkdocs serve

docker:
  docker build -t pyview .
  docker run -p 8000:8000 pyview
