"""Identifica no cabeçalho a versão publicada, para conferir se a produção corresponde ao commit auditado."""
import re
from django.conf import settings

# Só aceita um identificador simples de commit; qualquer outro valor é ignorado.
_VALID = re.compile(r"[0-9a-f]{7,40}")


def app_version():
    value = (getattr(settings, "APP_COMMIT", "") or "").strip().lower()
    return value if _VALID.fullmatch(value) else ""


class VersionHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.version = app_version()

    def __call__(self, request):
        response = self.get_response(request)
        if self.version:
            response["X-App-Version"] = self.version
        return response
