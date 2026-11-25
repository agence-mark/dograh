"""[.mark] Lot 7b-C2, fermeture (``SourceClasseur.etat``) : l'heure de reprise que dit la phrase est un fait de l'état (``reprise_dite``), la règle de la pause appliquée par le code,
et la phrase (la clé ``phrase``, le texte de secours que lit le moteur) se refait de ``statut``, ``reprise_dite`` et ``planifiee_permise`` seuls."""

from __future__ import annotations

from datetime import timedelta

import pytest

from api.db.bases_clients import horloge
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

PROPOSE = " Je peux prendre votre commande pour plus tard, sur un créneau de la prochaine ouverture."


@pytest.fixture
def source(commerce):  # noqa: F811
    return SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")


async def _regler(commerce, colonne: str, valeur, type_: str = "emporter"):  # noqa: F811
    await commerce.c.execute(f"UPDATE mark.resto_reglage_type SET {colonne} = $3 WHERE site_id = $1 AND type = $2", commerce.a, type_, valeur)


async def test_ouvert_ne_dit_ni_phrase_ni_reprise(source):
    etat = await source.etat("emporter")
    assert (etat["ouvert"], etat["reprise_dite"], etat["phrase"]) == (True, None, "")


async def test_pause_a_reprise_connue_dit_la_reprise(commerce, source):  # noqa: F811
    await _regler(commerce, "pause_jusqu_a", JEUDI_MIDI + timedelta(minutes=30))
    etat = await source.etat("emporter")
    assert (etat["statut"], etat["en_pause"], etat["reprise_dite"]) == ("PAUSE_TYPE", True, "douze heures trente")
    assert etat["phrase"] == "Nous sommes en pause pour le moment. Nous reprenons à douze heures trente."
    assert etat["phrase"] == TSC.fermeture(etat)


async def test_pause_sans_reprise_connue_ne_dit_jamais_la_prochaine_ouverture(commerce, source):  # noqa: F811
    await commerce.c.execute("UPDATE mark.site SET etat_force = 'PAUSE', etat_force_jusqu_a = NULL WHERE id = $1", commerce.a)
    etat = await source.etat("emporter")
    assert etat["en_pause"] is True and etat["reprise"] is None
    assert etat["prochaine_ouverture"] is not None, "le cas n'a de dents que si les horaires donnent une prochaine ouverture"
    assert etat["reprise_dite"] is None
    assert etat["phrase"] == "Nous sommes en pause pour le moment." == TSC.fermeture(etat)


async def test_hors_horaires_dit_la_prochaine_ouverture(commerce, source):  # noqa: F811
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        etat = await source.etat("emporter")
    assert (etat["statut"], etat["en_pause"], etat["reprise"], etat["reprise_dite"]) == ("FERME", False, None, "dix-huit heures")
    assert etat["phrase"] == "Nous sommes fermés pour le moment. Nous reprenons à dix-huit heures." == TSC.fermeture(etat)


async def test_commande_pour_plus_tard_permise_la_propose(commerce, source):  # noqa: F811
    await _regler(commerce, "planifiee_permise", True)
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        etat = await source.etat("emporter")
    assert etat["planifiee_permise"] is True
    assert etat["phrase"] == "Nous sommes fermés pour le moment. Nous reprenons à dix-huit heures." + PROPOSE == TSC.fermeture(etat)


async def test_livraison_terminee_dit_sa_phrase(commerce, source):  # noqa: F811
    await _regler(commerce, "fin_par_jour", '{"4": "11:30"}', "livraison")
    etat = await source.etat("livraison")
    assert etat["statut"] == "LIVRAISON_TERMINEE" and etat["phrase"].startswith("Les livraisons sont terminées pour aujourd'hui.")
    assert etat["phrase"] == TSC.fermeture(etat)


async def test_la_phrase_se_refait_des_seuls_faits_statut_reprise_dite_et_planifiee_permise():
    """Rien d'autre que ces trois clés n'entre dans le texte : un état écrit à la main suffit."""
    assert TSC.fermeture({"statut": "FERME", "reprise_dite": None, "planifiee_permise": False}) == "Nous sommes fermés pour le moment."
    assert TSC.fermeture({"statut": "PAUSE_TYPE", "reprise_dite": "vingt heures", "planifiee_permise": True}) == (
        "Nous sommes en pause pour le moment. Nous reprenons à vingt heures." + PROPOSE)
    assert TSC.fermeture({"statut": "LIVRAISON_TERMINEE", "reprise_dite": None, "planifiee_permise": False}) == "Les livraisons sont terminées pour aujourd'hui."
