"""[.mark] Chantier Partie 1, lot 17 : la porte d'acceptation = des tests OBLIGATOIRES de l'agent, générés depuis le gabarit et la carte (D56).

Aucun contrôle de publication neuf : les tests sont rangés par le mécanisme des tests de l'agent (``builder/tests_agent/stockage.py``, origine
``code``, dossier « Générés depuis la carte ») et le contrôle existant « Tests obligatoires » (``publication/controles.py``, ``_tests``) bloque la
publication tant que l'un d'eux est rouge, jamais rejoué, ou rejoué sur un autre brouillon. Ils ne bloquent pas la création (D10).

Deux sortes :

* **sans modèle**, joués par le code (``jouer_les_tests_du_code``) sur la carte du client : chaque donnée B qui manque, chaque article (trouvé
  seul par la recherche, avec un prix), chaque brique que la carte emploie (sa règle existe), chaque zone (sa commune retrouvée par la
  vérification d'adresse), chaque mode ouvert ; c'est la partie qui doit passer du premier coup (critère de fin) ;
* **conversations** contre le modèle : la série de base (``agents/_gabarit/09``, ``serie_de_base.json``) et des conversations construites avec
  les articles du client ; elles sont jouées par le mécanisme existant (tests de l'agent), dans le budget du lot.

Un échec est RANGÉ (``famille``) : ``donnee`` (le formulaire ou la carte se corrige) ou ``capacite`` (il manque une brique ou une action).
Régénérés quand la carte ou le gabarit change (``regenerer``) ; un test généré qui n'a plus d'objet est retiré, jamais un test écrit à la main.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from api.services.builder.tests_agent import stockage

DOSSIER = "Générés depuis la carte"
ORIGINE = "code"
DONNEE, CAPACITE = "donnee", "capacite"
FAMILLES = (DONNEE, CAPACITE)
SANS_MODELE = ("donnee", "article", "brique", "zone", "mode")
SERIE = Path(__file__).parent / "restauration" / "serie_de_base.json"
CRITERE_DU_CODE = {"type": "issue", "attendue": "le contrôle du code sur la carte du client est vert"}
NB_CONVERSATIONS = 3
# Une conversation générée est jugée par le code sur ce qui se mesure (un nom d'outil ou de mécanique n'est jamais dit à voix haute : ces noms
# portent un trait bas, aucune phrase d'appel n'en contient) ; ce que la garantie du scénario dit en prose va au juge, qui informe sans bloquer.
# L'ancien critère « issue = la garantie » comparait une phrase à l'issue enregistrée de l'appel : il ne pouvait jamais être vert.
MECANIQUES_JAMAIS_DITES = ["en_plus", "valider_la_commande", "passer_a", "rendre_la_main", "signaler_un_probleme", "infos_pratiques",
                           "ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms"]


def _test(nom: str, genre: str, sujet: str, *, etape: str, version_gabarit: str, carte_version: Any = None, scenario: str | None = None,
          garantie: str | None = None) -> dict[str, Any]:
    from api.services.builder.tests_agent import verdict

    critere = {"type": "mecanique_dite", "noms": MECANIQUES_JAMAIS_DITES} if scenario else CRITERE_DU_CODE
    test: dict[str, Any] = {
        "version": stockage.VERSION,
        "nom": nom[:200],
        "description": f"Généré depuis le gabarit {version_gabarit} et la carte du client.",
        "criteres": verdict.valider_criteres([critere]),
        "critere": verdict.CRITERE_NEUTRE,
        "obligatoire": True,
        "dossier": DOSSIER,
        "origine": ORIGINE,
        "questions_juge": [garantie[:300]] if scenario and garantie else [],
        "cree_le": stockage.maintenant(),
        "cree_par": "gabarit",
        "slug": f"genere-{genre}-{stockage.slug_de(sujet)}"[:64],
        "genere": {"genre": genre, "sujet": sujet, "etape": etape, "gabarit": version_gabarit, "carte_version": carte_version, "sans_modele": genre in SANS_MODELE},
    }
    if scenario:
        test["scenario"] = {"but": scenario[:4000], "personnage": None, "ouverture": "", "tours_max": None}
    else:
        test.update({"replique": "", "historique": [], "etape": etape, "fiche": {}, "source": {"code": True}})
    return test


def _lignes(carte: Mapping[str, Any], rubrique: str) -> list[dict]:
    """Les lignes d'une rubrique de la carte ; les déclinaisons sont rangées sous leur produit (carte assemblée comme format commun)."""
    lignes = [l for l in carte.get(rubrique) or [] if isinstance(l, Mapping)]
    if rubrique == "declinaisons" and not lignes:
        lignes = [d for p in _lignes(carte, "produits") for d in p.get("declinaisons") or [] if isinstance(d, Mapping)]
    return lignes


