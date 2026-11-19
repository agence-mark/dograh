"""Le certificat du banc, pour la seule vérification de clé de Soniox.

À l'enregistrement d'une configuration Soniox, le fork vérifie la clé sur une
adresse fixe, https://api.soniox.com/v1/models, qui ne suit pas l'adresse réglée
(api/services/configuration/check_validity.py). Sur le réseau fermé du banc, ce
nom mène au faux fournisseur (alias dans compose.yaml), qui doit donc répondre
en HTTPS avec un certificat que l'API du banc accepte.

Ce module fabrique, au premier démarrage, une autorité et un certificat valables
pour ce seul nom. L'autorité n'existe que dans un volume du banc : elle n'est
connue d'aucune autre machine, et sa clé privée est effacée dès la signature.
"""

from __future__ import annotations

import ssl
import subprocess
from pathlib import Path

NOMS = ("api.soniox.com", "api.eu.soniox.com")
DUREE_JOURS = "30"


def _openssl(*arguments: str, dossier: Path) -> None:
    subprocess.run(
        ["openssl", *arguments], cwd=dossier, check=True, capture_output=True
    )


def fabriquer(dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "autorite.cnf").write_text(
        "[req]\ndistinguished_name = nom\nx509_extensions = autorite\nprompt = no\n"
        "[nom]\nCN = Autorite du banc de telephonie\n"
        "[autorite]\nbasicConstraints = critical, CA:TRUE\n"
        "keyUsage = critical, keyCertSign, cRLSign\nsubjectKeyIdentifier = hash\n"
    )
    (dossier / "serveur.ext").write_text(
        "basicConstraints = critical, CA:FALSE\n"
        "keyUsage = critical, digitalSignature, keyEncipherment\n"
        "extendedKeyUsage = serverAuth\n"
        "subjectKeyIdentifier = hash\nauthorityKeyIdentifier = keyid\n"
        f"subjectAltName = {', '.join(f'DNS:{nom}' for nom in NOMS)}\n"
    )
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", DUREE_JOURS,
        "-config", "autorite.cnf", "-keyout", "autorite.cle", "-out", "autorite.pem",
        dossier=dossier,
    )  # fmt: skip
    _openssl(
        "req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={NOMS[0]}",
        "-keyout", "serveur.cle", "-out", "serveur.csr",
        dossier=dossier,
    )  # fmt: skip
    _openssl(
        "x509", "-req", "-in", "serveur.csr", "-CA", "autorite.pem", "-CAkey", "autorite.cle",
        "-CAcreateserial", "-days", DUREE_JOURS, "-extfile", "serveur.ext", "-out", "serveur.pem",
        dossier=dossier,
    )  # fmt: skip
    # L'autorité ne signera plus rien : sa clé privée ne sert plus.
    for superflu in (
        "autorite.cle",
        "autorite.cnf",
        "autorite.srl",
        "serveur.csr",
        "serveur.ext",
    ):
        (dossier / superflu).unlink(missing_ok=True)
    (dossier / "autorite.pem").chmod(0o644)


def contexte_du_serveur(dossier: Path) -> ssl.SSLContext:
    """Le contexte TLS du faux fournisseur. Fabrique le certificat s'il manque."""
    if (
        not (dossier / "serveur.pem").exists()
        or not (dossier / "autorite.pem").exists()
    ):
        fabriquer(dossier)
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.load_cert_chain(dossier / "serveur.pem", dossier / "serveur.cle")
    return contexte
