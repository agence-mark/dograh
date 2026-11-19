"""[.mark] Appel 2610 (Casa Italia, 17/11) : des outils standard, une passe de modèle par tour quand l'outil rend la question.

Vrai gestionnaire d'outil, vraie base du client (R1), mécanisme commun, aucun mot de métier.

| Test | Ce qu'il prouve |
|---|---|
| question dite par le code | un geste qui rend UNE question (mode, choix obligatoire) est conseillé « dit par le code » : le modèle n'est pas relancé |
| où va la réponse | le retour dit l'outil et le paramètre de la réponse (``repondre``) : le prompt n'a plus à le prévoir |
| refus | un refus (introuvable) reste reformulé, sans ``repondre`` : il demande le jugement du modèle |
| fiche de l'outil | un réglage ``restitution`` posé sur l'outil garde la main (T-01) |
| fermé dès la première question | aucun mode ouvert : la fermeture est dite avec la question du mode, une seule fois ; sans précommande, la fermeture seule |
| tout recommencer | ``voir_commande`` avec ``vider`` vide la commande (un outil de moins sur l'étape) |
| étiquettes du collègue | le prompt d'un collègue préparé avant d'avoir la main est rendu avec SA table (les outils cités n'étaient plus que des blancs) |
| transcription en voix | un texte du code qui entre dans l'historique n'est écrit qu'une fois au journal (répliques 27, 30, 32 doublées) |
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from api.services.commande import panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.banc_a.commun import faire_monde  # noqa: F401
from api.tests.mark.partie_1.porte_essai import essai_de  # noqa: F401

JEUDI = 4


# test_la_question_du_mode_est_reformulee… : supprimé au lot 6 (D49), la question est numérotée et la réponse revient par ``reponse.question_id`` (plus de ``repondre`` ni de restitution par outil) ; sens repris par partie_1/test_l04_cuisine.py::test_proposition_une_fois_question_numerotee et partie_1/test_l06_parole.py::test_a_dire_un_passage


# test_un_choix_obligatoire_est_reformule… : supprimé au lot 6 (D49), idem : question numérotée, réponse dans ``reponse`` ; sens repris par partie_1/test_l04_cuisine.py::test_changer_la_taille et partie_1/test_l06_parole.py::test_a_dire_un_passage


# test_un_refus_reste_au_jugement_du_modele : supprimé au lot 6 (D49) ; sens repris par partie_1/test_l06_parole.py::test_refus_du_metier_phrase_gardee et partie_1/test_l06_parole.py::test_pas_de_phrase_sans_outil_apres_refus_de_la_fiche


# test_le_reglage_de_la_fiche_de_l_outil_garde_la_main : supprimé au lot 6 (D49), le réglage ``restitution`` par outil est remplacé par la parole de la fiche ; sens repris par partie_1/test_l06_parole.py::test_portee_du_reglage_a_l_etape


# test_ferme_la_personne_le_sait… : supprimé au lot 4 (D49) ; sens repris par partie_1/test_l04_cuisine.py::test_fermeture_dite_une_fois


# test_ferme_sans_precommande_la_fermeture_seule : supprimé au lot 4 (D49) ; sens repris par partie_1/test_l04_cuisine.py::test_fermeture_dite_une_fois (précommande refusée, fermeture dite seule) et ::test_pause_de_la_caisse_au_decroche


async def test_vider_le_panier_recommence(essai_de):
    """Lot 4 (D49) : même scénario par la fiche : la case ``vider_le_panier`` remplace ``voir_commande`` avec ``vider`` ; le mode reste."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina normale et un coca", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}, {"article": "coca", "quantite": 1}])
    assert e.p["lignes"]
    q = e.p.get("question") or {}
    if q:  # la proposition en plus attend sa réponse : elle est refusée avant de tout recommencer
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    await e.tour("on recommence", vider_le_panier=True)
    assert e.p["lignes"] == [] and e.p["mode"] == "emporter", e.retours[-1]


def test_le_prompt_d_un_collegue_est_rendu_avec_sa_table():
    from api.services.etiquettes_prompt import moteur as etiquettes
    from api.services.etiquettes_prompt import resolution

    accueil, collegue = SimpleNamespace(nodes={}), SimpleNamespace(nodes={})
    table_collegue = resolution.Table(outils={"u-1": "ajouter"})
    engine = SimpleNamespace(_active_agent=SimpleNamespace(workflow=accueil), _call_context_vars={})
    engine._tables_etiquettes = {id(accueil): resolution.Table(), id(collegue): table_collegue}
    assert etiquettes.rendre(engine, "Appelle {{outil:u-1}}.") == "Appelle ."  # l'agent qui joue n'a pas cet outil
    assert etiquettes.rendre(engine, "Appelle {{outil:u-1}}.", collegue) == "Appelle ajouter."


async def test_un_texte_du_code_dans_l_historique_n_est_ecrit_qu_une_fois_au_journal():
    from pipecat.frames.frames import TTSSpeakFrame

    from api.services.workflow.pipecat_engine import PipecatEngine

    engine = PipecatEngine(workflow=None, call_context_vars={})
    vues: list = []

    async def recevoir(frame):
        vues.append(frame)

    engine.active_agent.worker = SimpleNamespace(queue_frame=recevoir)
    await engine.queue_speech("Vous réglez comment ?", append_to_context=True, persist_to_logs=True)
    await engine.queue_speech("Un instant.", append_to_context=False, persist_to_logs=True)
    dits = [f for f in vues if isinstance(f, TTSSpeakFrame)]
    assert [(f.text, f.append_to_context, f.persist_to_logs) for f in dits] == [
        ("Vous réglez comment ?", True, False),  # l'agrégateur de l'agent l'écrit à la fin du tour
        ("Un instant.", False, True),  # hors historique : seul ce drapeau l'écrit
    ]
