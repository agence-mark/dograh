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
from api.services.publication.probleme import Probleme, detail_de

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
    "valeur_en_dur": "Valeur écrite en dur",
    "verbe_ecran": "Verbe d'écran",
    "action_sans_outil": "Action promise sans outil",
    "sortie_non_citee": "Sortie non citée",
    "poids_agent": "Poids de l'agent",
    "annonce_ia": "Annonce « vous parlez à une IA »",
    "etiquettes": "Étiquettes des prompts",
    "blocs_a_jour": "Blocs à jour",
}

# [.mark] L3e : contrôles dont la position est FIXE (ils ne sont pas dans ``reglages.CONTROLES`` : aucun réglage ne les éteint).
# Clôture, lot B (D1) : l'annonce « vous parlez à une IA » en est sortie, c'est un contrôle réglable comme les autres.
CONTROLES_FIXES: dict[str, str] = {}
# [.mark] Lot 8 (décision d'Evan du 04/11) : une étiquette cassée bloque TOUJOURS (aucun réglage ne l'assouplit). Lot 22 : un bloc
# resté sur sa version alors qu'une Recette plus récente existe est un conseil, jamais un blocage.
CONTROLES_FIXES["etiquettes"] = "bloque"
CONTROLES_FIXES["blocs_a_jour"] = "previent"


async def problemes_des_etiquettes(org: int, brouillon: Any) -> tuple[list[str] | None, list[str] | None]:
    """(bloquants, conseils) : les étiquettes d'objets du brouillon, en phrases courtes (étape · message). ``None`` : sans objet
    (aucune étiquette d'objet, ou aucun bloc) ; la ligne ne se montre alors pas dans « Prêt à publier »."""
    from api.services.etiquettes_prompt import familles as f
    from api.services.etiquettes_prompt.catalogue import problemes_du_brouillon, textes_du_brouillon

    graphe = getattr(brouillon, "workflow_json", None)
    configs = getattr(brouillon, "workflow_configurations", None)
    textes = [t for _c, _n, _e, t, _d in textes_du_brouillon(graphe if isinstance(graphe, dict) else None, configs if isinstance(configs, dict) else None)]
    if not textes:
        return None, None
    a_des_blocs = any(e.famille == f.BLOC for t in textes for e in f.etiquettes_de(t))
    bloquants: list[str] = []
    conseils: list[str] = []
    for p in await problemes_du_brouillon(org, brouillon):
        texte = f"{p.etape or 'Réglages'} · {p.message}"
        (bloquants if p.bloquant else conseils).append(texte)
    return bloquants, (conseils if a_des_blocs else None)


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
    return [Probleme(f"{t['nom']}: {t['raison']}", t.get("code"), nom=t["nom"], **(t.get("parametres") or {})) for t in lignes]


async def _bilan(workflow: Any, brouillon: Any, org: int, controle_de_l_agent: Any) -> list[str]:
    from api.services.builder.controle.regles import CODES_DE_REDACTION
    from api.services.builder.tests_agent import publication as garde

    # Comme la garde d'avant : le bilan ne garde que les agents suivis par le builder (des tests ou une trace).
    if not await garde.agent_suivi(org, workflow.id):
        return []
    controle = await controle_de_l_agent()
    # Les contrôles de rédaction ont leur propre position et leur propre ligne : le bilan ne les compte pas deux fois.
    return [
        Probleme(e["message"], e["code"], etape=e.get("etape"), forme="suffixe", **(e.get("parametres") or {}))
        for e in controle["elements"]
        if e["statut"] == "echec" and e["code"] not in CODES_DE_REDACTION
    ]


def _de_redaction(controle: dict[str, Any], cle: str) -> list[str]:
    """Les défauts d'un contrôle de rédaction (K1 à K5) en phrases courtes : étape · message."""
    return [
        Probleme(
            f"{e['etape'] or 'Agent'} · {e['message']}",
            e["code"],
            etape=e.get("etape"),
            forme="prefixe",
            **(e.get("parametres") or {}),
        )
        for e in controle["elements"]
        if e["code"] == cle
    ]


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
        return [Probleme("No attack run on this agent yet.", "attaque_jamais_jouee")]
    empreinte = boucle.empreinte_du_brouillon(getattr(brouillon, "workflow_json", None), getattr(brouillon, "workflow_configurations", None))
    problemes = []
    if dernier.get("empreinte") != empreinte:
        problemes.append(Probleme("The last attack run was on an earlier draft: replay it.", "attaque_brouillon_change"))
    resume = dernier.get("resume") or {}
    if resume.get("a_cede"):
        problemes.append(Probleme(f"{resume['a_cede']} attack(s) got through.", "attaque_a_cede", nombre=resume["a_cede"]))
    if resume.get("plausibles"):
        problemes.append(Probleme(f"{resume['plausibles']} attack(s) possibly got through (not reproduced).", "attaque_plausible", nombre=resume["plausibles"]))
    if (dernier.get("controle_du_juge") or {}).get("ok") is False:  # sous-lot 4 : le juge a vu une attaque dans une demande normale
        problemes.append(Probleme("The judge flagged a harmless request as an attack: read the verdicts of this run with care.", "attaque_juge_alarmiste"))
    if resume.get("non_testees"):  # ⛔ jamais compté comme réussi
        problemes.append(Probleme(f"{resume['non_testees']} attack(s) not tested: they do not count as held.", "attaque_non_testee", nombre=resume["non_testees"]))
    return problemes


