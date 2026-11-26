"""[.mark] Lot 7b-C2, fermeture (``SourceClasseur.etat``) : l'heure de reprise que dit la phrase est un fait de l'état (``reprise_dite``), la règle de la pause appliquée par le code,
et ce que disait le texte de secours d'avant tient dans ``statut``, ``reprise_dite`` et ``planifiee_permise`` (C7 B9 : catalogue supprimé) ; l'état ne porte plus de clé ``phrase`` (lot 7b-C7)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from api.db.bases_clients import horloge
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.source_commande import SourceClasseur
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark import test_base_client as BASE
from api.tests.mark import test_restauration_classeur_commande as CLASSEUR

# Les fixtures du classeur, reprises par affectation (jamais d'import qui ne sert qu'à les enregistrer).
base_essai, base_prete, commerce = BASE.base_essai, BASE.base_prete, CLASSEUR.commerce

@pytest.fixture
def source(commerce):
    return SourceClasseur(commerce.c, Lieu(commerce.base, commerce.a, 1), nom_prise="test")


async def _regler(commerce, colonne: str, valeur, type_: str = "emporter"):
    await commerce.c.execute(f"UPDATE mark.resto_reglage_type SET {colonne} = $3 WHERE site_id = $1 AND type = $2", commerce.a, type_, valeur)


async def test_ouvert_ne_dit_ni_phrase_ni_reprise(source):
    etat = await source.etat("emporter")
    assert (etat["ouvert"], etat["reprise_dite"], "phrase" in etat) == (True, None, False)


async def test_pause_a_reprise_connue_dit_la_reprise(commerce, source):
    await _regler(commerce, "pause_jusqu_a", JEUDI_MIDI + timedelta(minutes=30))
    etat = await source.etat("emporter")
    assert (etat["statut"], etat["en_pause"], etat["reprise_dite"]) == ("PAUSE_TYPE", True, "douze heures trente")
    assert "phrase" not in etat  # C7 : la source n'écrit aucune phrase, le modèle la dit des faits
    assert (etat["statut"], etat["reprise_dite"], etat["planifiee_permise"]) == ('PAUSE_TYPE', 'douze heures trente', False)


async def test_pause_sans_reprise_connue_ne_dit_jamais_la_prochaine_ouverture(commerce, source):
    await commerce.c.execute("UPDATE mark.site SET etat_force = 'PAUSE', etat_force_jusqu_a = NULL WHERE id = $1", commerce.a)
    etat = await source.etat("emporter")
    assert etat["en_pause"] is True and etat["reprise"] is None
    assert etat["prochaine_ouverture"] is not None, "le cas n'a de dents que si les horaires donnent une prochaine ouverture"
    assert etat["reprise_dite"] is None
    assert "phrase" not in etat and (etat["statut"], etat["reprise_dite"], etat["planifiee_permise"]) == ('PAUSE_TYPE', None, False)


async def test_hors_horaires_dit_la_prochaine_ouverture(commerce, source):
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        etat = await source.etat("emporter")
    assert (etat["statut"], etat["en_pause"], etat["reprise"], etat["reprise_dite"]) == ("FERME", False, None, "dix-huit heures")
    assert "phrase" not in etat and (etat["statut"], etat["reprise_dite"], etat["planifiee_permise"]) == ('FERME', 'dix-huit heures', False)


async def test_commande_pour_plus_tard_permise_la_propose(commerce, source):
    await _regler(commerce, "planifiee_permise", True)
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        etat = await source.etat("emporter")
    assert etat["planifiee_permise"] is True
    assert "phrase" not in etat and (etat["statut"], etat["reprise_dite"], etat["planifiee_permise"]) == ('FERME', 'dix-huit heures', True)


async def test_livraison_terminee_dit_sa_phrase(commerce, source):
    await _regler(commerce, "fin_par_jour", '{"4": "11:30"}', "livraison")
    etat = await source.etat("livraison")
    assert etat["statut"] == "LIVRAISON_TERMINEE" and "phrase" not in etat
    assert (etat["statut"], etat["reprise_dite"], etat["planifiee_permise"]) == ('LIVRAISON_TERMINEE', 'dix-huit heures', False)


async def test_l_etat_d_ouverture_n_a_pas_de_cle_phrase(commerce, source):
    """C7 (A4) : la source n'écrit plus de phrase de fermeture (C7a) ; la clé ``phrase``, toujours vide, part avec ses lecteurs. Ni l'état d'un mode, ni la lecture
    de l'ouverture (décroché, état, outils) ne la portent, ouvert comme fermé : le modèle dit l'ouverture d'après le statut et les faits."""
    from api.services.commande import moteur

    ouvert, lu_ouvert = await source.etat("emporter"), await moteur.lire_l_ouverture(source, "emporter")
    await _regler(commerce, "pause_jusqu_a", JEUDI_MIDI + timedelta(minutes=30))
    ferme, lu_ferme = await source.etat("emporter"), await moteur.lire_l_ouverture(source, "emporter")
    assert (ouvert["ouvert"], lu_ouvert["ouvert"], ferme["ouvert"], lu_ferme["ouvert"]) == (True, True, False, False)
    assert not [e for e in (ouvert, lu_ouvert, ferme, lu_ferme) if "phrase" in e], (ouvert, lu_ouvert, ferme, lu_ferme)
