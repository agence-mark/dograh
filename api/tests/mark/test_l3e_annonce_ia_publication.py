"""[.mark] builder partie 3, L3e sous-lot 2 : la ligne BLOQUANTE de « Prêt à publier » pour l'annonce « vous parlez à une IA ».

| Test | La garantie |
|---|---|
| texte par défaut | la ligne est faite, bloquante en position, et ne gêne pas la publication |
| texte vide | une règle de l'agent qui vide le texte bloque la publication et la ligne dit où le régler (thème Phrases) |
| impossible à éteindre | aucun réglage de publication ne change sa position |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.builder.tests_agent import publication
from api.services.phrases.catalogue import ANNONCE_IA
from api.services.publication import controles
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, monde, sans_les_lignes_de_pret  # noqa: F401
from api.tests.mark.test_builder_tests_agent import banc  # noqa: F401
from api.tests.mark.test_pret_a_publier import _graphe


def _brouillon(configurations):
    return SimpleNamespace(workflow_json=_graphe(), version_number=2, workflow_configurations=configurations)


def _base(**en_plus):
    return sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False, **en_plus})


async def test_le_texte_par_defaut_est_fait_et_ne_bloque_pas(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vue = await controles.evaluer(wf, _brouillon(_base()), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert (bloc["position"], bloc["statut"], bloc["problemes"]) == ("bloque", "ok", [])
    ligne = next(l for l in vue["lignes"] if l["id"] == "annonce_ia")
    assert ligne["etat"] == "fait" and ligne["theme"] == "phrases"
    assert await publication.verifier_avant_publication(wf, _brouillon(_base()), ORG_CLIENT) is None


async def test_un_texte_vide_bloque_la_publication_et_la_ligne_mene_au_theme_phrases(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vide = _base(phrases_regles=[{"motif": ANNONCE_IA, "portee": "agent", "variantes": [], "active": False}])
    vue = await controles.evaluer(wf, _brouillon(vide), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert bloc["statut"] == "echec" and vue["bloque"] is True and "empty text" in bloc["problemes"][0]
    ligne = next(l for l in vue["lignes"] if l["id"] == "annonce_ia")
    assert ligne["etat"] == "bloquant" and ligne["theme"] == "phrases"
    refus = await publication.verifier_avant_publication(wf, _brouillon(vide), ORG_CLIENT)
    assert refus is not None and [c["cle"] for c in refus["controles_publication"]] == ["annonce_ia"]


async def test_aucun_reglage_de_publication_ne_peut_eteindre_ce_controle(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    vide = _base(
        phrases_regles=[{"motif": ANNONCE_IA, "portee": "agent", "variantes": [], "active": False}],
        publication={"controles": {"annonce_ia": "eteint"}},
    )
    vue = await controles.evaluer(wf, _brouillon(vide), ORG_CLIENT)
    bloc = next(c for c in vue["controles"] if c["cle"] == "annonce_ia")
    assert bloc["position"] == "bloque" and bloc["statut"] == "echec"
