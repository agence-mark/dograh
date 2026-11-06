"""[.mark] Builder partie 3, N1 (sous-lot 6) : la garde « les secrets ne sont jamais lus en clair par le builder », dans TOUS les modes.

Une seule porte, ``registre.executer``, donc la même garde pour le chat (Demander, Tout permettre sur cet agent, Tout permettre, Plan) et pour
Claude Code. Le mode ne la change pas : « Tout permettre » compris, le builder choisit un secret par son NOM (un identifiant de clé, un
compte de téléphonie) et une personne le saisit à l'écran.

* **En entrée** : une valeur en clair sous un champ de secret (``api_key``, ``token``, ``password``...) est refusée avant toute écriture
  (code ``secret``). Passent : la référence ``CLE_MASQUEE`` (reprendre la clé en place), une valeur vide, et les champs qui désignent
  un secret sans le porter (``credential_uuid``, ``*_id``, ``*_name``...).
* **En sortie** : tout ce que le builder reçoit d'une action (lecture comprise) passe par le masque ; une valeur de secret est remplacée par
  ``CLE_MASQUEE``, à tous les niveaux. Même définition du « champ secret » que partout ailleurs (``est_un_champ_secret``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.services.builder.reglages_agent import CLE_MASQUEE

# Un champ dont le nom contient un mot de secret mais qui n'en porte pas la valeur : une référence (désigne le secret par son nom).
SUFFIXES_DE_REFERENCE = ("_uuid", "_id", "_ids", "_name", "_nom", "_ref", "_label", "_present", "_set")


def _est_secret(nom: Any) -> bool:
    from api.services.modeles_reglages.classement import est_un_champ_secret

    return est_un_champ_secret(nom) and not (isinstance(nom, str) and nom.lower().endswith(SUFFIXES_DE_REFERENCE))


def _porte_une_valeur(valeur: Any, *, structure: bool = False) -> bool:
    """Seul un texte non vide peut être un secret en clair ; un nombre, un booléen ou « rien » n'en est pas un. En sortie (``structure``),
    un bloc non vide rangé sous un nom de secret est aussi caché en entier."""
    if isinstance(valeur, bool) or valeur is None:
        return False
    if isinstance(valeur, str):
        return valeur.strip() != "" and valeur != CLE_MASQUEE
    return structure and isinstance(valeur, (Mapping, list)) and bool(valeur)


def secret_en_clair(valeur: Any, chemin: str = "") -> str | None:
    """Le chemin du premier champ de secret qui porte une valeur en clair dans ``valeur`` (entrée d'une action), sinon ``None``."""
    if isinstance(valeur, Mapping):
        for cle, v in valeur.items():
            lieu = f"{chemin}.{cle}" if chemin else str(cle)
            if _est_secret(cle) and _porte_une_valeur(v):
                return lieu
            if (trouve := secret_en_clair(v, lieu)) is not None:
                return trouve
    elif isinstance(valeur, list):
        for i, v in enumerate(valeur):
            if (trouve := secret_en_clair(v, f"{chemin}[{i}]")) is not None:
                return trouve
    return None


def masquer(valeur: Any) -> Any:
    """Copie de ``valeur`` sans aucune valeur de secret (sortie d'une action, arguments montrés, état avant / après du journal)."""
    if isinstance(valeur, Mapping):
        return {k: (CLE_MASQUEE if _est_secret(k) and _porte_une_valeur(v, structure=True) else masquer(v)) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [masquer(v) for v in valeur]
    if isinstance(valeur, tuple):
        return [masquer(v) for v in valeur]
    return valeur


def refus_d_un_secret(arguments: dict[str, Any] | None) -> dict[str, Any] | None:
    """Le résultat à rendre au cerveau si ses arguments portent un secret en clair, sinon ``None``. Ne montre jamais la valeur."""
    lieu = secret_en_clair(arguments or {})
    if lieu is None:
        return None
    return {
        "ok": False,
        "code": "secret",
        "erreur": (
            f"Nothing was done: « {lieu} » holds a secret in clear. You never read or write a key, a token or a password: choose it by its "
            "name (the credential already saved) and tell the person to type the secret on the screen."
        ),
    }
