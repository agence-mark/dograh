"""[.mark] Chantier Partie 1, lot 19 bis, étape E : les preuves de fin de lot.

V8 : l'aide des anciens tests (``commande_sur_la_fiche``, ~300 tests de la cuisine réécrits sur la fiche) et la vraie porte (``porte.executer``) rendent le même
résultat sur un jeu de fiches. V2 : un test traversant, du modèle simulé à la phrase dite. V7 : le banc A joué exprès échoue quand un prérequis manque.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from api.services.actions_communes import conversation as CONV
from api.services.commande import moteur, porte
from api.services.commande import panier as P
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A

API = Path(__file__).resolve().parents[3]

# Un jeu de fiches : ce que le modèle met dans la case ``ajouter`` (un article, une quantité, une variante), et ce que la cuisine en fait.
JEU = {
    "une_margherita": [A("margherita", 1, "Normale")],
    "deux_regina": [A("regina", 2, "Normale")],
    "margherita_sans_taille": [A("margherita")],
    "article_inconnu": [A("zzz introuvable")],
    "un_coca": [A("coca")],
    "deux_articles": [A("regina", 1, "Normale"), A("coca")],
    "avec_retrait": [A("regina", 1, "Normale", sans=["olives"])],
}


def _public(r) -> dict:
    """Ce que la porte garde d'un résultat du module : statut, ce qui manque, les faits sans le panier ni les clés internes."""
    return porte._resultat_public("ajouter", r)


async def _par_la_porte(essai_de, articles: list[dict]):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    retour = await e.tour("ma commande", ajouter=json.loads(json.dumps(articles)))
    faits = [x for x in retour.get("resultats") or [] if x.get("operation") == "ajouter"]
    return e, retour, faits[-1] if faits else None


async def _par_l_aide(e, articles: list[dict]):
    """L'aide des anciens tests, sur la source et les réglages de la porte, un panier neuf au même mode."""
    async with porte.registre_des_sources.ouvrir("x", e.ctx) as source:
        regles = porte._regles(e.ctx)
        p = P.nouveau()
        await moteur.choisir_mode(source, p, regles, "emporter")
        r = await F.ajouter(source, p, regles, *json.loads(json.dumps(articles)))
    return p, _public(r)


@pytest.mark.parametrize("nom", list(JEU))
async def test_l19bis_v8_parite_aide_et_porte(essai_de, nom):
    """V8 : sur chaque fiche du jeu, l'aide des anciens tests et ``porte.executer`` donnent le même statut, le même « manque », les mêmes faits et les mêmes lignes de panier."""
    e, retour, par_la_porte = await _par_la_porte(essai_de, JEU[nom])
    p, par_l_aide = await _par_l_aide(e, JEU[nom])
    assert par_la_porte is not None, retour
    assert par_la_porte == par_l_aide, (par_la_porte, par_l_aide)
    assert [(l["nom"], l["quantite"], tuple(sorted(l.get("retires") or []))) for l in sorted(p["lignes"], key=lambda l: l["nom"])] == \
        [(l["nom"], l["quantite"], tuple(sorted(l.get("retires") or []))) for l in sorted(e.p["lignes"], key=lambda l: l["nom"])]


