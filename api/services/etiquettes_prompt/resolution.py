"""[.mark] Lots 8 et 22 : le RÉSOLVEUR des étiquettes, posé devant le moteur des variables. Pur : aucune base, rien de levé.

``rendre(texte, table, ...)`` rend le texte que le modèle reçoit :

1. chaque ``{{bloc:…}}`` devient le texte de la version choisie (``@vN`` : la version N ; sans version : la dernière en
   Recette, lue UNE fois au départ de l'appel : jamais deux versions mélangées dans un même appel). Un bloc qui cite un bloc :
   refusé au-delà d'un niveau (l'étiquette intérieure disparaît) ;
2. chaque autre étiquette devient ce que le modèle connaît : le nom EXACT de la fonction d'un outil (``mcp__serveur__outil``
   pour un outil MCP), le nom d'une étape ou d'un agent, le code d'un sujet de l'équipe, le nom d'un document, le texte d'une
   phrase ;
3. le texte part ensuite chez ``render_template`` (les ``{{variables}}`` d'un bloc sont donc rendues comme les autres).

Une étiquette que la table ne connaît pas disparaît, comme une variable inconnue : la publication l'a déjà refusée
(``catalogue.diagnostic``) ; à l'appel, rien ne lève. Un texte sans étiquette ressort à l'identique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from api.services.etiquettes_prompt import familles as f

RECETTE = "recette"
REJETE = "rejete"


@dataclass(frozen=True)
class VersionDeBloc:
    numero: int
    statut: str
    texte: str


@dataclass(frozen=True)
class BlocLu:
    slug: str
    titre: str
    famille: str
    versions: tuple[VersionDeBloc, ...] = ()

    def version(self, numero: int) -> VersionDeBloc | None:
        return next((v for v in self.versions if v.numero == numero), None)

    @property
    def derniere_recette(self) -> VersionDeBloc | None:
        recettes = [v for v in self.versions if v.statut == RECETTE]
        return max(recettes, key=lambda v: v.numero) if recettes else None

    @property
    def derniere(self) -> int:
        return max((v.numero for v in self.versions), default=0)

    def choisie(self, epingle: int | None) -> VersionDeBloc | None:
        """La version qu'une étiquette joue : l'épinglée (sauf rejetée), sinon la dernière Recette."""
        if epingle is not None:
            v = self.version(epingle)
            return v if v is not None and v.statut != REJETE else None
        return self.derniere_recette


@dataclass
class Table:
    """Ce que l'appel sait des objets cités : lu une fois au départ (``table.construire``)."""

    outils: dict[str, str] = field(default_factory=dict)  # clé (uuid ou uuid/fonction) -> nom de la fonction vue par le modèle
    agents: dict[str, str] = field(default_factory=dict)  # identifiant -> nom
    documents: dict[str, str] = field(default_factory=dict)  # document_uuid -> nom
    blocs: dict[str, BlocLu] = field(default_factory=dict)  # slug -> versions


def _texte_d_un_bloc(table: Table, cle: str) -> str | None:
    slug, epingle = f.bloc_et_version(cle)
    bloc = table.blocs.get(slug)
    version = bloc.choisie(epingle) if bloc is not None else None
    if version is None:
        return None
    # Un bloc ne cite pas un bloc (un niveau au plus) : l'étiquette intérieure disparaît.
    return f.remplacer(version.texte, lambda e: None if e.famille == f.BLOC else e.texte)


def rendre(
    texte: str | None,
    table: Table | None,
    *,
    etapes: Mapping[str, str] | None = None,
    phrase: Callable[[str], str | None] | None = None,
) -> str | None:
    """``etapes`` : identifiant -> nom des étapes de l'agent qui joue ; ``phrase`` : le texte d'une phrase (motif)."""
    if not texte or "{{" not in texte:
        return texte
    table = table or Table()

    def _blocs(e: f.Etiquette) -> str | None:
        return _texte_d_un_bloc(table, e.cle) if e.famille == f.BLOC else e.texte

    def _objets(e: f.Etiquette) -> str | None:
        if e.famille == f.OUTIL:
            return table.outils.get(e.cle)
        if e.famille == f.ETAPE:
            return (etapes or {}).get(e.cle)
        if e.famille == f.AGENT:
            return table.agents.get(e.cle)
        if e.famille == f.EQUIPE:
            return e.cle
        if e.famille == f.DOCUMENT:
            return table.documents.get(e.cle)
        if e.famille == f.PHRASE:
            return phrase(e.cle) if phrase is not None else None
        return None  # un bloc laissé par la première passe (version introuvable)

    return f.remplacer(f.remplacer(texte, _blocs), _objets)