def _accueil_ecrit(graphe: Any) -> bool:
    """Le départ de l'agent a-t-il un accueil écrit (en texte) ?"""
    for noeud in (graphe.get("nodes") if isinstance(graphe, dict) else None) or []:
        donnees = noeud.get("data") if isinstance(noeud, dict) else None
        if isinstance(donnees, dict) and noeud.get("type") == "startCall":
            return donnees.get("greeting_type", "text") == "text" and bool(str(donnees.get("greeting") or "").strip())
    return False


def _annonce_ia(configurations: dict[str, Any], *, temps_reel: bool = False, graphe: Any = None) -> list[str]:
    """L'annonce « vous parlez à une IA » (clôture, lot B, D1 et D2) : le contrôle prévient quand l'annonce est éteinte ou vidée, et quand une voix temps
    réel n'a pas d'accueil écrit (l'ouverture vient alors du fournisseur : rien n'est injecté, la phrase s'écrit dans le prompt)."""
    from api.services.phrases.catalogue import ANNONCE_IA
    from api.services.phrases.regles import resoudre

    phrase = resoudre(ANNONCE_IA, reglages_agent=configurations, reglages_principal=configurations)
    if phrase is None or not phrase.active or not any(v.strip() for v in phrase.variantes):
        return [Probleme("The announcement « you are talking to an AI » is off or empty: callers are not told they are talking to an AI.", "annonce_ia_eteinte")]
    if temps_reel and not _accueil_ecrit(graphe):
        return [
            Probleme(
                "Realtime voice without a written greeting: the announcement « you are talking to an AI » cannot be imposed word for word. "
                "Write it in the prompt.",
                "annonce_ia_temps_reel",
            )
        ]
    return []


def _garde_fous(configurations: dict[str, Any]) -> list[str]:
    securite = configurations.get("securite_conversation")
    if not isinstance(securite, dict):
        return [Probleme("No safety layer of the conversation is on.", "garde_fous_aucun")]
    actives = [
        bool((securite.get(c) or {}).get("actif"))
        for c in ("manipulation", "confidentialite", "role", "urgence")
        if isinstance(securite.get(c), dict)
    ]
    sortie = securite.get("jamais") if isinstance(securite.get("jamais"), dict) else {}
    ecoute = securite.get("ecoute") if isinstance(securite.get("ecoute"), dict) else {}
    urgence = securite.get("garde_urgence") if isinstance(securite.get("garde_urgence"), dict) else {}
    if any(actives) or sortie.get("outils") or sortie.get("recitation") or ecoute.get("actif") or urgence.get("actif"):
        return []
    return [Probleme("No safety layer of the conversation is on.", "garde_fous_aucun")]


