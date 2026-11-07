FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.prod.txt ./
RUN pip install --no-cache-dir -r requirements.prod.txt \
    && useradd --uid 10001 --no-create-home app
COPY config ./config
COPY passport ./passport
COPY manage.py ./
# As configurações de produção geram os nomes com hash e o manifesto usados em execução.
RUN DJANGO_DEBUG=1 DJANGO_SETTINGS_MODULE=config.settings_production python manage.py collectstatic --noinput
RUN chmod -R a+rX /app
ARG APP_COMMIT=""
ENV APP_COMMIT=${APP_COMMIT}
USER app
# O socket de controle do gunicorn 26 seria criado em $HOME, que não existe para o usuário app; não é usado.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--no-control-socket", "config.wsgi:application"]
