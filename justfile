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

type-check:
  poetry run pyright

lint:
  poetry run ruff check .

format:
  poetry run ruff format .

format-fix:
  poetry run ruff check --fix .
  poetry run ruff format .

build-js:
  cd pyview/assets && npx esbuild js/app.js --bundle --target=es2017 --outdir=../static/assets/
  cp pyview/assets/js/uploaders.js pyview/static/assets/uploaders.js