async def _lectures_de_la_liste(workflow: Any, brouillon: Any, org: int, configurations: dict[str, Any], memo: dict[str, Any] | None = None):
    """Les étapes de la préparation et les constats « sans effet » du brouillon. Une lecture qui tombe en panne ne fait pas
    tomber la fenêtre : elle rend une liste vide. ``memo`` reçoit ``temps_reel`` (une seule lecture alimente aussi le contrôle de l'annonce)."""
    from api.services import preparation

    try:
        etapes, contexte = await preparation.lire_avec_contexte(org, workflow.id)
        if memo is not None:
            memo["temps_reel"] = bool(contexte.temps_reel)
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
    memo: dict[str, Any] = {}
    etapes, constats = await _lectures_de_la_liste(workflow, brouillon, organisation_id, configurations, memo)
    # [.mark] Lot « façon Tala par motif » : UNE lecture du prompt alimente le bilan et les cinq contrôles de rédaction.

    async def controle_de_l_agent() -> dict[str, Any]:
        if "controle" not in memo:
            from api.services.builder.controle.service import controler_l_agent

            memo["controle"] = await controler_l_agent(
                workflow, organisation_id, graphe=brouillon.workflow_json, configurations=configurations
            )
        return memo["controle"]

    par_cle = {e.controle: e for e in etapes if e.controle}
    for cle in reglages.CONTROLES:
        position = getattr(pub.controles, cle)
        problemes: list[str] = []
        if position != "eteint":  # un contrôle éteint ne joue pas
            try:
                if cle in ("variables", "briques", "outils"):
                    etape = par_cle.get(cle)
                    if etape is not None and etape.etat == "a_faire":
                        problemes = [str(m) for m in etape.manquants] or [Probleme("To do.", "a_faire")]
                elif cle in sans_effet.CONTROLES_DES_CONSTATS:
                    problemes = [Probleme(c.message(), f"effet_{c.cle}", noms=", ".join(c.noms)) for c in constats if c.controle == cle]
                elif cle == "tests_obligatoires":
                    problemes = await _tests(workflow, brouillon, organisation_id)
                elif cle == "bilan_du_prompt":
                    problemes = await _bilan(workflow, brouillon, organisation_id, controle_de_l_agent)
                elif cle in reglages.CONTROLES_DE_REDACTION:
                    problemes = _de_redaction(await controle_de_l_agent(), cle)
                elif cle == "liste_vocale":
                    problemes, vocale = await _vocale(configurations)
                elif cle == "attaques":
                    problemes = await _attaques(workflow, brouillon, organisation_id)
                elif cle == "garde_fous":
                    problemes = _garde_fous(configurations)
                elif cle == "annonce_ia":
                    problemes = _annonce_ia(configurations, temps_reel=bool(memo.get("temps_reel")), graphe=getattr(brouillon, "workflow_json", None))
            except Exception as erreur:  # noqa: BLE001 -- un contrôle qui tombe en panne ne se tait pas : il prévient
                logger.warning(f"[publication] contrôle {cle} en panne ({type(erreur).__name__})")
                problemes = [Probleme(f"The check could not be played ({type(erreur).__name__}).", "controle_en_panne", erreur=type(erreur).__name__)]
        controles.append(
            {
                "cle": cle,
                "libelle": LIBELLES[cle],
                "position": position,
                "statut": _statut(position, problemes),
                "problemes": problemes[:20],
                "details": [detail_de(p) for p in problemes[:20]],
            }
        )
    etiquettes, conseils_blocs = await problemes_des_etiquettes(organisation_id, brouillon)
    for cle, position in CONTROLES_FIXES.items():
        problemes = []
        if cle in ("etiquettes", "blocs_a_jour"):
            trouves = etiquettes if cle == "etiquettes" else conseils_blocs
            if trouves is None:  # sans objet (aucune étiquette, aucun bloc) : le contrôle n'est pas joué, aucune ligne
                continue
            problemes = trouves
        controles.append({"cle": cle, "libelle": LIBELLES[cle], "position": position, "statut": _statut(position, problemes), "problemes": problemes, "details": [detail_de(p) for p in problemes]})
    from api.services.preparation import liste

    return {
        "version": getattr(brouillon, "version_number", None),
        "controles": controles,
        "lignes": liste.assembler(etapes, constats, controles),
        "bloque": any(c["statut"] == ECHEC for c in controles),
        "liste_vocale": vocale,
        # Le bilan de santé du prompt (étape, extrait) et le poids de l'agent, pour les sections de la fenêtre.
        **await _sections_de_redaction(controle_de_l_agent, brouillon, configurations, pub),
        "deploiement_actif": pub.deploiement.actif,
        "forcable": True,
    }


async def _sections_de_redaction(controle_de_l_agent: Any, brouillon: Any, configurations: dict[str, Any], pub: Any) -> dict[str, Any]:
    """``defauts_du_prompt`` : chaque défaut de rédaction avec son étape, son extrait et l'identifiant de l'étape (pour « Régler »).
    ``poids`` : une ligne par étape, du plus lourd au plus léger, avec les seuils réglés dans Briques (``None`` = aucun seuil)."""
    from api.services.builder.controle import regles
    from api.services.builder.controle.service import _seuil

    graphe = getattr(brouillon, "workflow_json", None)
    graphe = graphe if isinstance(graphe, dict) else {"nodes": [], "edges": []}
    identifiants: dict[str, str] = {}
    for n in graphe.get("nodes") or []:
        if isinstance(n, dict):
            identifiants.setdefault(str((n.get("data") or {}).get("name") or n.get("id")), str(n.get("id")))
    defauts: list[dict[str, Any]] = []
    try:
        controle = await controle_de_l_agent()
        defauts = [
            {**e, "noeud_id": identifiants.get(e["etape"] or "")}
            for e in controle["elements"]
            if e["code"] in regles.CODES_DE_REDACTION and e["code"] != regles.K5
        ]
    except Exception as erreur:  # noqa: BLE001 -- la fenêtre ne tombe pas pour une section
        logger.warning(f"[publication] bilan de rédaction en panne ({type(erreur).__name__})")
    return {
        "defauts_du_prompt": defauts,
        "poids": {
            "actif": pub.controles.poids_agent != "eteint",
            "plafond_prompt": _seuil(configurations.get("cerveau_plafond_prompt")),
            "poids_max": _seuil(configurations.get("cerveau_poids_max")),
            "etapes": [p.en_json() for p in regles.poids_par_etape(graphe)],
        },
    }


def raison_valide(raison: str | None) -> str:
    texte = (raison or "").strip()
    if len(texte) < RAISON_MIN:
        raise RaisonObligatoire("A reason is required to force a publication.")
    return texte[:RAISON_MAX]
