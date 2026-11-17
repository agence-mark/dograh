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

from types import SimpleNamespace

from api.services.commande import panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401
from api.tests.mark.test_restauration_precommande_ferme import _ferme_a_midi

JEUDI = 4


async def test_la_question_du_mode_est_dite_par_le_code_avec_ou_va_la_reponse(appel_de_test):
    r = await appel_de_test.jouer("ajouter", articles="une regina normale")
    assert r["manque"] == "mode" and r["suggestion"].endswith("?"), r
    assert r["restitution"] == "dit_par_le_code", r
    assert r["repondre"] == "choisir_mode.mode", r


async def test_un_choix_obligatoire_est_dit_par_le_code_et_sa_reponse_va_dans_choix(appel_de_test):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    r = await jouer("ajouter", articles="une regina")
    assert r["statut"] == "CHOIX_OBLIGATOIRE", r
    assert r["restitution"] == "dit_par_le_code" and r["repondre"] == "ajouter.choix", r


async def test_un_refus_reste_au_jugement_du_modele(appel_de_test):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    r = await jouer("ajouter", articles="un zorglub")
    assert r["statut"] in ("INTROUVABLE", "HORS_CARTE"), r
    assert r.get("restitution") != "dit_par_le_code" and "repondre" not in r, r


async def test_le_reglage_de_la_fiche_de_l_outil_garde_la_main(appel_de_test):
    r = await appel_de_test.jouer("ajouter", config={"restitution": "reformule"}, articles="une regina normale")
    assert r["manque"] == "mode" and r["restitution"] == "reformule", r


async def test_ferme_la_personne_le_sait_des_la_question_du_mode_une_seule_fois(appel_de_test, commerce):
    await _ferme_a_midi(commerce, True)
    await commerce.c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND jour = $2 AND ouverture = '11:00'::time", commerce.a, JEUDI)
    jouer = appel_de_test.jouer
    r = await jouer("ajouter", articles="un coca")
    if r["manque"] == "mode":
        # Aucun mode ouvert à midi : la fermeture et la reprise passent AVANT la question du mode.
        assert "fermés" in r["suggestion"] and "dix-huit heures" in r["suggestion"] and r["suggestion"].endswith("?"), r
        assert r["restitution"] == "dit_par_le_code", r
        pose = await jouer("choisir_mode", mode="à emporter")
        assert pose["statut"] == "FERME_PLANIFIABLE", pose
        assert "fermés" not in (pose.get("suggestion") or pose.get("texte_a_dire") or ""), pose  # dite une fois
    else:
        raise AssertionError(f"la question du mode attendue : {r}")


async def test_ferme_sans_precommande_la_fermeture_seule(appel_de_test, commerce):
    await _ferme_a_midi(commerce, False)
    await commerce.c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = false WHERE site_id = $1", commerce.a)
    r = await appel_de_test.jouer("ajouter", articles="un coca")
    assert r.get("manque") != "mode" and "fermés" in r["suggestion"], r
    assert "emporter" not in r["suggestion"], r


async def test_voir_commande_avec_vider_recommence(appel_de_test):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="à emporter")
    await jouer("ajouter", articles="une regina normale et un coca")
    assert appel_de_test.fiche[panier.CLE]["lignes"]
    r = await jouer("voir_commande", vider=True)
    assert r["statut"] == "OK" and appel_de_test.fiche[panier.CLE]["lignes"] == [], r
    assert appel_de_test.fiche[panier.CLE]["mode"] == "emporter"


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