def briques_de_la_carte(carte: Mapping[str, Any]) -> list[str]:
    """Les briques que la carte emploie : une de ses lignes porte une valeur dans un champ que la brique lit (registre des briques)."""
    from api.services.commande.briques import registre

    _charger_les_briques()
    employees = []
    for code, b in sorted(registre.BRIQUES.items()):
        if any(l.get(champ) not in (None, "", [], {}, False) for rubrique, champ in b.champs_de_la_carte for l in _lignes(carte, rubrique)):
            employees.append(code)
    return employees


def _charger_les_briques() -> None:
    import importlib
    import pkgutil

    import api.services.commande.briques as paquet

    for m in pkgutil.iter_modules(paquet.__path__):
        importlib.import_module(f"{paquet.__name__}.{m.name}")


def serie_de_base(etapes: list[str], carte: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Les scénarios de la série de base que joue cet agent : ceux de ses étapes ; la section F (formules et choix) seulement si la carte en a."""
    scenarios = json.loads(SERIE.read_text(encoding="utf-8"))["scenarios"]
    avec_formules = bool(_lignes(carte, "formules") or _lignes(carte, "groupes"))
    return [s for s in scenarios if s["etape"] in etapes and (s["section"] != "F" or avec_formules)]


def conversations_de_la_carte(carte: Mapping[str, Any], zones: list[dict], services: list[str]) -> list[tuple[str, str, str]]:
    """Des conversations construites avec les articles du client : (sujet, scénario, garantie). Aucun nom écrit ici : tout vient de la carte."""
    produits = [p for p in _lignes(carte, "produits") if not p.get("masque")]
    if not produits:
        return []
    sorties: list[tuple[str, str, str]] = []
    a, b = produits[0], produits[min(1, len(produits) - 1)]
    mode = "emporter" if "emporter" in services else ("livraison" if "livraison" in services else None)
    if mode:
        sorties.append((
            "deux-articles",
            f"Commande {'à emporter' if mode == 'emporter' else 'en livraison'} : « {a['nom']} » puis « {b['nom']} », dits en une phrase ; "
            "réponses d'un seul mot aux questions ; refuse la proposition en plus ; donne prénom et numéro quand on les lui demande.",
            "les deux articles enregistrés, avec leurs choix, au total dit par le code ; rien d'inventé",
        ))
        sorties.append((
            "question-puis-commande",
            f"Demande ce qu'il y a dans « {a['nom']} » et si c'est possible sans un ingrédient, puis le commande.",
            "la réponse vient de la carte (ou « je ne peux pas le confirmer ») ; la ligne enregistrée est juste",
        ))
    if "livraison" in services and zones:
        sorties.append((
            "livraison-zone",
            f"Commande en livraison dans la zone « {zones[0]['nom']} » : donne son adresse dans cette zone, commande « {a['nom']} » jusqu'au minimum.",
            "adresse vérifiée, zone et minimum dits par le code, commande enregistrée en livraison",
        ))
    return sorties[:NB_CONVERSATIONS]


async def _ecrire(org: int, workflow_id: int, tests: list[dict[str, Any]]) -> list[str]:
    """Écrit les tests générés de l'agent et retire ceux qui n'ont plus d'objet (seulement des tests générés : origine ``code``, dossier
    « Générés depuis la carte ») ; un test écrit à la main n'est jamais touché."""
    voulus = {t["slug"]: t for t in tests}
    for existant in await stockage.lister(org, workflow_id):
        if existant.get("dossier") == DOSSIER and existant.get("origine") == ORIGINE and existant.get("genere") and existant["slug"] not in voulus:
            await stockage.supprimer(org, workflow_id, existant["slug"])
    for t in tests:
        await stockage.ecrire(org, workflow_id, t)
    return sorted(voulus)


