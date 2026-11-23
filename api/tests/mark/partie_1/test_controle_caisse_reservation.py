"""[.mark] Correctifs d'avant le banc (23/11), points de Pierre sur la caisse et la réservation, un test par point.

| Test | Ce qu'il prouve |
|---|---|
| A5 | une panne (erreur ou coupure) à l'enregistrement après le « oui » laisse la question posée : un second « oui » enregistre la réservation |
"""

from __future__ import annotations

import asyncio

import pytest

from api.services.reservation import moteur
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation import PARIS, SAMEDI_20H, salle  # noqa: F401


@pytest.mark.parametrize("panne", [RuntimeError("base coupée"), asyncio.TimeoutError()])
async def test_a5_oui_apres_une_panne_enregistre_la_reservation(salle, monkeypatch, panne):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    assert q["type"] == "recapitulatif", r
    vrai = moteur.reserver
    pannes = [panne]

    async def reserver_en_panne(*a, **k):
        if pannes and k.get("confirmer"):
            raise pannes.pop()
        return await vrai(*a, **k)

    monkeypatch.setattr(moteur, "reserver", reserver_en_panne)
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert await essai.nombre_de_reservations() == 0 and r["statut"] != "ENREGISTREE", r
    assert (essai.etat.get("question") or {}).get("id") == q["id"], essai.etat.get("question")  # la question attend toujours
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE" and await essai.nombre_de_reservations() == 1, r
