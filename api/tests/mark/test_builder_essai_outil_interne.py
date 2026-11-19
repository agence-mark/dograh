"""[.mark] Lot 26 (M31) : l'outil d'essai du builder accepte les outils INTERNES (``commande``, ``reservation``, ``service``).

Le chemin de l'appel (``connectors.execution.executer``) est joué pour de vrai ; seul ce qu'il lit chez le client (le classeur) est remplacé par une
réponse écrite, et la décision « y a-t-il une vraie caisse ? » est posée à la main. Aucun appel réel, aucun tiers.

| Test | Ce qu'il prouve |
|---|---|
| lecture | un outil interne qui lit (état d'ouverture, produit) est joué avec un appelant fictif et les réglages de l'agent : branché sur une réponse |
| panne | « indisponible » ou un repli = non branché, avec le repli du rappel |
| écriture | un geste qui écrit ne part JAMAIS sur une vraie caisse : non essayé, rien appelé ; sans caisse ou sur la caisse de démo il part |
| tout le reste | un outil d'une autre catégorie reste « non essayé » |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.builder import essai_outil, essai_outil_interne
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.constantes import cle_builder
from api.services.integrations.connectors import execution
from api.services.integrations.connectors.execution import Resultat
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)
TEST = {"articles": "une margherita"}


def un_outil_interne(nom: str, connecteur: str, action: str, categorie="integration"):
    return SimpleNamespace(name=nom, tool_uuid=f"uuid-{nom}", category=categorie, definition={"config": {"connecteur": connecteur, "action": action}})


@pytest.fixture
def jeu(monkeypatch, monde):
    class Jeu:
        appels: list = []
        reponse = Resultat("ok", {"statut": "OK", "faits": {}, "suggestion": "Nous sommes ouverts."})
        sans_vraie_caisse = False

    j = Jeu()
    j.appels = []
    outils = [
        un_outil_interne("etat_ouverture", "commande", "etat_ouverture"),
        un_outil_interne("finaliser", "commande", "finaliser"),
        un_outil_interne("reserver", "reservation", "reserver"),
        un_outil_interne("infos_pratiques", "service", "infos_pratiques"),
        un_outil_interne("lien_externe", "commande", "etat_ouverture", categorie="mcp"),
    ]

    async def liste(organization_id, *a, **k):
        return outils

    async def jouer(organisation_id, config, arguments, fiche=None, numero=None, anticipee=None, **kw):
        j.appels.append({"config": config, "arguments": arguments, "numero": numero, "appel": kw.get("appel")})
        return j.reponse

    async def caisse(organisation_id):
        return j.sans_vraie_caisse

    async def configs(organisation_id, workflow_id):
        return {"commande_sur_catalogue": True}

    monkeypatch.setattr(essai_outil.db_client, "get_tools_for_organization", liste)
    monkeypatch.setattr(execution, "executer", jouer)
    monkeypatch.setattr(essai_outil_interne, "_sans_vraie_caisse", caisse)
    monkeypatch.setattr(essai_outil_interne, "_configurations_de_l_agent", configs)
    return j


async def essayer(outil: str, donnees=None):
    return await executer("outil_essayer", {"outil": outil, "donnees_test": TEST if donnees is None else donnees}, EQUIPE)


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : écrit sur la fiche avec la couche de parole (anciens-tests.md, D49)")
async def test_un_outil_interne_qui_lit_est_joue_avec_un_appelant_fictif_et_branche(jeu, monde):
    r = await essayer("etat_ouverture")
    assert r["ok"] is True and r["branche"] is True and r["repli"] is None, r
    (appel,) = jeu.appels
    assert appel["config"]["connecteur"] == "commande" and appel["numero"] == essai_outil_interne.APPELANT_FICTIF
    assert appel["numero"].startswith("+336399")  # une plage réservée à la fiction : jamais un vrai numéro
    assert monde.configs[(ORG_CLIENT, cle_builder(AGENT, "outils"))]["etat_ouverture"]["branche"] is True


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : écrit sur la fiche avec la couche de parole (anciens-tests.md, D49)")
async def test_un_refus_normal_prouve_que_l_outil_repond(jeu):
    jeu.reponse = Resultat("ok", {"statut": "CHOIX_OBLIGATOIRE", "faits": {}, "suggestion": "Quelle taille ?"})
    r = await essayer("etat_ouverture")
    assert r["branche"] is True and "CHOIX_OBLIGATOIRE" in r["raison"]


@pytest.mark.parametrize(
    "reponse",
    [
        Resultat("ok", {"statut": "INDISPONIBLE", "faits": {}, "suggestion": ""}),
        Resultat("ok", {}),
        Resultat("repli", {}, 0, "deadline passed"),
        Resultat("erreur", {"manque": ["x"]}, 0, "Ask the caller for: x."),
    ],
)
async def test_un_outil_interne_en_panne_n_est_pas_branche(jeu, reponse):
    jeu.reponse = reponse
    r = await essayer("etat_ouverture")
    assert r["branche"] is False and r["repli"] == "demander_un_rappel"


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : écrit sur la fiche avec la couche de parole (anciens-tests.md, D49)")
async def test_un_geste_qui_ecrit_ne_part_jamais_sur_une_vraie_caisse(jeu):
    for nom in ("finaliser", "reserver"):
        r = await essayer(nom)
        assert r["branche"] is False and "Not tried" in r["raison"] + r["elements"][0]["message"], r
    assert jeu.appels == []  # rien n'a été appelé


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : écrit sur la fiche avec la couche de parole (anciens-tests.md, D49)")
async def test_un_geste_qui_ecrit_part_sans_caisse_ou_sur_la_caisse_de_demo(jeu):
    jeu.sans_vraie_caisse = True
    r = await essayer("finaliser")
    assert r["branche"] is True and len(jeu.appels) == 1


async def test_le_connecteur_de_service_est_essaye_aussi_et_un_outil_non_interne_reste_non_essaye(jeu):
    assert (await essayer("infos_pratiques"))["branche"] is True
    r = await essayer("lien_externe")
    assert r["branche"] is False and "cannot be tried here" in r["raison"]
    assert len(jeu.appels) == 1  # seul l'outil interne a été joué


async def test_une_donnee_qui_a_l_air_reelle_reste_refusee(jeu):
    r = await essayer("etat_ouverture", {"tel": "06 12 34 56 78"})
    assert r["ok"] is False and "fictitious" in r["erreur"] and jeu.appels == []
