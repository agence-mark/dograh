"""[.mark] builder-agent-vocal, lot 5 : l'essai d'un outil avant « branché » (Q11).

Le système du client est SIMULÉ (``httpx.MockTransport`` posé sous le vrai chemin d'appel d'un outil HTTP) : aucun appel réel.
Un outil qui répond une réponse valide = branché ; qui échoue, ne répond pas, répond du vide ou autre chose que du JSON =
non branché, avec le repli ``demander_un_rappel``.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from api.services.builder import essai_outil
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.constantes import cle_builder
from api.services.builder.donnees_fictives import est_fictive, rendre_fictif
from api.services.workflow.tools import custom_tool
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)
TEST = {"nom": "Camille Exemple", "email": "personne1@exemple.test", "telephone": "06 39 98 00 01"}


def un_outil(nom="chercher_un_creneau", categorie="http_api", methode="GET"):
    return SimpleNamespace(
        name=nom,
        tool_uuid=f"uuid-{nom}",
        category=categorie,
        definition={"config": {"method": methode, "url": "https://systeme.exemple.test/api", "timeout_ms": 1000}},
    )


@pytest.fixture
def systeme(monkeypatch, monde):
    """Un système de client simulé : ``systeme.reponse`` est une fonction requête -> réponse (ou lève)."""
    class Systeme:
        appels: list[httpx.Request] = []
        reponse = staticmethod(lambda requete: httpx.Response(200, json={"creneaux": ["10h"]}))

    s = Systeme()
    s.appels = []
    vrai = httpx.AsyncClient

    def gestionnaire(requete):
        s.appels.append(requete)
        return s.reponse(requete)

    monkeypatch.setattr(custom_tool.httpx, "AsyncClient", lambda **o: vrai(transport=httpx.MockTransport(gestionnaire), **o))
    outils = [un_outil(), un_outil("lien_externe", "mcp"), un_outil("reserver", methode="POST"), un_outil("annuler", methode="delete")]

    async def liste(organization_id, *a, **k):
        assert organization_id == ORG_CLIENT
        return outils

    monkeypatch.setattr(essai_outil.db_client, "get_tools_for_organization", liste)
    return s


async def essayer(donnees=None, outil="chercher_un_creneau"):
    return await executer("outil_essayer", {"outil": outil, "donnees_test": TEST if donnees is None else donnees}, EQUIPE)


async def test_un_outil_qui_repond_une_reponse_valide_est_branche(systeme, monde):
    r = await essayer()
    assert r["ok"] is True and r["branche"] is True and r["repli"] is None
    assert len(systeme.appels) == 1 and systeme.appels[0].url.host == "systeme.exemple.test"
    assert r["elements"][0]["statut"] == "ok" and r["carte"]["type"] == "outils"
    # Le fait est rangé pour le rapport.
    assert monde.configs[(ORG_CLIENT, cle_builder(AGENT, "outils"))]["chercher_un_creneau"]["branche"] is True


@pytest.mark.parametrize(
    "reponse",
    [
        lambda r: httpx.Response(500, json={"error": "boom"}),
        lambda r: httpx.Response(404, json={"error": "inconnu"}),
        lambda r: httpx.Response(200, text="<html>pas du json</html>"),
        lambda r: httpx.Response(200, json={}),
        lambda r: httpx.Response(200, json={"success": False, "message": "refusé"}),
        lambda r: httpx.Response(200, json={"status": "error"}),
        lambda r: httpx.Response(200, json={"error": "indisponible"}),
    ],
)
async def test_un_outil_qui_echoue_ou_repond_mal_n_est_pas_branche_et_replie_sur_le_rappel(systeme, reponse):
    systeme.reponse = reponse
    r = await essayer()
    assert r["ok"] is True and r["branche"] is False
    assert r["repli"] == "demander_un_rappel" and "demander_un_rappel" in r["elements"][0]["message"]
    assert r["elements"][0]["statut"] == "echec"


async def test_un_outil_qui_ne_repond_pas_n_est_pas_branche(systeme):
    def silence(requete):
        raise httpx.ConnectTimeout("pas de réponse", request=requete)

    systeme.reponse = silence
    r = await essayer()
    assert r["branche"] is False and r["repli"] == "demander_un_rappel"


async def test_une_donnee_qui_a_l_air_reelle_est_refusee_et_rien_n_est_envoye(systeme):
    for reel in ({"email": "marie.dupont@gmail.com"}, {"tel": "06 12 34 56 78"}):
        r = await essayer(reel)
        assert r["ok"] is False and "fictitious" in r["erreur"]
    assert systeme.appels == []


async def test_un_outil_inconnu_est_refuse_et_un_outil_non_http_n_est_jamais_dit_branche(systeme):
    assert (await essayer(outil="n_existe_pas"))["ok"] is False
    r = await essayer(outil="lien_externe")
    assert r["branche"] is False and r["repli"] == "demander_un_rappel" and systeme.appels == []


async def test_l_essai_ne_renvoie_ni_en_tete_ni_cle(systeme):
    r = await essayer()
    assert "request_headers" not in r and "authorization" not in str(r).lower()


async def test_un_autre_client_ne_peut_pas_essayer_les_outils_de_cet_agent(systeme, monde):
    r = await executer("outil_essayer", {"outil": "chercher_un_creneau", "donnees_test": TEST}, Contexte(user=utilisateur(3, organisation=99), workflow_id=AGENT))
    assert r["ok"] is False and systeme.appels == []


# --- Q3 : données fictives ------------------------------------------------------------------------------------------------


def test_les_donnees_fictives_sont_reconnues_et_les_reelles_non():
    assert est_fictive(TEST) and est_fictive({"liste": ["a@exemple.test"]}) and est_fictive("+33 6 39 98 12 34")
    assert not est_fictive("a@gmail.com") and not est_fictive({"x": {"tel": "01 42 00 11 22"}}) and not est_fictive("+33 6 12 34 56 78")


def test_rendre_fictif_remplace_partout_la_meme_vraie_valeur_par_la_meme_fausse():
    vrai = {
        "nom": "t",
        "historique": [
            {"role": "user", "texte": "Je suis Marie Dupont, mon mail est marie.dupont@gmail.com"},
            {"role": "assistant", "texte": "Merci Marie Dupont, je note le 06 12 34 56 78."},
        ],
        "replique": "Oui c'est marie.dupont@gmail.com",
        "fiche": {"nom_client": "Marie Dupont", "telephone": "06 12 34 56 78", "motif": "un rendez-vous"},
    }
    faux = rendre_fictif(vrai)
    texte = str(faux)
    assert "Marie Dupont" not in texte and "gmail" not in texte and "06 12 34 56 78" not in texte
    assert faux["fiche"]["motif"] == "un rendez-vous" and faux["donnees_fictives"] is True
    mail = faux["replique"].split()[-1]
    assert mail in faux["historique"][0]["texte"] and est_fictive(faux)
    assert "Marie Dupont" in str(vrai)  # l'original n'est pas modifié


# --- revue R5 : un essai qui écrit chez le client attend un geste humain ----------------------------------------------------------------


@pytest.mark.parametrize("outil", ["reserver", "annuler"])
async def test_un_outil_qui_ecrit_rend_une_carte_a_valider_et_rien_n_est_appele(systeme, monde, outil):
    r = await essayer(outil=outil)
    assert r["ok"] is True and r["a_valider"] is True and r["branche"] is False
    assert r["carte"]["type"] == "essai_a_valider" and r["carte"]["outil"] == outil
    assert r["carte"]["methode"] in ("POST", "DELETE") and r["carte"]["adresse"] == "https://systeme.exemple.test/api"
    assert r["carte"]["donnees_test"] == TEST
    assert systeme.appels == []  # le système du client n'a pas été appelé
    assert (ORG_CLIENT, cle_builder(AGENT, "outils")) not in monde.configs  # et rien n'est dit « branché » ni « non branché »


async def test_un_get_part_directement(systeme):
    r = await essayer()
    assert r.get("a_valider") is None and r["branche"] is True and len(systeme.appels) == 1


async def test_le_geste_humain_lance_l_essai_d_un_outil_qui_ecrit(systeme, monde):
    r = await essai_outil.essayer(ORG_CLIENT, AGENT, "reserver", TEST, geste_humain=True)
    assert r["branche"] is True and len(systeme.appels) == 1 and systeme.appels[0].method == "POST"
    assert monde.configs[(ORG_CLIENT, cle_builder(AGENT, "outils"))]["reserver"]["branche"] is True
    # des données qui ont l'air réelles restent refusées, même par un geste humain
    with pytest.raises(essai_outil.ErreurEssai):
        await essai_outil.essayer(ORG_CLIENT, AGENT, "reserver", {"email": "marie.dupont@gmail.com"}, geste_humain=True)