async def test_l19bis_v8_les_barrieres_de_la_porte_ne_sont_pas_dans_l_aide(essai_de):
    """La seule différence voulue : le plafond de quantité est une barrière de la PORTE (la fiche entière refusée, rien n'est changé) ; l'aide appelle la cuisine
    en dessous des barrières. Une quantité de 50 est donc refusée par la porte, et le panier reste vide."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    retour = await e.tour("cinquante coca", ajouter=[A("coca", 50)])
    assert retour["raison"] == "plafond_d_operations" and e.p["lignes"] == [], retour


async def test_l19bis_v8_parite_de_la_reponse_a_la_question_ouverte(essai_de):
    """V8, la réponse (une taille à choisir) : ``F.repondre`` et la case ``reponse`` de la porte rendent le même statut et la même ligne de panier."""
    e, retour, _ = await _par_la_porte(essai_de, JEU["margherita_sans_taille"])
    q = CONV.question_de(e.p)
    assert q and q["type"] == "variante", retour
    par_la_porte = await e.tour("normale", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["Normale"]})
    async with porte.registre_des_sources.ouvrir("x", e.ctx) as source:
        regles = porte._regles(e.ctx)
        p = P.nouveau()
        await moteur.choisir_mode(source, p, regles, "emporter")
        await F.ajouter(source, p, regles, *JEU["margherita_sans_taille"])
        par_l_aide = await F.repondre(source, p, regles, "Normale")
    rep = [x for x in par_la_porte["resultats"] if x.get("operation") == "reponse"][-1]
    assert (rep["statut_du_module"], rep.get("manque")) == (par_l_aide.statut, par_l_aide.manque), (rep, par_l_aide)
    assert [(l["nom"], l["quantite"]) for l in p["lignes"]] == [(l["nom"], l["quantite"]) for l in e.p["lignes"]]


# --------------------------------------------------------------------------- V2


class ModeleSimule:
    """Le modèle de langage simulé : à chaque tour il rend le TEXTE JSON des arguments de l'outil ``fiche``, tel que le fournisseur le renvoie. Aucun fournisseur n'est joint."""

    def __init__(self, *textes: str):
        self.textes = list(textes)

    def arguments(self) -> dict:
        return json.loads(self.textes.pop(0))


async def test_l19bis_v2_du_modele_a_la_phrase_dite(essai_de):
    """V2 : modèle simulé → fiche → porte → base de test → prise d'essai (la caisse simulée) → phrase que le code dit à l'appelant. Chaque maillon est lu sur l'ÉTAT
    (la ligne en base, ce que la caisse a reçu), jamais sur les mots seulement."""
    from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE

    e = await essai_de()
    modele = ModeleSimule(
        '{"mode_de_retrait": "emporter", "ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}',
        '{"c_est_tout": true}',
    )
    await e.dit("à emporter, une margherita normale").fiche(**modele.arguments())
    q = CONV.question_de(e.p)  # la vente en plus, refusée : la fiche suivante la cite par son identifiant (E5)
    await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    await e.dit("c'est tout").fiche(**modele.arguments())
    q = CONV.question_de(e.p)
    assert q["type"] == "relecture", q
    await e.tour("oui, en carte, au nom de Martin", reponse={"question_id": q["id"], "sens": "accepte"}, prenom="Martin", moyen_de_paiement="carte_bancaire")
    q = CONV.question_de(e.p)
    assert q["type"] == "numero_affiche", q
    retour = await e.tour("oui, ce numéro", reponse={"question_id": q["id"], "sens": "accepte"})
    assert retour["statut"] == "ENREGISTREE", retour
    numero = e.p["enregistree"]["numero"]

    # 1. la base de test : la commande y est, à son total
    ligne = await e.monde.c.fetchrow("SELECT statut, total FROM mark.resto_commande WHERE numero = $1::uuid", numero)
    assert ligne is not None and ligne["total"] == 1090, ligne
    # 2. la prise d'essai (la caisse simulée) a reçu CETTE commande, une seule fois, avec la bonne ligne
    recues = e.source.prise.recues
    assert [c["numero"] for c in recues] == [numero], recues
    assert [(l["code_caisse"], l["quantite"]) for l in recues[0]["lignes"]] == [("PIZ-MARGHERITA-NORMALE", 1)] and recues[0]["total"] == 1090
    # 3. la phrase dite à l'appelant : celle du code, posée par la porte, qui dit l'heure annoncée par la commande
    dite = e.fiche_de_l_appel[CLE_TEXTES_DU_CODE]["avant"]
    assert "enregistrée" in dite and e.p["enregistree"]["annonce"]["dite"] in dite, dite
