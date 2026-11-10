"""[.mark] Clôture D2 (É69) : le chat dit « Tours 1 à N résumés » : combien de tours sont passés au résumé, et quand.

| Test | La garantie |
|---|---|
| compte | seuls les messages de la PERSONNE comptent comme des tours ; le compteur s'ajoute d'un résumé à l'autre |
| plafond | un chat trop long (lignes) note ses tours résumés comme le résumé par le cerveau |
| vue | la liste des chats donne le compteur sans le texte ; la lecture d'un chat donne aussi le texte |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.routes.builder_fils import _vue
from api.services.builder import contexte


def _tours(n):
    return [m for i in range(n) for m in ({"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"r{i}"})]


def test_le_compteur_ne_compte_que_les_tours_de_la_personne_et_s_additionne():
    conv = contexte.conversation_vide()
    contexte.noter_le_resume(conv, _tours(3))
    assert conv["tours_resumes"] == 3 and conv["resume_le"]
    contexte.noter_le_resume(conv, _tours(2))
    assert conv["tours_resumes"] == 5


def test_un_chat_au_dela_du_plafond_note_ses_tours_resumes(monkeypatch):
    monkeypatch.setattr(contexte, "CONVERSATION_MESSAGES_MAX", 10)
    conv = {**contexte.conversation_vide(), "messages": _tours(12)}
    contexte.borner(conv)
    assert conv["tours_resumes"] >= 1 and conv["resume"]


def _fil(historique):
    return SimpleNamespace(
        id=1, workflow_id=None, titre="t", etat="terminee", jetons=0, cout=0.0, jauge=0.0, changements=0, demarrage=None,
        cree_le=None, modifie_le=None, genre="principal", parent_id=None, sous_agents_actifs=True, auteur=None, historique=historique,
    )


def test_la_liste_donne_le_compteur_sans_le_texte_la_lecture_donne_aussi_le_texte(monkeypatch):
    from api.services.builder import fil as service_fil

    monkeypatch.setattr(service_fil, "en_cours", lambda _id: False)
    fil = _fil({"resume": "Dossiers lus ; 2 tests écrits.", "tours_resumes": 24, "resume_le": "2026-11-09T10:00:00+00:00"})
    liste, lecture = _vue(fil), _vue(fil, avec_resume=True)
    assert liste.tours_resumes == 24 and liste.resume is None
    assert lecture.tours_resumes == 24 and lecture.resume == "Dossiers lus ; 2 tests écrits."
