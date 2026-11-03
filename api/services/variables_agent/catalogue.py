"""[.mark] U3 bis (E62) : le CATALOGUE des variables qu'un agent peut citer, calculé depuis les sources.

Quatre sources, une couleur chacune à l'écran : ``entreprise`` (établissement, équipe, objets du client = « Variables »,
phrases), ``appel`` (date, heure, identifiants, contexte de l'appel), ``fiche`` (champs de la fiche et variables extraites),
``campagne`` (colonnes que la campagne apporte). Les « valeurs d'essai » (``template_context_variables``) ne sont PAS une
source d'étiquettes (E64) ; leurs clés comptent seulement comme colonnes de campagne pour ne pas refuser un agent dont une
campagne apporte la colonne (provisoire, noté dans ``08`` « B3 »).

``construire`` est pure (testée seule) ; ``catalogue_de`` lit les sources. Ne lève jamais : une source illisible est une
source vide, le catalogue reste calculé avec les autres.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger

SOURCES = ("entreprise", "appel", "fiche", "campagne")


@dataclass(frozen=True)
class Variable:
    cle: str
    libelle: str
    source: str
    exemple: str = ""
    description: str = ""

    def en_dict(self) -> dict:
        return asdict(self)


# Les variables du moteur : calculées à l'appel, avec un exemple pour l'aperçu.
VARIABLES_DU_MOTEUR = (
    Variable("current_time", "Heure de l'appel", "appel", "14:32", "Heure du moment."),
    Variable("current_weekday", "Jour de l'appel", "appel", "mardi", "Jour de la semaine."),
    Variable("initial_context", "Contexte de l'appel", "appel", "", "Toute clé apportée par l'appel (famille ouverte)."),
)


def _du_code() -> list[Variable]:
    from api.services.communes.adresse import CLE_ADRESSE
    from api.services.equipe.appel import CLE_CLES, CLE_EQUIPE
    from api.services.etablissements.appel import CLE_FICHE_DE_LAPPEL, CLE_NOM, CLE_NUMERO_TRANSFERT
    from api.services.lexique.ecoute import CLE_A_ECOUTER, CLE_PROPOSE
    from api.services.pipecat.etat_ouverture import (
        CLE_ANNONCE,
        CLE_DATE_APPEL,
        CLE_ETAT,
        CLE_HEURE_APPEL,
        CLE_HORAIRES,
        CLE_REOUVERTURE,
    )

    return [
        Variable(CLE_NOM, "Nom de l'établissement", "entreprise", "Maison Durand"),
        Variable(CLE_NUMERO_TRANSFERT, "Numéro de transfert", "entreprise", "01 23 45 67 89"),
        Variable(CLE_FICHE_DE_LAPPEL, "Fiche de l'établissement de l'appel", "entreprise"),
        Variable(CLE_ADRESSE, "Adresse de l'établissement", "entreprise", "12 rue des Lilas, 60000 Beauvais"),
        Variable(CLE_EQUIPE, "Équipe", "entreprise", "Marie, Paul"),
        Variable(CLE_CLES, "Clés de l'équipe", "entreprise"),
        Variable(CLE_HORAIRES, "Horaires d'ouverture", "entreprise", "lundi au vendredi, 9 h à 18 h"),
        Variable(CLE_ETAT, "État d'ouverture", "entreprise", "ouvert"),
        Variable(CLE_REOUVERTURE, "Prochaine réouverture", "entreprise", "demain 9 h"),
        Variable(CLE_ANNONCE, "Annonce d'ouverture", "entreprise"),
        Variable(CLE_PROPOSE, "Vocabulaire proposé", "appel"),
        Variable(CLE_A_ECOUTER, "Vocabulaire à écouter", "appel"),
        Variable(CLE_DATE_APPEL, "Date de l'appel", "appel", "2026-11-04"),
        Variable(CLE_HEURE_APPEL, "Heure de l'appel", "appel", "14:32"),
        Variable("workflow_run_id", "Numéro de l'exécution", "appel", "1024"),
        Variable("call_id", "Identifiant de l'appel", "appel", "CA123"),
    ]


def construire(
    *,
    objets: list[dict[str, Any]] | None = None,
    phrases: list[str] | None = None,
    champs_fiche: list[str] | None = None,
    extraites: list[str] | None = None,
    colonnes_campagne: list[str] | None = None,
    reservees: list[str] | None = None,
) -> list[Variable]:
    """Pure. ``objets`` : ``{nom, libelle, exemple}``. Une clé n'a qu'UNE source (la première qui la pose gagne)."""
    vues: set[str] = set()
    sortie: list[Variable] = []

    def ajouter(v: Variable) -> None:
        if v.cle not in vues:
            vues.add(v.cle)
            sortie.append(v)

    for v in [*VARIABLES_DU_MOTEUR, *_du_code()]:
        ajouter(v)
    for o in objets or []:
        ajouter(Variable(o["nom"], o.get("libelle") or o["nom"], "entreprise", o.get("exemple", ""), "Variable de l'entreprise"))
    for nom in phrases or []:
        ajouter(Variable(nom, nom, "entreprise", "", "Phrase du catalogue"))
    for nom in champs_fiche or []:
        ajouter(Variable(nom, nom, "fiche", "", "Champ de la fiche"))
    for nom in extraites or []:
        ajouter(Variable(nom, nom, "fiche", "", "Variable extraite pendant l'appel"))
    for nom in reservees or []:
        ajouter(Variable(nom, nom, "appel", "", "Posée par le moteur"))
    for nom in colonnes_campagne or []:
        ajouter(Variable(nom, nom, "campagne", "", "Colonne apportée par une campagne"))
    return sortie


def cles_connues(variables: list[Variable]) -> set[str]:
    return {v.cle for v in variables}


def _noms_extraits(workflow_json: dict | None) -> list[str]:
    noms: list[str] = []
    for noeud in (workflow_json or {}).get("nodes", []) or []:
        donnees = (noeud or {}).get("data") or {}
        for v in donnees.get("extraction_variables") or []:
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                noms.append(v["name"])
    return noms


async def _objets(organization_id: int) -> list[dict[str, Any]]:
    """Les objets du client avec un exemple quand sa base répond ; sinon leurs noms retenus."""
    from api.services.objets_agent import stockage

    try:
        from api.db.bases_clients.connexion import connecter
        from api.db.bases_clients.objets import lire_objets
        from api.services.base_client.rattachement import nom_de_la_base
        from api.services.objets_agent.rendu import rendre

        base = await nom_de_la_base(organization_id)
        if base:
            connexion = await connecter(base)
            try:
                return [
                    {"nom": o.nom, "libelle": o.libelle, "exemple": rendre(o)[:80]}
                    for o in await lire_objets(connexion)
                ]
            finally:
                await connexion.close()
    except Exception as erreur:  # noqa: BLE001 -- une source illisible est une source vide
        logger.warning(f"[.mark] Catalogue des variables : objets de {organization_id} illisibles ({erreur!r})")
    return [{"nom": n, "libelle": n, "exemple": ""} for n in await stockage.lire_noms(organization_id)]


async def _phrases(organization_id: int) -> list[str]:
    try:
        from api.services.etablissements.copie import lire_copie_complete

        copie = await lire_copie_complete(organization_id)
        noms = [p.variable for p in copie.phrases.phrases]
        for e in copie.etablissements.etablissements:
            noms += list((e.phrases or {}).keys())
        return sorted(set(noms))
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Catalogue des variables : phrases de {organization_id} illisibles ({erreur!r})")
        return []


async def catalogue_de(
    organization_id: int,
    workflow_json: dict | None = None,
    configurations: dict | None = None,
    valeurs_d_essai: dict | None = None,
) -> list[Variable]:
    from api.schemas.fiche_agent import NOMS_RESERVES

    configurations = configurations or {}
    champs = [c.get("nom") for c in configurations.get("fiche_champs") or [] if isinstance(c, dict) and c.get("nom")]
    colonnes = [k for k in (valeurs_d_essai or {}) if isinstance(k, str)]
    return construire(
        objets=await _objets(organization_id),
        phrases=await _phrases(organization_id),
        champs_fiche=champs,
        extraites=_noms_extraits(workflow_json),
        colonnes_campagne=colonnes,
        reservees=sorted(NOMS_RESERVES),
    )