async def generer(org: int, application: Mapping[str, Any], connexion, *, b_manquer: list[str]) -> int:
    """Écrit les tests obligatoires générés de chaque agent du groupe ; rend leur nombre."""
    from api.db.bases_clients.restauration_carte import carte_du_restaurant
    from api.services.gabarits import formulaire as F

    agents = {k: v for k, v in application["agents"].items() if not k.startswith("_")}
    version = f"{application['gabarit_nom']}@{application['gabarit_version']}"
    etab = application["formulaire"]["etablissement_id"]
    carte = await carte_du_restaurant(connexion, etab)
    zones = [dict(z) for z in await connexion.fetch("SELECT id, nom, communes FROM mark.resto_zone WHERE site_id = $1 ORDER BY ordre, id", etab)]
    services = list(application["formulaire"].get("services") or [])
    total = 0
    par_agent: dict[str, list[dict]] = {e: [] for e in agents}
    for cle in b_manquer:
        par_agent["accueil"].append(_test(f"Donnée à renseigner : {F.DONNEES[cle].libelle}", "donnee", cle, etape="accueil", version_gabarit=version))
    if "commande" in agents:
        t = par_agent["commande"]
        for p in _lignes(carte, "produits"):
            if not p.get("masque"):
                t.append(_test(f"Article de la carte : {p['nom']}", "article", p["id"], etape="commande", version_gabarit=version, carte_version=carte.get("version")))
        for fo in _lignes(carte, "formules"):
            t.append(_test(f"Formule de la carte : {fo['nom']}", "article", fo["id"], etape="commande", version_gabarit=version, carte_version=carte.get("version")))
        for code in briques_de_la_carte(carte):
            t.append(_test(f"Brique employée par la carte : {code}", "brique", code, etape="commande", version_gabarit=version, carte_version=carte.get("version")))
        for z in zones:
            t.append(_test(f"Zone de livraison : {z['nom']}", "zone", str(z["id"]), etape="commande", version_gabarit=version))
        for mode in services:
            t.append(_test(f"Mode ouvert : {mode}", "mode", mode, etape="commande", version_gabarit=version))
        for sujet, scenario, garantie in conversations_de_la_carte(carte, zones, services):
            t.append(_test(f"Conversation sur la carte : {sujet}", "conversation", sujet, etape="commande", version_gabarit=version, scenario=scenario, garantie=garantie))
    for etape in agents:
        for s in serie_de_base([etape], carte):
            par_agent[etape].append(
                _test(f"Série de base {s['id']} : {s['scenario']}", "serie_de_base", s["id"], etape=etape, version_gabarit=version, scenario=s["scenario"], garantie=s["garantie"])
            )
    for etape, tests in par_agent.items():
        total += len(await _ecrire(org, agents[etape], tests))
    return total


# --------------------------------------------------------------------------- les tests du code (sans modèle)


