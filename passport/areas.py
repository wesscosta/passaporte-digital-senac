"""Associação entre estande e área do Circuito Senac.

A associação é feita pelo nome do estande, porque o modelo não tem um campo de área. Um nome que não corresponda
a nenhuma área de referência recebe a insígnia neutra e é sinalizado na tela de gestão: não adivinhamos.
"""
import unicodedata

AREAS = {
    "tech": {"label": "Tecnologia da Informação", "names": ["tecnologia da informacao", "ti"]},
    "arts": {"label": "Artes e Design", "names": ["artes e design"]},
    "food": {"label": "Gastronomia e Turismo", "names": ["gastronomia e turismo"]},
    "fashion": {"label": "Moda e Beleza", "names": ["moda e beleza"]},
    "commerce": {"label": "Gestão e Comércio", "names": ["gestao e comercio", "gescom", "gestao e comercio (gescom)"]},
    "health": {"label": "Saúde", "names": ["saude"]},
}


def _plain(value):
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())


_LOOKUP = {name: key for key, area in AREAS.items() for name in area["names"]}


def area_key(stand):
    """Chave da área ou None quando o nome do estande não identifica uma área com segurança."""
    return _LOOKUP.get(_plain(stand.name))
