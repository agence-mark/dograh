"""[.mark] Chantier Partie 1, lot 18 : Casa Italia et les restaurants de démo installés par le script et le formulaire du lot 17 (D41, D47).

Les quatre formulaires du restaurateur vivent dans le labo (``Labo-agent-vocal/agents/<client>/formulaire.json``, écrits par
``plans/agent-qui-travaille-partie-1/outils/ecrire_formulaires_l18.py`` depuis les fiches, la caisse de démo et les cartes de démo du banc A) ;
chacun est contrôlé, installé par ``installer_un_restaurant`` dans une base de test, et sa porte d'acceptation (les tests générés sans modèle)
est jouée. Aucune requête au modèle : les conversations de la porte se jouent sur l'environnement chantier (journal du lot).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.services.gabarits import formulaire as F
from api.services.gabarits import installation as I
from api.services.gabarits import tests_generes as TG
from api.services.gabarits.formulaire import MOYENS
from api.tests.mark.partie_1.test_l17_gabarit import _client_avec_sa_base
from api.tests.mark.test_base_client import base_essai  # noqa: F401

QG = Path(__file__).resolve().parents[6]
AGENTS = QG / "Labo-agent-vocal" / "agents"
# dossier du labo -> (prénom de l'assistante, nom, type) : ceux des textes prouvés (``outils/installer_chantier/passer_aux_textes.QUI``).
DEMOS = {
    "casa-italia-restauration": ("Giulia", "Casa Italia", "une pizzeria"),
    "etoile-d-or": ("Lina", "L'Étoile d'Or", "un restaurant asiatique"),
    "kebab-demo": ("Samia", "Kebab de démo", "un kebab"),
    "lusitalia": ("Lucia", "Lusitalia Pont-Sainte-Maxence", "une pizzeria de l'enseigne Lusitalia"),
}
pytestmark = pytest.mark.skipif(not AGENTS.is_dir(), reason="le labo n'est pas sur ce poste")


def formulaire_de(dossier: str) -> dict:
    return json.loads((AGENTS / dossier / "formulaire.json").read_text(encoding="utf-8"))


# L18-01
@pytest.mark.parametrize("dossier", sorted(DEMOS))
def test_quatre_formulaires_valides(dossier):
    """Chaque formulaire passe le contrôle : A complet, B complet (la carte y est), aucune règle inconnue ; son prénom, son nom et son type sont ceux
    des textes prouvés ; ses moyens de paiement sont ceux du module."""
    f = formulaire_de(dossier)
    c = F.controler(f)
    assert c.a_manquer == [] and c.b_manquer == [] and c.signalements == [], (c.a_manquer, c.b_manquer)
    assert (f["prenom_assistante"], f["nom_etablissement"], f["type_d_etablissement"]) == DEMOS[dossier]
    assert f["prenom_assistante"] != F.PAR_DEFAUT["prenom_assistante"]
    assert set(f["moyens_paiement"]) <= set(MOYENS)
    assert f["carte"]["produits"]


def test_la_carte_a_la_livraison_est_un_moyen_du_formulaire():
    """Rouge connu (L18-01) : le formulaire disait « carte_a_la_livraison », que le module ne connaît pas (il écrit ``carte_livraison``) : Casa et
    Lusitalia rendaient « moyens de paiement » absent."""
    avec = {**formulaire_de("lusitalia")}
    assert "carte_livraison" in avec["moyens_paiement"]
    assert F.controler(avec).b_manquer == []
    assert F.controler({**avec, "moyens_paiement": ["carte_a_la_livraison"]}).b_manquer == ["moyens_paiement"]


# L18-02
async def test_porte_banc_a_quatre_cartes(db_session, base_essai, monkeypatch):  # noqa: F811
    """Les quatre restaurants s'installent l'un après l'autre dans la même organisation par le script ; sans donnée B qui manque, tous les tests
    générés sans modèle de chaque agent sont verts (articles, briques, zones, modes : la carte du client est sans défaut) ; les conversations,
    elles, restent à jouer contre le modèle (le contrôle « Tests obligatoires » les attend : la porte n'est verte qu'après leur rejeu)."""
    from api.services.builder.tests_agent import stockage

    cas = await _client_avec_sa_base(db_session, base_essai)
    groupes = {}
    for dossier in DEMOS:
        r = await I.installer_un_restaurant(cas.user, cas.org, formulaire_de(dossier), nom_base=base_essai)
        assert r["echec"] is None, (dossier, r["echec"])
        assert r["etape_6"]["b_manquer"] == [], dossier
        groupes[dossier] = r["application"]
    assert len({a["workflow_id"] for a in groupes.values()}) == len(DEMOS)
    for dossier, application in groupes.items():
        bilan = await TG.jouer_les_tests_du_code(cas.org, application)
        assert bilan["rouges"] == [], (dossier, bilan["rouges"][:3])
        assert bilan["verts"] > 0
        etapes = {k for k in application["agents"] if not k.startswith("_")}
        assert "commande" in etapes and ("reservation" in etapes) == ("prise_de_reservation" in formulaire_de(dossier)["missions"])
        for wid in (application["agents"][e] for e in etapes):
            attendus = [t for t in await stockage.lister(cas.org, wid) if not t["genere"]["sans_modele"]]
            assert all(t["obligatoire"] for t in attendus)


# L18-03
ANCIENS = (
    "L'outil propose un article en plus : … Accord : en_plus vrai … ; refus : en_plus faux.",
    "Elle approuve, quels que soient ses mots : {valider_la_commande} avec confirmer vrai.",
    "Passe `sens` et `mots` à la réservation.",
)
K01 = re.compile(r"\ben_plus\b|\bconfirmer (?:vrai|faux)\b|`(?:sens|mots)`|\bavec (?:sens|mots)\b")


def test_k01_reconnu_dans_les_anciens_textes():
    """Rouge connu : l'expression qui cherche les noms de champs retirés du contrat reconnaît les prompts de production d'avant (audit des rustines, K01)."""
    assert all(K01.search(t) for t in ANCIENS)


async def test_k01_disparu(db_session, base_essai):  # noqa: F811
    """Aucun texte des agents installés (instruction générale, étapes, descriptions des outils) ne nomme ``en_plus``, ``confirmer``, ``sens`` ni
    ``mots`` comme champ : le modèle ne reçoit que la fiche à cases du contrat actuel."""
    cas = await _client_avec_sa_base(db_session, base_essai)
    for dossier in DEMOS:
        r = await I.installer_un_restaurant(cas.user, cas.org, formulaire_de(dossier), nom_base=base_essai)
        assert r["echec"] is None, r["echec"]
        for etape, wid in {k: v for k, v in r["application"]["agents"].items() if not k.startswith("_")}.items():
            brouillon = await db_client.get_draft_version(wid)
            texte = json.dumps(brouillon.workflow_json, ensure_ascii=False)
            assert K01.findall(texte) == [], (dossier, etape, K01.findall(texte)[:3])


# L18-05 : le contrôle du prompt de la fenêtre « Publier » ne rejuge pas un texte prouvé du gabarit
CODES_DU_TEXTE_PROUVE = {"nom_d_outil_dans_le_texte", "outil_sans_consigne_d_echec"}


async def test_texte_du_gabarit_inchange_passe_le_controle_du_prompt(db_session, base_essai):  # noqa: F811
    """Un agent installé par le script porte les textes prouvés du gabarit (noms d'outils écrits en clair, retour de l'outil pour consigne d'échec) :
    le contrôle du prompt ne les bloque pas tant que personne n'y a touché ; dès qu'un mot change, le texte est jugé comme les autres."""
    from api.services.builder.controle.service import controler_l_agent

    cas = await _client_avec_sa_base(db_session, base_essai)
    r = await I.installer_un_restaurant(cas.user, cas.org, formulaire_de("kebab-demo"), nom_base=base_essai)
    assert r["echec"] is None, r["echec"]
    wid = r["application"]["agents"]["commande"]
    workflow = await db_client.get_workflow(wid, organization_id=cas.org)
    brouillon = await db_client.get_draft_version(wid)

    def codes(resultat):
        return {b["code"] for b in resultat["bloquants"]} & CODES_DU_TEXTE_PROUVE

    assert codes(await controler_l_agent(workflow, cas.org, graphe=brouillon.workflow_json)) == set()

    retouche = json.loads(json.dumps(brouillon.workflow_json))
    etape = next(n for n in retouche["nodes"] if n["data"].get("tool_uuids") and (n["data"].get("prompt") or ""))
    etape["data"]["prompt"] += "\nTu appelles fiche pour chaque réponse."
    assert "nom_d_outil_dans_le_texte" in codes(await controler_l_agent(workflow, cas.org, graphe=retouche))


# L18-06 : la série de base est un test du gabarit, jouée une fois
async def test_serie_de_base_jouee_une_fois_pour_le_gabarit(db_session, base_essai):  # noqa: F811
    """La série de base se joue contre le modèle sur un agent installé (le témoin) ; un autre restaurant installé depuis la même version la lit au
    lieu de la rejouer (``par`` : gabarit) ; un test du témoin rouge, ou joué par le code seulement, ne vaut rien pour les autres."""
    from api.services.builder.tests_agent import boucle, stockage

    cas = await _client_avec_sa_base(db_session, base_essai)
    temoin = (await I.installer_un_restaurant(cas.user, cas.org, formulaire_de("kebab-demo"), nom_base=base_essai))["application"]
    autre = (await I.installer_un_restaurant(cas.user, cas.org, formulaire_de("etoile-d-or"), nom_base=base_essai))["application"]

    async def series(application):
        return [(e, w, t) for e, w in application["agents"].items() if not e.startswith("_") for t in await stockage.lister(cas.org, w)
                if t["genere"]["genre"] == "serie_de_base"]

    async def jamais_jouees(application):
        return [await stockage.derniere_execution(cas.org, w, t["slug"]) for _e, w, t in await series(application)] == [None] * len(await series(application))

    async def jouer_sur_le_temoin(statut):
        for _e, wid, t in await series(temoin):
            b = await db_client.get_draft_version(wid)
            await stockage.ajouter_un_resultat(cas.org, wid, t["slug"], {"le": stockage.maintenant(), "version": b.version_number, "statut": statut,
                                                                        "empreinte": boucle.empreinte_du_brouillon(b.workflow_json, b.workflow_configurations),
                                                                        "reussis": int(statut == "ok"), "total": 1})

    await TG.jouer_les_tests_du_code(cas.org, autre)
    assert await series(autre) and await jamais_jouees(autre)
    await jouer_sur_le_temoin("echec")
    await TG.jouer_les_tests_du_code(cas.org, autre)
    assert await jamais_jouees(autre)
    await jouer_sur_le_temoin("ok")
    await TG.jouer_les_tests_du_code(cas.org, temoin)  # la porte du témoin ne lui fait pas perdre ce que le modèle a joué
    await TG.jouer_les_tests_du_code(cas.org, temoin)
    await TG.jouer_les_tests_du_code(cas.org, autre)
    for etape, wid, t in await series(autre):
        derniere = await stockage.derniere_execution(cas.org, wid, t["slug"])
        assert derniere and derniere["statut"] == "ok" and derniere["par"] == "gabarit", (etape, t["slug"])


# L18-07 : une conversation générée peut être verte (l'ancien critère comparait une phrase à l'issue de l'appel)
async def test_conversations_generees_jugees_sur_ce_qui_se_mesure(db_session, base_essai):  # noqa: F811
    """Les tests joués par le modèle (série de base, conversations) ont un critère que le code sait vérifier (aucun nom de mécanique dit) ; leur
    garantie en prose va au juge, qui n'a pas de voix bloquante. Jamais le critère « issue » d'une phrase, qu'aucun appel ne peut égaler."""
    from api.services.builder.tests_agent import stockage

    cas = await _client_avec_sa_base(db_session, base_essai)
    a = (await I.installer_un_restaurant(cas.user, cas.org, formulaire_de("kebab-demo"), nom_base=base_essai))["application"]
    vus = 0
    for wid in (w for e, w in a["agents"].items() if not e.startswith("_")):
        for t in await stockage.lister(cas.org, wid):
            if t["genere"]["sans_modele"]:
                continue
            vus += 1
            types = [c["type"] for c in t["criteres"]]
            # D28 (lot 19) : une conversation de la carte est aussi jugée sur la commande arrivée (``etat_final``), la série de base quand elle fixe l'issue
            assert types[0] == "mecanique_dite" and set(types[1:]) <= {"etat_final"}, t["slug"]
            if t["genere"]["genre"] == "conversation":
                assert "etat_final" in types, t["slug"]
            assert t["questions_juge"] and t["obligatoire"], t["slug"]
    assert vus >= 60



async def test_synonymes_du_formulaire_poses_a_l_installation(db_session, base_essai):
    """Lot 19 (passe de mesure, 20/11) : Casa installée par le formulaire ne trouvait plus « reine » (le synonyme vivait dans la surcouche de l'ancien
    établissement, écrite au portail). Les synonymes écrits dans la carte du formulaire sont posés, actifs, à l'installation."""
    from api.db.bases_clients.restauration_carte import carte_du_restaurant

    cas = await _client_avec_sa_base(db_session, base_essai)
    f = formulaire_de("casa-italia-restauration")
    regina = next(p for p in f["carte"]["produits"] if p["nom"] == "Regina")
    assert "reine" in (regina.get("synonymes") or []), "le formulaire de Casa porte les synonymes de l'établissement d'origine"
    a = (await I.installer_un_restaurant(cas.user, cas.org, f, nom_base=base_essai))["application"]
    connexion = await schema.connecter(base_essai)
    try:
        carte = await carte_du_restaurant(connexion, a["formulaire"]["etablissement_id"])
    finally:
        await connexion.close()
    lue = next(p for p in carte["produits"] if p["nom"] == "Regina")
    assert "reine" in lue["synonymes"], lue



async def test_commande_pour_plus_tard_du_formulaire_posee_a_l_installation(db_session, base_essai):
    """Lot 19 (passe de mesure, conversation 7) : Casa installée refusait « pour dix-neuf heures » ; la rubrique « precommande » du formulaire (permise,
    jours à l'avance, délai minimal, par type) est écrite à l'installation, comme sur l'établissement d'origine."""
    cas = await _client_avec_sa_base(db_session, base_essai)
    f = formulaire_de("casa-italia-restauration")
    assert (f.get("precommande") or {}).get("emporter", {}).get("permise") is True, "le formulaire de Casa porte la commande pour plus tard"
    a = (await I.installer_un_restaurant(cas.user, cas.org, f, nom_base=base_essai))["application"]
    connexion = await schema.connecter(base_essai)
    try:
        lu = await connexion.fetchrow("SELECT planifiee_permise, jours_a_l_avance, delai_minimal FROM mark.resto_reglage_type WHERE type = 'emporter' AND site_id = $1", a["formulaire"]["etablissement_id"])
    finally:
        await connexion.close()
    assert lu["planifiee_permise"] is True and lu["jours_a_l_avance"] == 1 and lu["delai_minimal"] == 30, dict(lu)
