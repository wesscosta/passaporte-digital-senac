FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.prod.txt ./
RUN pip install --no-cache-dir -r requirements.prod.txt \
    && useradd --uid 10001 --no-create-home app
COPY config ./config
COPY passport ./passport
COPY manage.py ./
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput
RUN chmod -R a+rX /app
USER app
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "config.wsgi:application"]
