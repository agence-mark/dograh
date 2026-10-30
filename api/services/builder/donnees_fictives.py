"""[.mark] Builder, lots 5 et 6 : les données fictives (Q3) et leur contrôle.

* ``rendre_fictif`` : un test tiré d'un vrai appel perd ses données personnelles À LA CRÉATION. Les adresses électroniques,
  numéros de téléphone et chiffres longs sont remplacés par des valeurs fausses stables (la même vraie valeur donne la même
  fausse dans tout le test, donc la conversation reste cohérente) ; les champs de la fiche dont le nom dit une personne
  (nom, prénom, adresse, mail, téléphone...) sont remplacés, et leurs anciennes valeurs sont réécrites partout où elles
  apparaissent dans la conversation.
* ``est_fictive`` : l'essai d'un outil (lot 5) n'accepte que des données de test, jamais une donnée qui a l'air réelle.

Les valeurs fausses sont des plages réservées : numéros de l'ARCEP prévus pour la fiction, domaine ``.test``.
⛔ Zéro vocabulaire métier : les noms de champs regardés sont ceux d'une PERSONNE, valables pour tout client.
"""

from __future__ import annotations

import copy
import re
from typing import Any

# Plages de numéros réservées à la fiction (ARCEP), écrites en chiffres nationaux.
PREFIXES_FICTIFS = ("019900", "026191", "035301", "046571", "053649", "063998", "073998")
DOMAINES_FICTIFS = (".test", ".invalid", ".example", "example.com", "example.org")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TELEPHONE = re.compile(r"(?<![\w])(?:\+33|0033|0)\s?[1-9](?:[\s.-]?\d{2}){4}(?![\w])")
_CHIFFRES_LONGS = re.compile(r"(?<![\w.])\d{9,}(?![\w])")
_CHAMPS_DE_PERSONNE = re.compile(r"(nom|prenom|name|adresse|address|mail|email|tel|phone|mobile|portable|naissance|birth|iban|siret|rue|ville|city)")


def _chiffres(texte: str) -> str:
    brut = re.sub(r"\D", "", texte)
    if brut.startswith("0033"):
        brut = "0" + brut[4:]
    elif brut.startswith("33") and len(brut) == 11:
        brut = "0" + brut[2:]
    return brut


def _telephone_fictif(rang: int) -> str:
    return f"06 39 98 {rang // 100 % 100:02d} {rang % 100:02d}"


def _email_fictif(rang: int) -> str:
    return f"personne{rang}@exemple.test"


def est_fictive(valeur: Any) -> bool:
    """Vrai si la valeur (récursivement) n'a rien d'une donnée réelle : e-mails en ``.test``, téléphones en plage fictive."""
    if isinstance(valeur, dict):
        return all(est_fictive(v) for v in valeur.values())
    if isinstance(valeur, (list, tuple)):
        return all(est_fictive(v) for v in valeur)
    if not isinstance(valeur, str):
        return True
    for email in _EMAIL.findall(valeur):
        if not email.lower().endswith(DOMAINES_FICTIFS):
            return False
    for tel in _TELEPHONE.findall(valeur):
        if not _chiffres(tel).startswith(PREFIXES_FICTIFS):
            return False
    return True


class _Faux:
    def __init__(self) -> None:
        self.table: dict[str, str] = {}
        self.rang = {"tel": 0, "mail": 0, "autre": 0}

    def pour(self, vrai: str, genre: str) -> str:
        if vrai not in self.table:
            self.rang[genre] += 1
            n = self.rang[genre]
            self.table[vrai] = _telephone_fictif(n) if genre == "tel" else _email_fictif(n) if genre == "mail" else f"valeur-fictive-{n}"
        return self.table[vrai]


def _masquer_texte(texte: str, faux: _Faux) -> str:
    texte = _EMAIL.sub(lambda m: m.group(0) if m.group(0).lower().endswith(DOMAINES_FICTIFS) else faux.pour(m.group(0), "mail"), texte)
    texte = _TELEPHONE.sub(lambda m: m.group(0) if _chiffres(m.group(0)).startswith(PREFIXES_FICTIFS) else faux.pour(m.group(0), "tel"), texte)
    return _CHIFFRES_LONGS.sub(lambda m: faux.pour(m.group(0), "autre"), texte)


def _valeurs_de_personne(fiche: Any, trouvees: dict[str, str], faux: _Faux, chemin: str = "") -> None:
    """Les valeurs texte des champs dont le NOM dit une personne : vraie valeur -> fausse."""
    if isinstance(fiche, dict):
        for cle, valeur in fiche.items():
            if isinstance(valeur, str):
                if valeur.strip() and len(valeur.strip()) >= 2 and _CHAMPS_DE_PERSONNE.search(str(cle).lower()):
                    trouvees[valeur] = faux.pour(valeur, "autre") if valeur not in faux.table else faux.table[valeur]
            else:
                _valeurs_de_personne(valeur, trouvees, faux, f"{chemin}.{cle}")
    elif isinstance(fiche, list):
        for v in fiche:
            _valeurs_de_personne(v, trouvees, faux, chemin)


def _appliquer(valeur: Any, remplacements: dict[str, str], faux: _Faux) -> Any:
    if isinstance(valeur, str):
        for vrai in sorted(remplacements, key=len, reverse=True):
            valeur = valeur.replace(vrai, remplacements[vrai])
        return _masquer_texte(valeur, faux)
    if isinstance(valeur, dict):
        return {k: _appliquer(v, remplacements, faux) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_appliquer(v, remplacements, faux) for v in valeur]
    return valeur


def rendre_fictif(test: dict[str, Any]) -> dict[str, Any]:
    """Le test (JSON ``tests_rejouables``) sans donnée personnelle. Ne modifie pas l'original. Marque ``donnees_fictives``."""
    faux = _Faux()
    copie = copy.deepcopy(test)
    remplacements: dict[str, str] = {}
    _valeurs_de_personne(copie.get("fiche") or {}, remplacements, faux)
    for cle in ("historique", "replique", "fiche", "critere", "description"):
        if cle in copie:
            copie[cle] = _appliquer(copie[cle], remplacements, faux)
    # La source garde le numéro du run (pour retrouver l'appel), jamais son contenu.
    copie["donnees_fictives"] = True
    return copie
