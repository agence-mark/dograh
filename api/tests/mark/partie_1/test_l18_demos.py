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
