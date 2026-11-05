"""[.mark] Lots 8 et 22 : les familles d'étiquettes et le découpage d'une clé. Pur : aucune base, rien de levé.

Une étiquette d'objet s'écrit ``{{famille:cle}}`` ; la clé est l'identifiant STABLE de l'objet (le renommage est suivi) :

| famille    | clé                                         | exemple                                  |
|------------|---------------------------------------------|------------------------------------------|
| outil      | ``tool_uuid`` (``tool_uuid/fonction`` MCP)  | ``{{outil:3f2a…}}``                      |
| etape      | identifiant du nœud dans le graphe          | ``{{etape:node-12}}``                    |
| agent      | identifiant de l'agent                      | ``{{agent:42}}``                         |
| equipe     | code du sujet de transfert                  | ``{{equipe:devis}}``                     |
| document   | ``document_uuid``                           | ``{{document:9c1…}}``                    |
| phrase     | motif du catalogue des phrases du code      | ``{{phrase:outil_echec}}``               |
| bloc       | slug de l'élément, version figée en option  | ``{{bloc:regles-politesse@v2}}``         |

Le motif reprend celui du moteur des variables : un ``{{outil:x}}`` que le résolveur n'a pas remplacé serait lu comme une
variable inconnue et rendu vide ; c'est pourquoi les citations de variables écartent les étiquettes (``est_une_etiquette``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OUTIL = "outil"
ETAPE = "etape"
AGENT = "agent"
EQUIPE = "equipe"
DOCUMENT = "document"
PHRASE = "phrase"
BLOC = "bloc"
FAMILLES: tuple[str, ...] = (OUTIL, ETAPE, AGENT, EQUIPE, DOCUMENT, PHRASE, BLOC)

MOTIF = re.compile(r"\{\{\s*(" + "|".join(FAMILLES) + r"):([^|\s}]+)\s*\}\}")
_VERSION = re.compile(r"^(?P<slug>[^@]+)@v(?P<numero>[1-9]\d{0,3})$")


@dataclass(frozen=True)
class Etiquette:
    famille: str
    cle: str  # sans la famille, version comprise pour un bloc (``slug@v2``)

    @property
    def texte(self) -> str:
        return "{{" + f"{self.famille}:{self.cle}" + "}}"

    @property
    def complete(self) -> str:
        """``famille:cle`` : la clé que l'écran et le catalogue manipulent."""
        return f"{self.famille}:{self.cle}"


def est_une_etiquette(cle: str) -> bool:
    """``outil:x``, ``bloc:y@v2``… : une clé d'objet, jamais une variable (les citations de variables l'écartent)."""
    famille, sep, reste = (cle or "").partition(":")
    return bool(sep) and famille in FAMILLES and bool(reste)


def decouper(complete: str) -> Etiquette | None:
    famille, sep, reste = (complete or "").strip().partition(":")
    if not sep or famille not in FAMILLES or not reste:
        return None
    return Etiquette(famille, reste)


def etiquettes_de(texte: str | None) -> list[Etiquette]:
    """Les étiquettes d'un texte, dans l'ordre, avec leurs doublons."""
    return [Etiquette(m.group(1), m.group(2)) for m in MOTIF.finditer(texte or "")]


def bloc_et_version(cle: str) -> tuple[str, int | None]:
    """``regles@v2`` -> (``regles``, 2) ; ``regles`` -> (``regles``, None) : suit la dernière Recette."""
    m = _VERSION.match(cle or "")
    if m:
        return m.group("slug"), int(m.group("numero"))
    return cle, None


def outil_et_fonction(cle: str) -> tuple[str, str | None]:
    """``uuid/fonction`` (un outil d'un serveur MCP) -> (uuid, fonction) ; ``uuid`` -> (uuid, None)."""
    uuid, sep, fonction = (cle or "").partition("/")
    return uuid, (fonction or None) if sep else None


def sans_etiquettes(texte: str) -> str:
    """Le texte sans ses étiquettes d'objets (une règle qui cherche un NOM brut ne doit pas voir une étiquette)."""
    return MOTIF.sub(" ", texte or "")


def remplacer(texte: str, rendu) -> str:
    """Remplace chaque étiquette par ``rendu(Etiquette)`` ; ``None`` = l'étiquette disparaît (rien n'est dit du code)."""
    if not texte or "{{" not in texte:
        return texte

    def _un(m: re.Match[str]) -> str:
        valeur = rendu(Etiquette(m.group(1), m.group(2)))
        return "" if valeur is None else str(valeur)

    return MOTIF.sub(_un, texte)
