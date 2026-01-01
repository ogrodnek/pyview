start:
  PYVIEW_SECRET=`openssl rand -base64 16` uv run uvicorn examples.app:app --reload

test:
  uv run pytest -vvvs

code:
  uv run code -n .

docs:
  cd docs-site && npm run dev

docs-build:
  cd docs-site && npm run build

docs-preview:
  cd docs-site && npm run preview

docker:
  docker build -t pyview .
  docker run -p 8000:8000 pyview

type-check:
  uv run pyright

lint:
  uv run ruff check .

format:
  uv run ruff format .

format-fix:
  uv run ruff check --fix .
  uv run ruff format .

build-js:
  cd pyview/assets && npx esbuild js/app.js --bundle --target=es2017 --outdir=../static/assets/
  cp pyview/assets/js/uploaders.js pyview/static/assets/uploaders.js
