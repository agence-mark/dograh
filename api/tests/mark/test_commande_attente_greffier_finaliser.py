"""[.mark] Agent fiable (appel 2628) : ``finaliser`` n'attend le greffier que pour la note de la question posée, et jamais quand le modèle
l'a déjà passée. Avant : 2,3 s et 2,7 s perdues (prénom, puis numéro passés par le modèle), et l'attente portait toujours sur le prénom."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.commande import action


def test_rien_a_attendre_quand_le_modele_a_passe_la_valeur():
    assert action.note_attendue({"question_en_attente": "finaliser.prenom"}, {"prenom": "Evan"}) is None
    assert action.note_attendue({"question_en_attente": "finaliser.telephone"}, {"telephone": "0788261409"}) is None


def test_l_attente_porte_sur_la_question_posee():
    assert action.note_attendue({"question_en_attente": "finaliser.prenom"}, {}) == "prenom"
    assert action.note_attendue({"question_en_attente": "finaliser.telephone"}, {"prenom": "Evan"}) == "telephone"
    assert action.note_attendue({"question_en_attente": "finaliser.moyen"}, {}) is None
    assert action.note_attendue({}, {}) is None


async def test_le_numero_absent_est_attendu_meme_si_le_prenom_est_note():
    appels = []

    async def rattraper(delai):
        appels.append(delai)

    ctx = SimpleNamespace(fiche={"prenom": "Evan"}, rattraper=rattraper)
    await action._notes_a_jour(ctx, "telephone")
    assert appels == [action.ATTENTE_DU_GREFFIER_S]
