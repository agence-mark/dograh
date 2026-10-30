"""[.mark] figeage-v12, lot A1 : trois défauts de la v12 corrigés à la source (plan `Labo-agent-vocal/plans/figeage-v12/`).

Causes prouvées au lot 0 (`lot-0-causes.md`) : D7 (deux paroles dans un tour), D8 (report perdu au clavier), D14 (espace
avalée par le filtre du nom).

| Test | Ce qu'il prouve |
|---|---|
| D7, deux familles de cerveaux | une condition de la fiche déjà vraie quand la requête part : le passage a lieu AVANT la requête (elle part dans l'étape d'arrivée), sans relance, une seule porte par parole ; la fin de la réplique ne reprend rien |
| D7, rien de vrai | aucune condition vraie : le greffier n'est pas attendu (aucune latence ajoutée), la requête part de l'étape d'avant |
| D7, étape qui ne lit pas la fiche | comportement d'avant : rien lu, rien attendu |
| D7, greffier en retard / correction | délai dépassé : rien avant, l'option 1 joue en fin de réplique comme avant ; la parole nouvelle rend la condition fausse : pas de passage |
| D7, vers une fin | une porte vers une fin ne se prend pas avant la requête (l'option 1 joue) |
| D8, deux moteurs, une fiche | le report « une seule fois » est rangé dans la fiche de l'appel : un moteur neuf (le clavier en reconstruit un à chaque tour) le retrouve, et décide au tour suivant |
| D8, clavier | deux tours de suite qui finissent par « ? » dans une vraie session : le premier reporte, le second passe |
| D14 | le blanc de fin de la phrase d'origine est rendu : « Je note Marc. » + « Est-ce que… » ne se collent plus |
"""

from __future__ import annotations

import pytest

from api.services.pipecat.filtre_nom_civilite import retirer_nom_et_civilite
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.tests.mark.test_passages_fiables_agnostique import FAMILLES, _brancher, _requete
from api.tests.mark.test_passages_fiables_fiche import (
    GreffierFactice,
    _complete,
    _Contexte,
    _etape,
    _fin_de_reponse,
    definition_clavier,
    graphe,
    monter,
)

PAROLE = [{"role": "assistant", "content": "Quelle est la demande ?"}, {"role": "user", "content": "une demande"}]


# --------------------------------------------------------------------------- #
# D7 : une condition de la fiche déjà vraie passe AVANT la requête
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_d7_fiche_deja_vraie_la_requete_part_dans_l_etape_d_arrivee_une_seule_parole(famille):
    greffier = GreffierFactice()
    harness = await monter(fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        cerveau = await _brancher(engine, famille)
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        assert "Tu es l'étape Suite." in requete["systeme"]  # la requête part déjà dans l'étape d'arrivée
        engine.active_agent.queue_frame.assert_not_awaited()  # aucune relance : une seule parole dans le tour
        derniere = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert (derniere["raison"], derniere["option"], derniere["resultat"]) == ("fiche", 2, "prise")
        # La fin de la réplique ne prend pas une seconde porte sur la même parole.
        qui, _, _ = await _fin_de_reponse(engine, "Voici la suite.")
        assert qui is None and _etape(engine) == "suite"
        assert len(engine._gathered_context[passage.CLE_PASSAGES]) == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d7_rien_de_vrai_le_greffier_n_est_pas_attendu():
    greffier = GreffierFactice()
    harness = await monter(fiche={"nom": "Lemaire"}, greffier=greffier)  # un champ manque
    try:
        engine = harness.engine
        contexte = _Contexte([dict(m) for m in PAROLE])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert greffier.appels == [] and _etape(engine) == "etape"
        assert passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d7_une_etape_qui_ne_lit_pas_la_fiche_comportement_d_avant():
    greffier = GreffierFactice()
    harness = await monter(graphe({"champs_etape": "nom,objet"}), fiche=_complete(), greffier=greffier)  # mode agent
    try:
        engine = harness.engine
        contexte = _Contexte([dict(m) for m in PAROLE])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert greffier.appels == [] and _etape(engine) == "etape"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d7_greffier_en_retard_rien_avant_l_option_1_joue_en_fin_de_reponse():
    greffier = GreffierFactice(reponse=False)
    harness = await monter(fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        contexte = _Contexte([dict(m) for m in PAROLE])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape" and len(greffier.appels) == 1
        greffier.reponse = True
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["option"] == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d7_la_parole_nouvelle_rend_la_condition_fausse_pas_de_passage():
    greffier = GreffierFactice()
    harness = await monter(fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        # Le greffier lit la correction de la personne : le nom est de nouveau « à confirmer ».
        greffier.pendant = lambda: engine._gathered_context.update(fiche_etat={"nom": {"sure": False}})
        contexte = _Contexte([dict(m) for m in PAROLE])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape" and len(greffier.appels) == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d7_vers_une_fin_pas_de_passage_avant_la_requete():
    greffier = GreffierFactice()
    harness = await monter(graphe(vers_la_fin=True, refus=False), fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        contexte = _Contexte([dict(m) for m in PAROLE])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape"
        # Le dernier message n'est pas la parole de la personne (résultat d'outil) : rien non plus.
        contexte = _Contexte([{"role": "user", "content": "x"}, {"role": "tool", "content": "ok"}])
        assert await passage.fiche_deja_vraie_avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# D8 : le report « une seule fois » vit dans la fiche de l'appel
# --------------------------------------------------------------------------- #


class _Moteur:
    """Un moteur neuf (le clavier en reconstruit un à chaque tour) autour de la même fiche de l'appel."""

    def __init__(self, fiche):
        self._gathered_context = fiche


def test_d8_un_moteur_neuf_retrouve_le_report_dans_la_fiche():
    fiche = {"tour_appelant": 3}
    jeton = ("visite", "etape", 0)
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "C'est bien ça ?", jeton) is True
    assert fiche[decideur.CLE_REPORT] == {"etape": "etape", "tour": 3}
    # Tour suivant, moteur reconstruit (rang d'entrée reparti de zéro) : la même étape, une seconde question : le code décide.
    fiche["tour_appelant"] = 4
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "Quel jour ?", ("autre", "etape", 0)) is False
    assert decideur.CLE_REPORT not in fiche
    # Et la fois d'après, une nouvelle question reporte de nouveau (une fois par visite).
    fiche["tour_appelant"] = 5
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "Autre chose ?", jeton) is True


def test_d8_un_report_ancien_ou_d_une_autre_etape_ne_compte_pas():
    jeton = ("visite", "etape", 0)
    # Rangé trois tours plus tôt : la personne a eu le temps de répondre, on reporte de nouveau.
    fiche = {"tour_appelant": 6, decideur.CLE_REPORT: {"etape": "etape", "tour": 3}}
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "Et ensuite ?", jeton) is True
    # Rangé pour une autre étape.
    fiche = {"tour_appelant": 4, decideur.CLE_REPORT: {"etape": "ailleurs", "tour": 3}}
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "Et ensuite ?", jeton) is True
    # Une réplique sans question efface le report.
    assert decideur._reporter_pour_la_question(_Moteur(fiche), "Merci.", jeton) is False
    assert decideur.CLE_REPORT not in fiche


