"""[.mark] Lot 8, tranche 8d : un outil qui propose un texte (``texte_a_dire`` ou ``suggestion``) ne le fait jamais dire par le code.

Décision d'Evan (25/11 8 h 45, ``REPRISE.md`` § 3, l. 30-31) : « le modèle parle, jamais le code ; aucun texte de secours dit par le code ». Les deux lecteurs
(``reponse_avalee.texte_du_dernier_outil``, ``verite_des_actions.texte_demande_par``) disaient pourtant à la voix le texte d'un outil quand le modèle restait muet ou
affirmait le faux. Ici : le modèle muet ou fautif est relancé ou remplacé par la phrase réglée « réponse perdue », jamais par le texte de l'outil ; et les deux
outils hors fiche du connecteur (garde « échec répété », garde « confirmation avant la réponse ») rendent leurs faits, pas une phrase.
"""

from __future__ import annotations

import json

from api.services.integrations.connectors import confirmation, garde
from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin, phrase_de_repli
from api.services.workflow.verite_des_actions import affirmation_sans_outil_fait
from api.tests.mark.test_reponse_avalee import FLUX_AVALE, _Base, _reponse
from api.tests.mark.test_reponse_coupee_apres_outil import _apres_l_outil, _lire_tout, _texte

PHRASE_DE_L_OUTIL = "Quel est votre numéro de téléphone ?"
RESULTATS = {
    "suggestion au premier niveau": {"statut": "INCOMPLETE", "faits": {}, "suggestion": PHRASE_DE_L_OUTIL, "manque": "telephone"},
    "texte_a_dire": {"statut": "INCOMPLETE", "faits": {}, "texte_a_dire": PHRASE_DE_L_OUTIL, "restitution": "mot_pour_mot", "manque": "telephone"},
    "suggestion dans data": {"statut": "INCOMPLETE", "data": {"suggestion": PHRASE_DE_L_OUTIL}, "manque": "telephone"},
}


class _Service(RepriseSansFluxMixin, _Base):
    pass


async def test_modele_muet_apres_un_outil_qui_pose_un_texte_le_code_ne_dit_pas_ce_texte():
    for nom, resultat in RESULTATS.items():
        for service in (_Service(FLUX_AVALE, reprise=_reponse()), _Service(FLUX_AVALE, erreur=RuntimeError("x"))):
            dit = _texte(await _lire_tout(service, _apres_l_outil(resultat)))
            assert PHRASE_DE_L_OUTIL not in dit, f"{nom} : le code a dit le texte de l'outil : {dit!r}"


def test_une_affirmation_fausse_n_est_jamais_remplacee_par_le_texte_de_l_outil():
    for nom, resultat in RESULTATS.items():
        messages = [
            {"role": "user", "content": "Mon numéro, c'est le deux."},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "t", "type": "function", "function": {"name": "outil", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "t", "content": json.dumps(resultat, ensure_ascii=False)},
        ]
        retenue = affirmation_sans_outil_fait("C'est noté, c'est enregistré.", messages)
        assert retenue is not None, nom
        assert retenue.a_dire is None, f"{nom} : la retenue remplace la réplique par le texte de l'outil : {retenue.a_dire!r}"


def test_l_echec_repete_donne_un_fait_pas_une_phrase():
    retour = garde.retour_d_echec_repete("INTROUVABLE")
    assert "suggestion" not in retour and "texte_a_dire" not in retour, retour
    assert retour["statut"] == garde.STATUT_ECHEC_REPETE
    assert retour["faits"]["dernier_statut"] == "INTROUVABLE" and retour["faits"]["deja_echoue_deux_fois"] is True
    assert retour["consigne"] == garde.STRATEGIE  # pour le modèle seulement : jamais lue comme un texte à dire


def test_la_confirmation_trop_tot_ne_porte_aucune_suggestion_meme_vide():
    from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

    fiche = {confirmation.CLE_RELECTURES: {"a": 3}, CLE_TOUR: 3}
    refus = confirmation.confirmation_avant_la_reponse(fiche, "a", {"confirmer": True})
    assert refus is not None and refus["manque"] == "reponse_a_la_relecture"
    assert "suggestion" not in refus, refus
    assert phrase_de_repli(_Service([])) is not None  # la phrase réglée reste là pour le modèle muet


async def test_l_echec_repete_est_un_resultat_qui_attend_une_reponse_modele_muet_phrase_reglee():
    """Reprise R2 : l'échec répété ne porte plus de texte, seulement une consigne : un modèle muet et une relance vide ne font jamais un tour muet."""
    retour = garde.retour_d_echec_repete("INTROUVABLE")
    for service in (_Service(FLUX_AVALE, reprise=_reponse()), _Service(FLUX_AVALE, erreur=RuntimeError("x"))):
        assert _texte(await _lire_tout(service, _apres_l_outil(retour))) == phrase_de_repli(service)