async def _verdict_du_test(test: Mapping[str, Any], connexion, etab: int, carte: Mapping[str, Any], formulaire: Mapping[str, Any]) -> tuple[bool, str | None, str]:
    """(vert, famille de l'échec, raison) d'un test généré sans modèle, sur la carte et la base du client."""
    from api.db.bases_clients.restauration_client import chercher_dans_la_liste
    from api.db.bases_clients.restauration_formulaire import faits_de_l_etablissement
    from api.db.bases_clients.restauration_zone import zone_de_l_etablissement
    from api.services.commande.briques import registre
    from api.services.gabarits import formulaire as F

    g = test["genere"]
    genre, sujet = g["genre"], g["sujet"]
    if genre == "donnee":
        controle = F.controler(formulaire, await faits_de_l_etablissement(connexion, etab))
        return (sujet not in controle.b_manquer, DONNEE, f"donnée B manquante : {sujet}")
    if genre == "article":
        ligne = next((l for r in ("produits", "formules") for l in _lignes(carte, r) if l["id"] == sujet), None)
        if ligne is None:
            return False, DONNEE, "l'article n'est plus sur la carte"
        # Son nom dit tel quel le retrouve : retenu, ou parmi les choix d'une question (« le kebab ou le menu kebab ? ») ; jamais introuvable.
        trouve = await chercher_dans_la_liste(connexion, "carte", ligne["nom"], etab)
        candidats = {c.get("id") if isinstance(c, Mapping) else c for c in trouve.faits.get("candidats") or []}
        if trouve.faits.get("retenu") != sujet and sujet not in candidats:
            return False, DONNEE, f"son nom ne retrouve pas l'article ({trouve.statut}) : nom à corriger ou synonyme à poser"
        prix = [ligne.get("prix")] + [d.get("prix") for d in ligne.get("declinaisons") or [] if isinstance(d, Mapping)]
        if not any(isinstance(x, int) and x >= 0 for x in prix):
            return False, DONNEE, "aucun prix"
        return True, None, ""
    if genre == "brique":
        _charger_les_briques()
        b = registre.BRIQUES.get(sujet)
        ok = b is not None and (b.regle is not None or b.alias_de is not None)
        return ok, CAPACITE, f"la brique {sujet} n'a pas de règle : une nouvelle brique est à écrire"
    if genre == "zone":
        zone = await zone_de_l_etablissement(connexion, etab, int(sujet))
        if zone is None:
            return False, DONNEE, "la zone n'existe plus"
        ok = bool(zone.get("communes") or zone.get("rayon_km") or zone.get("cercle_km")) and zone.get("minimum") is not None
        return ok, DONNEE, "la zone n'a ni commune ni rayon, ou pas de minimum"
    if genre == "mode":
        ouvert = await connexion.fetchval("SELECT ouvert FROM mark.resto_reglage_type WHERE site_id = $1 AND type = $2", etab, sujet)
        return bool(ouvert), DONNEE, f"le mode {sujet} n'est pas ouvert dans les réglages de l'établissement"
    return False, CAPACITE, f"genre de test inconnu : {genre}"


def ranger_l_echec(famille: str | None) -> str:
    """Un échec est rangé : donnée (le formulaire se corrige) ou capacité (une brique ou une action manque). Rien d'autre."""
    if famille not in FAMILLES:
        raise ValueError(f"famille d'échec inconnue : {famille!r}")
    return famille


