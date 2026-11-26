"""[.mark] Lot 7b-C6, reprise R3 de l'audit (ordre de « C6 révisée » : la phrase du modèle, puis la phrase réglée du code, la question toujours la dernière) : la phrase réglée posée par
la porte (la question DC10, le total…) tient jusqu'à ce qu'elle soit dite. Une décision qui fait repasser le modèle sans la dire la remet ; une fiche vide rappelée ensuite ne la perd pas.

Avant : Client « Léa, au zéro six… » + un code de remise refusé / le modèle rappelle une fiche vide / modèle « Ce code n'est pas ouvert maintenant, désolé. » seul ; la relecture du
numéro et sa question jamais dites, alors que DC10 reste ouverte et qu'un « oui » l'accepte. Après : + code « Je note le zéro six…, c'est bon ? ».
Reprise S1 du second audit : la phrase réglée d'un passage précédent ne tient que tant qu'elle est vraie. Avant : Client « Non merci, c'est tout. » (relecture à dix euros
quatre-vingt-dix) puis, dans le même tour, une margherita ajoutée / modèle « Voilà, deux margherita alors. » + code « Cela fait dix euros quatre-vingt-dix, c'est bon pour vous ? »
(total faux, question sans objet). Après : modèle « Voilà, deux margherita alors. » puis la nouvelle relecture avec son total.
Vraie source, vraie porte, vraie parole et ``RepliqueVerifiee`` (les relances rendent les phrases données), sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.mots_dits import montant_en_lettres, numero_en_lettres
from api.services.phrases import catalogue as CAT
from api.services.pipecat.reponse_avalee import RepliqueVerifiee
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_au_numero, premier_article, question_posee

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


async def test_s1_un_article_ajoute_dans_le_tour_l_ancien_total_n_est_pas_dit(essai_de):
    """La relecture naît (son total suit la phrase du modèle) ; dans le même tour, une fiche ajoute une margherita : l'ancien total et sa question ne sont pas dits."""
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    q = question_posee(e)
    r = await e.tour("non merci, c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("type") == "proposition" else {}))
    assert question_posee(e).get("type") == "relecture", r
    ancien = montant_en_lettres(e.p["relecture"]["total"])
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Alors une margherita, ça fait douze euros."}).mode == PAROLE.SECOND_PASSAGE
    r2 = await e.fiche(ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    phrase = "Voilà, deux margherita alors."
    dit = await _voix(e, r2, phrase, [phrase])
    assert ancien not in dit, dit
    assert dit == phrase and question_posee(e) == {}, (dit, question_posee(e))  # la relecture est tombée avec l'ajout : rien de réglé ne suit la phrase du modèle


async def test_s1_voisin_le_numero_change_dans_le_tour_l_ancienne_question_dc10_n_est_pas_dite(essai_de):
    """DC10 : le numéro dicté est relu (sa question suit la phrase du modèle) ; dans le même tour, une fiche donne un autre numéro : la question de l'ancien numéro n'est pas dite."""
    e, r = await _dc10_et_refus(essai_de)
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Merci Léa."}).mode == PAROLE.SECOND_PASSAGE
    r2 = await e.dit("pardon, c'est le zéro six quatre-vingt-dix-huit soixante-seize cinquante-quatre trente-deux").fiche(telephone="0698765432")
    phrase = "C'est noté, Léa."
    dit = await _voix(e, r2, phrase, [phrase])
    nouvelle = CAT.MOTIFS[CAT.NUMERO_DICTE_RELU].variantes_defaut[0].replace("{numero}", numero_en_lettres("+33698765432"))
    assert QUESTION_DC10 not in dit and dit.endswith(nouvelle), dit


async def test_s1_voisin_un_numero_refuse_dans_le_tour_la_question_dc10_qui_attend_reste_dite(essai_de):
    """Le numéro de la seconde fiche n'est pas pris (rien de dicté) : la question DC10 attend toujours, au même ``question_id`` ; sa phrase réglée tient et finit le tour."""
    e, r = await _dc10_et_refus(essai_de)
    q = question_posee(e)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Merci Léa."})
    r2 = await e.fiche(telephone="0698765432")
    assert question_posee(e).get("id") == q["id"] and question_posee(e).get("texte") == q["texte"], question_posee(e)
    phrase = "Ce code de remise n'est pas ouvert maintenant, désolé."
    dit = await _voix(e, r2, phrase, [phrase])
    assert dit.endswith(QUESTION_DC10), dit
