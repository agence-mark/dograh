"""[.mark] Builder, lot 6 : la garde de publication (Q12, B38, B42).

La publication est refusée si :

* le **contrôle du prompt** a un défaut bloquant sur le brouillon ;
* un **test obligatoire** échoue, n'a jamais été rejoué, ou a été rejoué sur une AUTRE version du brouillon (B38 : après toute
  modification, la suite est rejouée avant de publier).

Jamais la moyenne (B42) : un seul test obligatoire rouge suffit. Les tests non obligatoires informent, ils ne bloquent pas.

**Portée** (constat C1, Evan 01/11) : les **tests obligatoires** gardent la publication de TOUT agent qui en a, suivi par le
builder ou non. Le **contrôle du prompt** ne garde que les agents suivis par le builder (des tests, ou une trace du builder) : un
agent ancien sans rien de tout cela se publie comme avant. Interrupteur d'urgence côté serveur, réservé à l'équipe (variable
d'environnement) : ``MARK_PUBLICATION_SANS_GARDE=1`` ; chaque publication qui passe grâce à lui est **journalisée**.

La forme rendue est celle de la validation (``is_valid`` + ``errors``) que l'écran sait déjà afficher, plus le détail.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from api.services.builder import stock
from api.services.builder.constantes import PREFIXE_BUILDER
from api.services.builder.controle.service import controler_l_agent
from api.services.builder.tests_agent import stockage

INTERRUPTEUR = "MARK_PUBLICATION_SANS_GARDE"


async def agent_suivi(organization_id: int, workflow_id: int) -> bool:
    if await stockage.lister(organization_id, workflow_id):
        return True
    lignes = await stock.lister_sans(organization_id, f"{PREFIXE_BUILDER}{workflow_id}:", ["avant", "apres", "complement"])
    # Partie 3, sous-lot 7 : l'instantané que prend une PUBLICATION (pour « Revenir avant ») n'est pas la trace d'un builder qui suit
    # l'agent : sans cette exception, publier suffirait à rendre l'agent « suivi » et à lui imposer les gardes de publication.
    return any(not (":instantanes:" in cle and valeur.get("cause") == "publication") for cle, valeur in lignes)


async def problemes_des_tests_obligatoires(
    organization_id: int, workflow_id: int, version: int | None, empreinte: str | None = None
) -> list[dict[str, Any]]:
    """``empreinte`` : celle du brouillon actuel (graphe + réglages). Revue R1 : une exécution rangée sans empreinte, ou avec une autre,
    n'a pas été rejouée sur CE brouillon, même si le numéro de version n'a pas bougé."""
    from api.services.builder import recettes

    # SE-6 : la recette a changé après une publication ; TOUS les tests déjà joués sont à rejouer depuis ce changement.
    depuis = await recettes.tests_a_rejouer_depuis(organization_id, workflow_id)
    problemes = []
    for test in await stockage.lister(organization_id, workflow_id):
        obligatoire = bool(test.get("obligatoire"))
        if not obligatoire and not depuis:
            continue
        derniere = await stockage.derniere_execution(organization_id, workflow_id, test["slug"])
        if not obligatoire and (derniere is None or str(derniere.get("le") or "") >= depuis):
            continue  # hors recette changée : un test facultatif jamais joué n'est pas bloquant
        if depuis and derniere is not None and str(derniere.get("le") or "") < depuis:
            raison = "the recipe changed after the last publication: replay the suite"
        elif derniere is None:
            raison = "never replayed"
        elif derniere.get("version") != version:
            raison = f"replayed on version {derniere.get('version')}, the draft is now version {version}: replay the suite"
        elif empreinte is not None and derniere.get("empreinte") != empreinte:
            raison = "the draft changed since the last replay (graph or settings): replay the suite"
        elif derniere.get("statut") != "ok":
            raison = f"failed ({derniere.get('reussis')}/{derniere.get('total')})"
        else:
            continue
        problemes.append({"slug": test["slug"], "nom": test["nom"], "raison": raison})
    return problemes


def empreinte_du_brouillon_publie(brouillon: Any) -> str:
    from api.services.builder.tests_agent import boucle

    return boucle.empreinte_du_brouillon(getattr(brouillon, "workflow_json", None), getattr(brouillon, "workflow_configurations", None))


async def verifier_avant_publication(
    workflow: Any, brouillon: Any, organization_id: int, user_id: int | None = None
) -> dict[str, Any] | None:
    """``None`` : on peut publier. Sinon le corps du refus (``is_valid`` faux + ``errors`` + détail)."""
    if os.environ.get(INTERRUPTEUR) == "1":
        logger.warning(
            f"[.mark] publication sans garde ({INTERRUPTEUR}=1) : organisation {organization_id}, agent {workflow.id}, "
            f"version {getattr(brouillon, 'version_number', None)}, personne {user_id}"
        )
        return None
    # [.mark] U11 : chaque contrôle a trois positions (``publication.controles``) ; les défauts sont la garde d'avant. Seule la
    # position « bloque » refuse ici ; « prévient » et « éteint » se lisent dans la fenêtre « Publier » (``publication/controles``).
    from api.services.publication import controles as fenetre
    from api.services.publication import reglages as reglages_publication

    from api.services.publication import defauts_org

    positions = reglages_publication.lire(
        await defauts_org.effectives(organization_id, getattr(brouillon, "workflow_configurations", None))
    ).controles
    tests = []
    if positions.tests_obligatoires == "bloque":
        tests = await problemes_des_tests_obligatoires(
            organization_id, workflow.id, getattr(brouillon, "version_number", None), empreinte_du_brouillon_publie(brouillon)
        )
    if positions.bilan_du_prompt == "bloque" and await agent_suivi(organization_id, workflow.id):
        controle = await controler_l_agent(
            workflow,
            organization_id,
            graphe=brouillon.workflow_json,
            configurations=await defauts_org.effectives(organization_id, getattr(brouillon, "workflow_configurations", None)),
        )
    else:
        controle = {"ok": True, "elements": [], "bloquants": []}
    # [.mark] Lot « façon Tala par motif » : K1 à K4 ont leur propre position (et leur propre ligne plus bas) ; le bilan ne les compte pas deux fois.
    from api.services.builder.controle.regles import CODES_DE_REDACTION

    elements = [e for e in controle["elements"] if e.get("code") not in CODES_DE_REDACTION]
    controle = {
        **controle,
        "elements": elements,
        "bloquants": [d for d in controle["bloquants"] if d.get("code") not in CODES_DE_REDACTION],
        "ok": not any(e["statut"] == "echec" for e in elements),
    }
    autres = []
    # [.mark] Partie 3 (SA-L3a) : les lignes obligatoires de « Prêt à publier » (variables, briques, outils), la sortie d'impasse sans
    # issue, les réglages sans effet et les deux webhooks bloquent par le même réglage que les autres contrôles.
    cles_de_la_fenetre = (
        "liste_vocale", "attaques", "garde_fous", "variables", "briques", "outils", "sans_effet", "sortie_d_impasse", "deux_webhooks",
        # Lot « façon Tala par motif » : K1 à K4 bloquent par le même réglage ; K5 (le poids) ne bloque jamais.
        "valeur_en_dur", "verbe_ecran", "action_sans_outil", "sortie_non_citee",
    )
    if any(getattr(positions, cle) == "bloque" for cle in cles_de_la_fenetre):
        vue = await fenetre.evaluer(workflow, brouillon, organization_id)
        autres = [c for c in vue["controles"] if c["statut"] == fenetre.ECHEC and c["cle"] in cles_de_la_fenetre]
    # [.mark] L3e : l'annonce « vous parlez à une IA » bloque toujours (position fixe, aucun réglage ne l'éteint) quand son texte est vide.
    vide = fenetre._annonce_ia(getattr(brouillon, "workflow_configurations", None) or {})
    if vide:
        autres.append({"cle": "annonce_ia", "libelle": fenetre.LIBELLES["annonce_ia"], "problemes": vide})
    # [.mark] U3 bis (E62) : une clé citée que le catalogue ne connaît pas bloque la publication.
    from api.services.variables_agent.garde import cles_inconnues_du_brouillon

    variables = await cles_inconnues_du_brouillon(workflow, brouillon, organization_id)
    # [.mark] Lot 8 (décision d'Evan du 04/11) : une étiquette d'objet cassée bloque toujours, sans réglage.
    etiquettes, _conseils = await fenetre.problemes_des_etiquettes(organization_id, brouillon)
    if etiquettes:
        autres.append({"cle": "etiquettes", "libelle": fenetre.LIBELLES["etiquettes"], "problemes": etiquettes})
    if controle["ok"] and not tests and not variables and not autres:
        return None
    erreurs = [{"kind": "node", "id": None, "field": "data.prompt", "message": f"[Prompt check] {e['message']}"} for e in controle["elements"] if e["statut"] == "echec"]
    erreurs += [{"kind": "node", "id": None, "field": None, "message": f"[Required test] {t['nom']}: {t['raison']}"} for t in tests]
    erreurs += [
        {"kind": "node", "id": None, "field": v["champ"], "message": f"[Unknown variable] {{{{{v['cle']}}}}} is not in the catalogue ({v['etape'] or 'settings'})"}
        for v in variables
    ]
    erreurs += [
        {"kind": "node", "id": None, "field": None, "message": f"[{c['libelle']}] {p}"} for c in autres for p in c["problemes"]
    ]
    return {
        "is_valid": False,
        "errors": erreurs,
        "garde": "builder",
        "controle": controle["bloquants"],
        "tests_obligatoires": tests,
        "variables_inconnues": variables,
        "controles_publication": [{"cle": c["cle"], "problemes": c["problemes"]} for c in autres],
    }
