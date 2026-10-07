"""[.mark] What the run window shows of the team (chantier l-agent-collegue, L8).

The sub-part « Mentions » of the section « After the call »:

- ``lire_mentions``: the mentions of THIS call in the client's database of THIS organization
  (person, source, certainty, extract), and the names of the people (key -> name) to label the
  actions. Never raises: an unreadable database is said, never a crash of the section.
- ``actions_pour_lequipe``: what the agent did for the team during the call, read in the run's
  record (transfers, requests passed on, call-backs to make, appointments booked, verifications,
  records read). Pure.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from api.schemas.apres_appel import ActionEquipe, MentionDuRun
from api.services.apres_appel.rappels import ORIGINE_PLANIFICATEUR, origine, rappels_de


def _nom(prenom: str | None, nom: str | None, cle: str) -> str:
    return " ".join(x for x in (prenom, nom) if x) or cle


async def lire_mentions(organization_id: int, appel_id: int | None) -> tuple[list[MentionDuRun], dict[str, str], bool]:
    """(mentions, names by key, unreadable). Nothing when the call is not written yet."""
    from api.db.bases_clients.connexion import connecter
    from api.db.bases_clients.gestes import mentions_de_l_appel, personnes_de_la_base
    from api.services.base_client.rattachement import nom_de_la_base

    noms: dict[str, str] = {}
    try:
        base = await nom_de_la_base(organization_id)
        if not base:
            return [], noms, False
        connexion = await connecter(base)
        try:
            for r in await personnes_de_la_base(connexion):
                noms[r["cle"]] = _nom(r["prenom"], r["nom"], r["cle"])
            if not appel_id:
                return [], noms, False
            lignes = await mentions_de_l_appel(connexion, appel_id)
        finally:
            await connexion.close()
    except Exception as erreur:  # noqa: BLE001 -- the section shows the rest
        logger.warning(f"[.mark] Mentions of call {appel_id} unreadable: {erreur!r}")
        return [], noms, True
    return [
        MentionDuRun(personne=noms.get(r["cle"], r["cle"]), source=r["source"], certitude=r["certitude"], extrait=r["extrait"])
        for r in lignes
    ], noms, False


def _moment(iso) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if isinstance(iso, str) else None
    except ValueError:
        return None


def _liste(contexte: dict, cle: str) -> list[dict]:
    brut = contexte.get(cle)
    return [x for x in brut if isinstance(x, dict)] if isinstance(brut, list) else []


def actions_pour_lequipe(contexte: dict, noms: dict[str, str] | None = None) -> list[ActionEquipe]:
    noms = noms or {}

    def qui(cle) -> str | None:
        return noms.get(cle, cle) if cle else None

    sortie: list[ActionEquipe] = []
    for g in _liste(contexte, "equipe_gestes"):
        if g.get("geste") == "transfert":
            detail = ("décroché" if g.get("decroche") else "pas de réponse")
            if isinstance(g.get("duree_s"), int):
                detail += f", {g['duree_s']} s"
            sortie.append(ActionEquipe(type="transfert", personne=qui(g.get("personne")), detail=detail, le=_moment(g.get("le"))))
        elif g.get("geste") == "transmission":
            sortie.append(ActionEquipe(type="transmission", personne=qui(g.get("personne")),
                                       detail=g.get("motif"), le=_moment(g.get("le"))))
    for r in rappels_de(contexte):
        if origine(r) == ORIGINE_PLANIFICATEUR:
            detail = "aucun créneau" + (f" (souhait : « {r['souhait']} »)" if r.get("souhait") else "")
        elif origine(r) == "equipe":
            detail = " ; ".join(x for x in (r.get("objet"), f"souhaité : « {r['souhait']} »" if r.get("souhait") else None) if x) or None
        else:
            detail = "appelant non vérifié"
        sortie.append(ActionEquipe(type="rappel", personne=qui(r.get("personne")), detail=detail, le=_moment(r.get("le"))))
    for rdv in _liste(contexte, "hub_rendez_vous"):
        sortie.append(ActionEquipe(type="rendez_vous", personne=qui(rdv.get("personne")),
                                   detail=rdv.get("type") or rdv.get("motif"), le=_moment(rdv.get("debut"))))
    for v in _liste(contexte, "verification_appelant"):
        reussis = ", ".join(v.get("facteurs_reussis") or []) or "aucun facteur"
        sortie.append(ActionEquipe(type="verification", detail=f"{v.get('resultat')} ({reussis})", le=_moment(v.get("le"))))
    for lu in _liste(contexte, "dossier_lu"):
        sortie.append(ActionEquipe(type="dossier_lu", detail=f"{lu.get('quoi')} : {lu.get('nombre')} élément(s)",
                                   le=_moment(lu.get("le"))))
    return sortie
