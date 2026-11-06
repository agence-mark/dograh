"""[.mark] Builder partie 2 (U2, Base et automatisations) : la consigne de synthèse par défaut vit dans la bibliothèque.

| Test | Ce qu'il prouve |
|---|---|
| versée | le fichier du dépôt est versé dans ``apres-appel/consigne-synthese`` et reprend le texte du code mot pour mot |
| lue | la synthèse envoie au modèle le texte de la bibliothèque (corrigé par une personne), mots du code remplis |
| secours | bibliothèque non réglée, élément absent, texte vide ou inutilisable : le texte du code part |
| consigne propre | la consigne de l'organisation passe avant la bibliothèque |
"""

from __future__ import annotations

import json

import httpx

from api.schemas.apres_appel import ReglagesSynthese
from api.services.apres_appel import synthese
from api.services.builder import versement
from api.services.builder.bibliotheque import service

LIGNES = [{"speaker": "caller", "text": "Bonjour, je voudrais un devis."}]


class ModeleEspion:
    """Le modèle de synthèse factice : garde la consigne reçue."""

    def __init__(self):
        self.systemes: list[str] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        corps = json.loads(requete.content)
        self.systemes.append(corps["messages"][0]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "Un devis a été demandé."}}], "usage": {}})


async def _resumer(reglages: ReglagesSynthese) -> str:
    espion = ModeleEspion()
    client = httpx.AsyncClient(transport=httpx.MockTransport(espion))
    await synthese.resumer("cle", reglages, LIGNES, {"nom": "Dupont"}, client=client)
    return espion.systemes[0]


def _fichier_du_depot():
    return next(f for f in versement.lire_les_fichiers() if f.famille == "apres-appel" and f.slug == "consigne-synthese")


def test_le_fichier_du_depot_reprend_le_texte_du_code_mot_pour_mot():
    assert _fichier_du_depot().contenu["texte"] == synthese.CONSIGNE_GENERIQUE


async def test_la_consigne_est_versee_dans_la_bibliotheque(monde):
    rapport = await versement.verser()
    assert "apres-appel/consigne-synthese" in rapport.crees
    element = await service.lire_element("apres-appel", "consigne-synthese")
    assert element.courante.contenu["texte"] == synthese.CONSIGNE_GENERIQUE


async def test_la_synthese_lit_la_bibliotheque(monde):
    await versement.verser()
    await service.ajouter_version(
        "apres-appel", "consigne-synthese", {"texte": "BIBLIOTHEQUE {assistant}{entreprise} / {assistant_court} / {champs}"}, "evan"
    )
    texte = await _resumer(ReglagesSynthese(nom_assistant="Léa", nom_entreprise="Société X"))
    assert texte.startswith("BIBLIOTHEQUE Léa, l'assistant vocal de Société X / Léa / nom")
    assert "{" not in texte


async def test_la_version_versee_part_telle_quelle(monde):
    await versement.verser()
    texte = await _resumer(ReglagesSynthese())
    assert texte.startswith("Tu résumes un appel téléphonique reçu par l'assistant vocal")


async def test_secours_element_absent(monde):
    texte = await _resumer(ReglagesSynthese())
    assert texte == synthese.consigne(ReglagesSynthese(), ["nom"])


async def test_secours_bibliotheque_non_reglee(monde, monkeypatch):
    await versement.verser()
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    assert await _resumer(ReglagesSynthese()) == synthese.consigne(ReglagesSynthese(), ["nom"])


async def test_secours_texte_inutilisable(monde):
    await versement.verser()
    for abime in ("{mot_inconnu} suite", "accolade { seule", "   "):
        await service.ajouter_version("apres-appel", "consigne-synthese", {"texte": abime}, "evan")
        assert await _resumer(ReglagesSynthese()) == synthese.consigne(ReglagesSynthese(), ["nom"])


async def test_la_consigne_de_l_organisation_passe_avant_la_bibliotheque(monde):
    await versement.verser()
    await service.ajouter_version("apres-appel", "consigne-synthese", {"texte": "BIBLIOTHEQUE"}, "evan")
    assert await _resumer(ReglagesSynthese(consigne="Consigne du client.")) == "Consigne du client."
