FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app \
    && install --directory --owner=app --group=app /var/lib/celery

FROM base AS dependencies
COPY requirements/production.txt /tmp/requirements/production.txt
RUN python -m pip install --requirement /tmp/requirements/production.txt

FROM dependencies AS development
USER root
COPY requirements/base.txt requirements/development.txt /tmp/requirements/
RUN python -m pip install --requirement /tmp/requirements/development.txt
COPY --chown=app:app . /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live/', timeout=2)"
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM dependencies AS production
COPY --chown=app:app . /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live/', timeout=2)"
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
