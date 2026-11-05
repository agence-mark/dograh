"""[.mark] U11 : les contrôles de la fenêtre « Publier vX » (« Avant de publier »).

Chaque contrôle a trois positions (éteint, prévient, bloque), réglées dans ``publication.controles``. Un contrôle ÉTEINT n'est
pas joué du tout. Par défaut, seuls les tests obligatoires et le bilan du prompt bloquent : c'est la garde d'avant
(``tests_agent/publication.py``), qui garde la main sur les messages d'erreur et l'interrupteur serveur.

⛔ On peut TOUJOURS forcer la publication (le builder et le juge ne sont pas encore éprouvés) : raison obligatoire, écrite au
journal avec la personne (``forcer``). Ce que le forçage ne contourne pas : la validité technique du graphe.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.publication import liste_vocale, reglages, sans_effet

ECHEC = "echec"
ALERTE = "alerte"
OK = "ok"
ETEINT = "eteint"
RAISON_MIN = 5
RAISON_MAX = 600

LIBELLES = {
    "tests_obligatoires": "Tests obligatoires",
    "bilan_du_prompt": "Bilan de santé du prompt",
    "liste_vocale": "Liste de contrôle vocale",
    "attaques": "Attaques",
    "garde_fous": "Garde-fous",
    "variables": "Variables des prompts",
    "briques": "Modèles configurés",
    "outils": "Outils branchés",
    "sans_effet": "Réglages sans effet",
    "sortie_d_impasse": "Sortie d'impasse",
    "deux_webhooks": "Deux webhooks",
}


class RaisonObligatoire(Exception):
    pass


def _statut(position: str, problemes: list[str]) -> str:
    if position == "eteint":
        return ETEINT
    if not problemes:
        return OK
    return ECHEC if position == "bloque" else ALERTE


async def _tests(workflow: Any, brouillon: Any, org: int) -> list[str]:
    from api.services.builder.tests_agent import publication as garde

    lignes = await garde.problemes_des_tests_obligatoires(
        org, workflow.id, getattr(brouillon, "version_number", None), garde.empreinte_du_brouillon_publie(brouillon)
    )
    return [f"{t['nom']}: {t['raison']}" for t in lignes]


async def _bilan(workflow: Any, brouillon: Any, org: int) -> list[str]:
    from api.services.builder.controle.service import controler_l_agent
    from api.services.builder.tests_agent import publication as garde

    # Comme la garde d'avant : le bilan ne garde que les agents suivis par le builder (des tests ou une trace).
    if not await garde.agent_suivi(org, workflow.id):
        return []
    controle = await controler_l_agent(workflow, org, graphe=brouillon.workflow_json)
    return [e["message"] for e in controle["elements"] if e["statut"] == "echec"]


async def liste_vocale_de(configurations: dict[str, Any]) -> list[dict[str, Any]]:
    return liste_vocale.evaluer(await liste_vocale.points(), configurations)


async def _vocale(configurations: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    resultats = await liste_vocale_de(configurations)
    return [f"{r['libelle']}" for r in resultats if r["statut"] == liste_vocale.ECART], resultats


async def _attaques(workflow: Any, brouillon: Any, org: int) -> list[str]:
    from api.services.attaques import rapport
    from api.services.builder.tests_agent import boucle

    dernier = await rapport.lire(org, workflow.id)
    if dernier is None:
        return ["No attack run on this agent yet."]
    empreinte = boucle.empreinte_du_brouillon(getattr(brouillon, "workflow_json", None), getattr(brouillon, "workflow_configurations", None))
    problemes = []
    if dernier.get("empreinte") != empreinte:
        problemes.append("The last attack run was on an earlier draft: replay it.")
    resume = dernier.get("resume") or {}
    if resume.get("a_cede"):
        problemes.append(f"{resume['a_cede']} attack(s) got through.")
    if resume.get("plausibles"):
        problemes.append(f"{resume['plausibles']} attack(s) possibly got through (not reproduced).")
    if resume.get("non_testees"):  # ⛔ jamais compté comme réussi
        problemes.append(f"{resume['non_testees']} attack(s) not tested: they do not count as held.")
    return problemes


def _garde_fous(configurations: dict[str, Any]) -> list[str]:
    securite = configurations.get("securite_conversation")
    if not isinstance(securite, dict):
        return ["No safety layer of the conversation is on."]
    actives = [
        bool((securite.get(c) or {}).get("actif"))
        for c in ("manipulation", "confidentialite", "role", "urgence")
        if isinstance(securite.get(c), dict)
    ]
    sortie = securite.get("jamais") if isinstance(securite.get("jamais"), dict) else {}
    ecoute = securite.get("ecoute") if isinstance(securite.get("ecoute"), dict) else {}
    if any(actives) or sortie.get("outils") or sortie.get("recitation") or ecoute.get("actif"):
        return []
    return ["No safety layer of the conversation is on."]


async def _lectures_de_la_liste(workflow: Any, brouillon: Any, org: int, configurations: dict[str, Any]):
    """Les étapes de la préparation et les constats « sans effet » du brouillon. Une lecture qui tombe en panne ne fait pas
    tomber la fenêtre : elle rend une liste vide."""
    from api.services import preparation

    try:
        etapes, contexte = await preparation.lire_avec_contexte(org, workflow.id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[publication] préparation en panne ({type(erreur).__name__})")
        return [], []
    definition = getattr(brouillon, "workflow_json", None) or contexte.definition
    confs = {**dict(contexte.configurations), **configurations}
    try:
        from api.services.apres_appel.reglages import lire_reglages

        webhook_pret = bool((await lire_reglages(org)).webhook.url)
    except Exception:  # noqa: BLE001
        webhook_pret = False
    constats = sans_effet.evaluer(
        definition, confs, temps_reel=contexte.temps_reel, specialiste=contexte.specialiste, webhook_mark_pret=webhook_pret
    )
    return etapes, constats


async def evaluer(workflow: Any, brouillon: Any, organisation_id: int) -> dict[str, Any]:
    """La vue de la fenêtre : un bloc par contrôle (position, statut, détail), ``bloque`` et la liste vocale en simulation."""
    # [.mark] Partie 3 (SE-12) : sans réglages propres à l'agent, ceux de l'organisation (thème « Publication »), puis ceux du code.
    from api.services.publication import defauts_org

    configurations = await defauts_org.effectives(organisation_id, getattr(brouillon, "workflow_configurations", None))
    pub = reglages.lire(configurations)
    controles: list[dict[str, Any]] = []
    vocale: list[dict[str, Any]] = []
    # [.mark] Partie 3 (SA-L3a) : une seule lecture alimente la préparation, les lignes obligatoires et les réglages sans effet.
    etapes, constats = await _lectures_de_la_liste(workflow, brouillon, organisation_id, configurations)
    par_cle = {e.controle: e for e in etapes if e.controle}
    for cle in reglages.CONTROLES:
        position = getattr(pub.controles, cle)
        problemes: list[str] = []
        if position != "eteint":  # un contrôle éteint ne joue pas
            try:
                if cle in ("variables", "briques", "outils"):
                    etape = par_cle.get(cle)
                    if etape is not None and etape.etat == "a_faire":
                        problemes = [str(m) for m in etape.manquants] or ["To do."]
                elif cle in sans_effet.CONTROLES_DES_CONSTATS:
                    problemes = [c.message() for c in constats if c.controle == cle]
                elif cle == "tests_obligatoires":
                    problemes = await _tests(workflow, brouillon, organisation_id)
                elif cle == "bilan_du_prompt":
                    problemes = await _bilan(workflow, brouillon, organisation_id)
                elif cle == "liste_vocale":
                    problemes, vocale = await _vocale(configurations)
                elif cle == "attaques":
                    problemes = await _attaques(workflow, brouillon, organisation_id)
                elif cle == "garde_fous":
                    problemes = _garde_fous(configurations)
            except Exception as erreur:  # noqa: BLE001 -- un contrôle qui tombe en panne ne se tait pas : il prévient
                logger.warning(f"[publication] contrôle {cle} en panne ({type(erreur).__name__})")
                problemes = [f"The check could not be played ({type(erreur).__name__})."]
        controles.append(
            {"cle": cle, "libelle": LIBELLES[cle], "position": position, "statut": _statut(position, problemes), "problemes": problemes[:20]}
        )
    from api.services.preparation import liste

    return {
        "version": getattr(brouillon, "version_number", None),
        "controles": controles,
        "lignes": liste.assembler(etapes, constats, controles),
        "bloque": any(c["statut"] == ECHEC for c in controles),
        "liste_vocale": vocale,
        "deploiement_actif": pub.deploiement.actif,
        "forcable": True,
    }


def raison_valide(raison: str | None) -> str:
    texte = (raison or "").strip()
    if len(texte) < RAISON_MIN:
        raise RaisonObligatoire("A reason is required to force a publication.")
    return texte[:RAISON_MAX]
