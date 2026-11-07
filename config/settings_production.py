import os
from .settings import *

MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
    "passport.version.VersionHeaderMiddleware",
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Nomes de arquivo com hash do conteúdo: um CSS antigo não pode ser servido com o endereço de um novo,
# e o WhiteNoise pode usar cache longo nos arquivos versionados. Exige collectstatic com estas configurações.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Commit da imagem, informado no build (APP_COMMIT). Exposto no cabeçalho X-App-Version.
APP_COMMIT = os.environ.get("APP_COMMIT", "")
