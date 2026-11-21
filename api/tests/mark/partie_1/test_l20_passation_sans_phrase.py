"""Lot 20 (relecture, n7, H1, H4 : D-C) : l'agent principal disait « Une reine à emporter, c'est noté. Puis-je faire autre chose ? » EN passant la main ;
l'agent commande répondait ensuite : deux réponses de suite. Garde sur la forme de la réponse : une réponse qui appelle un outil de passation ne dit
rien d'elle-même (l'agent qui reçoit parle). Sans passation, le texte passe tel quel."""

from api.services.pipecat.reponse_avalee import SansPhraseAvecLaPassation
from api.tests.mark.test_correctifs_passations import _appel, _FluxSimple, _morceau


async def _par(morceaux, noms):
    return [m async for m in SansPhraseAvecLaPassation(_FluxSimple(morceaux), lambda: noms)]


def _textes(morceaux):
    return "".join((m.choices[0].delta.content or "") for m in morceaux if m.choices)


async def test_le_texte_dit_avec_une_passation_n_est_pas_dit():
    flux = [_morceau("Une reine à emporter, c'est noté. "), _morceau("Puis-je faire autre chose ?"),
            _appel(0, "passer_a", '{"cible": "commande", "demande": "une reine"}', "t1"), _morceau(fin="tool_calls")]
    sortie = await _par(flux, {"passer_a"})
    assert _textes(sortie) == ""
    assert any(m.choices and m.choices[0].delta.tool_calls for m in sortie)


async def test_sans_passation_le_texte_passe_tel_quel():
    flux = [_morceau("Nous ouvrons à onze heures."), _morceau(fin="stop")]
    assert await _par(flux, {"passer_a"}) == flux
    autre = [_morceau("Je regarde."), _appel(0, "infos_pratiques", "{}", "t1"), _morceau(fin="tool_calls")]
    assert await _par(autre, {"passer_a"}) == autre
