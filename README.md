# PolyData

<img src="/backend/src/dashboard/static/logo.svg" alt="PolyData Logo" style="width: 128px;" />

PolyData is a modular platform for ingesting, managing, and publishing data built on Django, Wagtail and PygeoAPI. Its architecture combines a Django backend with:

- Wagtail CMS for content and administration
- Catalog API, DRF for tabular data and Pygeoapi for geospatial services on top of Postgres with PostGIS and ParadeDB.
- OpenID Connect authentication (OIDC) using `django-oidc-provider`
- Internal apps (`account`, `catalog`, `ingestion`, `main`) containing
  business logic
- Docker compose ready for production deployment

## Features

- **OIDC authentication** for users and relying-party clients
- **REST API** with OpenAPI/Swagger (`drf-spectacular`)
- **OGC API service** configurable via environment variables
- **Data ingestion** leveraging PostGIS and GeoAlchemy
- **Elastic quality search** with ParadeDB
- **Flexible configuration** through env vars
- **Docker Compose** orchestration of database and Django server

## Requirements

- Docker & Docker Compose
- (Optional for local tasks) Python 3.14+
- PostgreSQL with PostGIS and ParadeDB extension (provided by the `database` container)

## Quickstart

When running through Docker Compose, set the database host to the Compose service name `database`, not `localhost`.

1. Clone the repository:

   ```bash
   git clone https://github.com/tu-org/PolyData.git
   cd PolyData
   ```

2. Copy and edit the environment files:

   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

3. Bring up the services:

   ```bash
   docker-compose up -d --build
   ```

   This will start the `database` (PostGIS and ParadeDB) and `backend` (Django/Gunicorn)
   containers.

   If you already have a local PostgreSQL volume created with the old
   `/var/lib/postgresql/data` mount layout, do not reuse it directly with
   PostgreSQL 18+ images. Remove the old development volume if it is
   disposable, or migrate it with `pg_upgrade` before reattaching data.

4. Create a Django superuser to access the admin:

   ```bash
   docker-compose exec backend uv run src/manage.py createsuperuser
   ```

5. Visit the key endpoints:
   - Django admin: `http://127.0.0.1:8000/admin/`
   - Wagtail admin: `http://127.0.0.1:8000/cms/` (if enabled)
   - REST API: `http://127.0.0.1:8000/api/`
   - PygeoAPI: `http://127.0.0.1:8000/geoapi/` (configurable via
     `PYGEOAPI_BASE_PATH`)
   - Swagger/OpenAPI: `http://127.0.0.1:8000/api/schema/swagger-ui/`

## Development

Inside the backend container:

```bash
docker-compose exec backend bash
# then use manage.py or uv like any Django project
uv run src/manage.py migrate
uv run src/manage.py runserver 0.0.0.0:8000
```

Python dependencies are managed with UV. To add a package:

```bash
docker-compose exec backend uv add <package>
```

## Project structure

- `backend/` – main Django application
  - `account/` – custom user model and auth
  - `catalog/` – catalog logic and pygeoapi configuration
  - `ingestion/` – data loading services
  - `main/` – settings, urls and general views
- `frontend/` – (optional) code for a decoupled client
- `docker-compose.yaml` – defines `db` and `backend` services

## Important environment variables

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `SECRET_KEY`, `DEBUG`, `DJANGO_URL`, `FRONTEND_URL`
- `PYGEOAPI_TABLE`, `PYGEOAPI_BASE_PATH`, `PYGEOAPI_TITLE`, etc.

See `backend/src/main/settings/base.py` for the full list with comments.

## Deployment

You can deploy on any container platform. Be sure to:

1. Adjust environment variables for production (`DEBUG=false`, hosts,
   etc.).
2. Use an appropriate WSGI/ASGI backend (Gunicorn is already configured).
3. Mount persistent volumes for `db` and `backend` if needed.

## Roadmap

- [x] Celery task queue for asynchronous processing
- [x] Fine grained permissions and roles
- [] Data versioning and history
- [] More ingestion connectors (CSV, APIs, etc.)
- [] Map creation and publishing tools
- [] DataStories and dashboards

## Contributing

Pull requests are welcome! 🙌

1. Fork and branch with a `feature/` or `fix/` prefix.
2. Add tests and documentation when applicable.
3. Open a PR describing your change.
4. Respond to feedback and keep commits tidy.

## License

This project is licensed under the GNU Affero General Public License. See the [LICENSE](LICENSE) file for details.

---

_Thanks for using PolyData!_ 🌍