def test_d8_sans_fiche_le_code_decide():
    class SansFiche:
        _gathered_context = None

    assert decideur._reporter_pour_la_question(SansFiche(), "Quel jour ?", ("v", "e", 0)) is False


@pytest.mark.asyncio
async def test_d8_clavier_deux_questions_de_suite_la_seconde_ne_reporte_plus(
    db_session, async_session, test_client_factory
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter, _noter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    etape = {"champs_etape": "nom", "qui_decide_du_passage": "collecte"}
    user, workflow = await _monter(db_session, async_session, FICHE, definition_clavier(etape))
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [
            _vide(),
            _dit(_noter({"nom": "Lemaire"}, "n1"), _texte("Je note Lemaire, c'est bien ça ?")),
            _dit(_texte("Quel jour vous arrangerait ?"), _texte("Voici la suite.")),
        ],
        ["je m'appelle Lemaire", "oui c'est ça"],
    )
    apres_la_premiere = reponses[0]["checkpoint"]["gathered_context"]
    assert decideur.CLE_REPORT in apres_la_premiere, apres_la_premiere  # le report survit à la reconstruction du moteur
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert [p["resultat"] for p in fiche.get(passage.CLE_PASSAGES) or []] == ["reportee_question", "prise"], fiche
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche


# --------------------------------------------------------------------------- #
# D14 : le blanc de fin de phrase survit au filtre du nom
# --------------------------------------------------------------------------- #


def test_d14_la_phrase_filtree_garde_son_espace_de_fin_et_la_suivante_ne_se_colle_pas():
    premiere = retirer_nom_et_civilite("Je note Marc Henry. ", "Henry", retirer_nom=True)
    assert premiere == "Je note Marc. "
    assert premiere + "Est-ce que c'est bien ça ?" == "Je note Marc. Est-ce que c'est bien ça ?"


@pytest.mark.parametrize(
    "texte, nom, attendu",
    [
        ("Je note Marc Henry.", "Henry", "Je note Marc."),  # pas de blanc à la fin : rien d'ajouté
        ("Je note Marc Henry.\n", "Henry", "Je note Marc.\n"),
        ("Bonjour monsieur Henry. ", "Henry", "Bonjour. "),
        ("Henry. ", "Henry", ""),  # une phrase qui n'était que le nom ne laisse rien, pas même un blanc
        ("Rien à retirer ici. ", "Henry", "Rien à retirer ici. "),
    ],
)
def test_d14_le_blanc_de_fin_est_celui_de_la_phrase_d_origine(texte, nom, attendu):
    assert retirer_nom_et_civilite(texte, nom, retirer_nom=True, retirer_civilite=True) == attendu
