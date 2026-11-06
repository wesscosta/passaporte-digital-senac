import secrets

# Sem 0/O, 1/I/L e U/V para facilitar a leitura em voz alta e na tela. 29^8 ≈ 5,0 × 10^11 combinações.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTWXYZ"
LENGTH = 8


def new_public_id():
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalize_public_id(value):
    """Aceita o identificador com hífen, espaços ou minúsculas; devolve None se não tiver o formato."""
    raw = "".join(ch for ch in value.upper() if ch.isalnum())
    if len(raw) == LENGTH and all(ch in ALPHABET for ch in raw):
        return raw
    return None


def format_public_id(raw):
    return f"{raw[:4]}-{raw[4:]}" if raw else ""
