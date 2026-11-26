"""[.mark] Lot 7b-C6, reprise R3 de l'audit (ordre de « C6 révisée » : la phrase du modèle, puis la phrase réglée du code, la question toujours la dernière) : la phrase réglée posée par
la porte (la question DC10, le total…) tient jusqu'à ce qu'elle soit dite. Une décision qui fait repasser le modèle sans la dire la remet ; une fiche vide rappelée ensuite ne la perd pas.

Avant : Client « Léa, au zéro six… » + un code de remise refusé / le modèle rappelle une fiche vide / modèle « Ce code n'est pas ouvert maintenant, désolé. » seul ; la relecture du
numéro et sa question jamais dites, alors que DC10 reste ouverte et qu'un « oui » l'accepte. Après : + code « Je note le zéro six…, c'est bon ? ».
Vraie source, vraie porte, vraie parole et ``RepliqueVerifiee`` (les relances rendent les phrases données), sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.mots_dits import numero_en_lettres
from api.services.phrases import catalogue as CAT
from api.services.pipecat.reponse_avalee import RepliqueVerifiee
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import jusqu_au_numero

DIT = numero_en_lettres("+33612345678")
QUESTION_DC10 = CAT.MOTIFS[CAT.NUMERO_DICTE_RELU].variantes_defaut[0].replace("{numero}", DIT)
REGLEE = "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"


def _morceau(texte):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)


def _reprise(texte: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=texte, tool_calls=None), finish_reason="stop")], usage=None)


async def _voix(e, retour, phrase: str, reponses: list[str]) -> str:
    """Ce qui part à la voix : la phrase de la fiche dite seule ; sinon le modèle repasse et répond ``reponses[0]``, puis chaque relance rend la suivante (la dernière ensuite)."""
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return str(d.a_dire)
    verificateur = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    vues: list[str] = []

    async def flux():
        yield _morceau(reponses[0])

    async def relancer(_retenue):
        vues.append("relance")
        return _reprise(reponses[min(len(vues), len(reponses) - 1)])

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relancer, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])


async def _dc10_et_refus(essai_de):
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False)
    r = await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678", prenom="Léa", code_de_remise="BIDON")
    assert (CONV.question_de(e.p) or {}).get("type") == "numero_dicte", r
    return e, r


async def test_dc10_et_refus_puis_une_fiche_vide_la_question_dc10_finit_le_tour(essai_de):
    """Le modèle repasse après le refus et rappelle une fiche vide : la question DC10, posée au premier passage, suit sa phrase."""
    e, r = await _dc10_et_refus(essai_de)
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Merci Léa."}).mode == PAROLE.SECOND_PASSAGE
    phrase = "Ce code de remise n'est pas ouvert maintenant, désolé."
    dit = await _voix(e, await e.fiche(), phrase, [phrase])
    assert dit == f"{phrase} {QUESTION_DC10}", dit


async def test_voisin_la_question_dc10_n_est_dite_qu_une_fois_dans_le_tour(essai_de):
    """Dite avec la phrase du modèle, elle ne revient pas sur une seconde fiche vide du même tour (une question à la fois)."""
    e, r = await _dc10_et_refus(essai_de)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Merci Léa."})
    phrase = "Ce code de remise n'est pas ouvert maintenant, désolé."
    premiere = await _voix(e, await e.fiche(), phrase, [phrase])
    assert premiere.endswith(QUESTION_DC10), premiere
    seconde = await _voix(e, await e.fiche(), "Je vous écoute.", ["Je vous écoute."])
    assert QUESTION_DC10 not in seconde, seconde


async def test_voisin_sans_fiche_vide_la_question_dc10_part_seule_quand_le_modele_reste_retenu(essai_de):
    """Refus de la fiche dans le tour : la phrase du modèle n'est jamais dite (repli A) ; la relance ratée laisse partir la suite réglée seule (reprise R1), jamais un tour muet."""
    e, r = await _dc10_et_refus(essai_de)
    dit = await _voix(e, r, "Merci Léa.", ["Merci Léa, ce code de remise n'est pas ouvert maintenant."])
    assert dit == QUESTION_DC10, dit
