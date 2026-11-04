"""[.mark] RA-B, R5 : la phrase de fin du widget (durée maximale) est au catalogue des phrases (audit 02 § 5.10)."""

import pytest

from api.services.phrases.carte import INVENTAIRE_DU_CODE, NATURE_MOTIF, NATURE_SOCLE
from api.services.phrases.catalogue import FIN_DE_DUREE_MAX, MOTIFS
from api.services.phrases.diseur import DiseurDePhrases
from api.services.site_mark.duree_max import PHRASE_DE_FIN, dire_la_fin
from api.tests.mark.test_phrases_veille_v4 import _Moteur


def test_le_motif_est_au_catalogue_avec_la_phrase_d_avant_par_defaut():
    motif = MOTIFS[FIN_DE_DUREE_MAX]
    assert motif.variantes_defaut == (PHRASE_DE_FIN,) and motif.actif_par_defaut is True


def test_la_carte_ne_la_range_plus_parmi_les_phrases_non_reglables():
    natures = [n for n, _ in INVENTAIRE_DU_CODE["site_mark/duree_max.py"]]
    assert NATURE_SOCLE not in natures and NATURE_MOTIF in natures


def _moteur(regles=None):
    moteur = _Moteur()
    moteur.active_agent = getattr(moteur, "active_agent", None) or moteur.active_agent
    moteur.active_agent.reglages = {"phrases_regles": regles or []}
    moteur.phrases = DiseurDePhrases(moteur)
    moteur.phrases.repos_s = lambda: 0.0
    return moteur


@pytest.mark.asyncio
async def test_sans_regle_le_widget_dit_la_phrase_d_avant():
    moteur = _moteur()
    await dire_la_fin(moteur)
    assert moteur.dites == [PHRASE_DE_FIN]


@pytest.mark.asyncio
async def test_une_regle_de_l_agent_change_la_phrase_de_fin():
    moteur = _moteur([{"motif": FIN_DE_DUREE_MAX, "portee": "agent", "variantes": ["Il faut que je vous laisse."]}])
    await dire_la_fin(moteur)
    assert moteur.dites == ["Il faut que je vous laisse."]


@pytest.mark.asyncio
async def test_regle_eteinte_la_phrase_d_avant_est_dite_quand_meme_la_conversation_ne_finit_jamais_en_silence():
    moteur = _moteur([{"motif": FIN_DE_DUREE_MAX, "portee": "agent", "actif": False}])
    await dire_la_fin(moteur)
    assert moteur.dites == [PHRASE_DE_FIN]
