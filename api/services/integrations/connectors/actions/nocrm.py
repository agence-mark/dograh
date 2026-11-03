"""[.mark] noCRM (prospecting CRM): actions (U3 sexies, point 8, F2).

State « À essayer ». noCRM.io API v2 (https://www.nocrm.io/crm-api-documentation); through
Nango's relay (integration ``nocrm``, the account's subdomain is in the connection). ⚠ The
documentation page could not be read at writing time and noCRM's presence in Nango's catalogue
is not confirmed: the shapes below are the documented v2 resources (``/leads``,
``/leads/{id}/comments``) and must be checked at the first trial.

noCRM has LEADS, not contacts: the caller is a lead, his phone and e-mail written in its
description. So the actions are the lead's own, with the same names where the meaning is the same:

- ``find_contact``: ``GET /leads?query=`` on the nine last digits of the number or the e-mail.
- ``create_lead``: ``POST /leads`` (title, description, pipeline and step, owner and tags of the
  settings).
- ``add_call_note``: ``POST /leads/{id}/comments``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors.actions._commun import (
    action_note,
    action_trouver,
    criteres,
    identite,
    nom_complet,
    resultat_creation,
    resultat_note,
    texte_de_la_note,
    trouves,
)
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES_PROSPECT = {"proprietaire": "", "pipeline": "", "etape": "", "etiquettes": []}


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    terme = "".join(c for c in formes[0] if c.isdigit())[-9:] if formes else str(mail)
    return Requete("GET", "/leads", params={"query": terme, "limit": 3})


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    prospects = reponse if isinstance(reponse, list) else (reponse or {}).get("leads") or []
    return trouves([(p.get("id"), p.get("title")) for p in prospects if isinstance(p, dict)])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_PROSPECT, **ctx.reglages}
    titre = params.get("titre") or nom_complet(i["prenom"], i["nom"]) or i["telephone"] or i["mail"]
    lignes = [
        f"Téléphone : {i['telephone']}" if i["telephone"] else None,
        f"E-mail : {i['mail']}" if i["mail"] else None,
        f"Motif : {ctx.modele.motif}" if ctx.modele.motif else None,
        str(params["resume"]) if params.get("resume") else None,
        "Prospect créé par l'assistant vocal.",
    ]
    corps: dict[str, Any] = {"title": titre, "description": "\n".join(x for x in lignes if x)}
    if r.get("proprietaire"):
        corps["user_id"] = int(r["proprietaire"])
    if r.get("pipeline"):
        corps["pipeline"] = str(r["pipeline"])
    if r.get("etape"):
        corps["step"] = str(r["etape"])
    if r.get("etiquettes"):
        corps["tags"] = [str(t) for t in r["etiquettes"]]
    return Requete("POST", "/leads", json=corps)


def _commentaire(params: dict, ctx: ContexteAction) -> Requete:
    return Requete(
        "POST",
        f"/leads/{quote(str(params['identifiant']), safe='')}/comments",
        json={"content": texte_de_la_note(params, ctx)},
    )


NOCRM = declarer(
    Connecteur(
        nom="nocrm",
        libelle="noCRM",
        integration="nocrm",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            Action(
                nom="create_lead",
                description="Create the caller as a lead in the business's noCRM. Search first: never create twice.",
                parametres=(
                    Parametre("prenom", description="His first name.", obligatoire=False),
                    Parametre("nom", description="His last name.", obligatoire=False),
                    Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
                    Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
                    Parametre("resume", description="What he asked, in one or two sentences.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_creer,
                resultat=resultat_creation("id"),
                reglages_par_defaut=REGLAGES_PROSPECT,
            ),
            action_note(_commentaire, resultat_note),
        ),
    )
)
