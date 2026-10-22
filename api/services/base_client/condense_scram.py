"""[.mark] Le condensé SCRAM-SHA-256 d'un mot de passe, calculé par l'api (revue du chantier cloture-code).

Postgres accepte dans ``PASSWORD`` un mot de passe déjà condensé et le garde tel quel : le mot de passe
en clair ne traverse alors jamais la base (ni ses journaux, ni ``pg_stat_statements``). Format de
Postgres (RFC 5802 et 7677) : ``SCRAM-SHA-256$<itérations>:<sel>$<StoredKey>:<ServerKey>``.
Le mot de passe est tiré par l'api (``secrets.token_urlsafe``) : ASCII, la normalisation SASLprep
ne le change pas.
"""

import base64
import hashlib
import hmac
import os

ITERATIONS = 4096  # la valeur par défaut de Postgres (scram_iterations)


def condense_scram(mot_de_passe: str, *, sel: bytes | None = None) -> str:
    sel = sel if sel is not None else os.urandom(16)
    sale = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, ITERATIONS)
    cle_client = hmac.new(sale, b"Client Key", hashlib.sha256).digest()
    cle_stockee = hashlib.sha256(cle_client).digest()
    cle_serveur = hmac.new(sale, b"Server Key", hashlib.sha256).digest()

    def b64(octets: bytes) -> str:
        return base64.b64encode(octets).decode("ascii")

    return f"SCRAM-SHA-256${ITERATIONS}:{b64(sel)}${b64(cle_stockee)}:{b64(cle_serveur)}"