async def serie_jouee_pour_le_gabarit(org: int, application: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """La série de base est un test du GABARIT (sa version), jouée une fois contre le modèle sur un des agents installés de cette version (le
    témoin) : ``{(étape, slug): exécution verte}`` de ce que le modèle a joué et réussi. Un agent installé depuis la même version la lit au lieu
    de la rejouer ; une nouvelle version du gabarit repart de zéro (le champ ``gabarit`` du test porte la version)."""
    from api.services.gabarits.diffusion import _toutes_les_applications

    version = f"{application['gabarit_nom']}@{application['gabarit_version']}"
    jouees: dict[tuple[str, str], dict[str, Any]] = {}
    for autre in await _toutes_les_applications(application["gabarit_nom"], org):
        if autre["gabarit_version"] != application["gabarit_version"]:
            continue
        for etape, wid in autre["agents"].items():
            if etape.startswith("_"):
                continue
            for test in await stockage.lister(org, wid):
                g = test.get("genere") or {}
                if g.get("genre") != "serie_de_base" or g.get("gabarit") != version:
                    continue
                derniere = await stockage.derniere_execution(org, wid, test["slug"])
                if derniere and derniere.get("statut") == "ok" and not derniere.get("par"):  # jouée par le modèle (``par`` : le code ou le gabarit)
                    jouees.setdefault((etape, test["slug"]), {**derniere, "temoin": wid})
    return jouees


async def jouer_les_tests_du_code(org: int, application: Mapping[str, Any]) -> dict[str, Any]:
    """Joue les tests générés sans modèle de chaque agent sur la carte du client et range chaque exécution avec la version et l'empreinte du
    brouillon (le contrôle « Tests obligatoires » les lit tels quels). Rend ``{verts, rouges: [{agent, slug, famille, raison}]}``."""
    from api.db import db_client
    from api.db.bases_clients.restauration_carte import carte_du_restaurant
    from api.services.builder.tests_agent import boucle
    from api.services.gabarits.installation import _base_du_client

    agents = {k: v for k, v in application["agents"].items() if not k.startswith("_")}
    etab = application["formulaire"]["etablissement_id"]
    connexion = await _base_du_client(org)
    verts, rouges = 0, []
    jouees = await serie_jouee_pour_le_gabarit(org, application)
    try:
        carte = await carte_du_restaurant(connexion, etab)
        for etape, wid in agents.items():
            brouillon = await db_client.get_draft_version(wid)
            version = getattr(brouillon, "version_number", None)
            emp = boucle.empreinte_du_brouillon(getattr(brouillon, "workflow_json", None), getattr(brouillon, "workflow_configurations", None))
            for test in await stockage.lister(org, wid):
                g = test.get("genere") or {}
                if g.get("genre") == "serie_de_base" and (etape, test["slug"]) in jouees:
                    temoin = jouees[(etape, test["slug"])]["temoin"]
                    await stockage.ajouter_un_resultat(org, wid, test["slug"], {
                        "le": stockage.maintenant(), "version": version, "empreinte": emp, "statut": "ok", "reussis": 1, "total": 1, "par": "gabarit",
                        "temoin": temoin,
                    })
                    verts += 1
                    continue
                if not g.get("sans_modele"):
                    continue
                ok, famille, raison = await _verdict_du_test(test, connexion, etab, carte, application["formulaire"])
                execution = {"le": stockage.maintenant(), "version": version, "empreinte": emp, "statut": "ok" if ok else "echec",
                             "reussis": 1 if ok else 0, "total": 1, "par": "code"}
                if not ok:
                    execution["famille"] = ranger_l_echec(famille)
                    execution["raison"] = raison
                    rouges.append({"agent": etape, "slug": test["slug"], "famille": famille, "raison": raison})
                else:
                    verts += 1
                await stockage.ajouter_un_resultat(org, wid, test["slug"], execution)
    finally:
        await connexion.close()
    return {"verts": verts, "rouges": rouges}


async def jouer_les_tests_du_code_de(org: int, workflow_id: int) -> dict[str, Any] | None:
    """Les tests du code du groupe dont ``workflow_id`` est un agent (``None`` si l'agent n'est pas installé depuis un gabarit)."""
    from api.db import db_client

    application = await db_client.application_de(org, workflow_id)
    return None if application is None else await jouer_les_tests_du_code(org, application)


async def regenerer(org: int, workflow_id: int) -> int:
    """La carte ou le gabarit a changé : les tests générés de l'agent installé sont réécrits (ceux qui n'ont plus d'objet sont retirés)."""
    from api.db import db_client
    from api.db.bases_clients.restauration_formulaire import faits_de_l_etablissement
    from api.services.gabarits import formulaire as F
    from api.services.gabarits.installation import _base_du_client

    application = await db_client.application_de(org, workflow_id)
    if application is None:
        return 0
    connexion = await _base_du_client(org)
    try:
        faits = await faits_de_l_etablissement(connexion, application["formulaire"]["etablissement_id"])
        return await generer(org, application, connexion, b_manquer=F.controler(application["formulaire"], faits).b_manquer)
    finally:
        await connexion.close()
