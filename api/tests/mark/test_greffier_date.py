"""[.mark] La date du jour donnée au greffier (chantier repliques-coupees, lot 5, décision D3 du 14/10).

Run 1175 : « octobre l'an dernier » devenait « octobre 2022 » sous la plume du greffier, refusé par
le code à chaque tour, champ perdu : le greffier ne savait pas en quelle année on était. Son message
commence désormais par la date de l'appel, au fuseau de Paris, côté serveur ; le calcul reste au
modèle. Chaque cas a été vu ROUGE avant d'être vert (R7).

| Test | Ce qu'il prouve |
|---|---|
| la phrase | jour, quantième, mois, année en toutes lettres, sans mot de métier ; « 1er » |
| le fuseau | 23 h 30 en temps universel le 14 est déjà le jeudi 15 à Paris |
| le message | la date ouvre le message, avant la fiche ; sans date, le message d'avant à l'octet |
| la vraie passe (R1) | une passe du greffier envoie au modèle un message qui contient l'année de l'appel |
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from api.services.pipecat import greffier as module
from api.services.pipecat.greffier import date_du_jour, message_du_greffier
from api.services.workflow.dates_relatives import FUSEAU
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.mark.test_greffier import FICHE_GREFFIER, _Modele, _Montage


def test_la_phrase_dit_le_jour_sans_mot_de_metier():
    assert (
        date_du_jour(datetime(2026, 10, 14, 20, 0, tzinfo=FUSEAU))
        == "Nous sommes le mercredi 14 octobre 2026."
    )
    assert (
        date_du_jour(datetime(2026, 8, 1, 9, 0, tzinfo=FUSEAU))
        == "Nous sommes le samedi 1er août 2026."
    )


def test_la_date_est_celle_de_paris():
    assert (
        date_du_jour(datetime(2026, 10, 14, 23, 30, tzinfo=UTC))
        == "Nous sommes le jeudi 15 octobre 2026."
    )


def test_la_date_ouvre_le_message_et_sans_elle_rien_ne_change():
    reglages = ReglagesFiche.depuis(FICHE_GREFFIER)
    messages = [{"role": "user", "content": "Le dernier entretien, c'était en octobre l'an dernier."}]
    sans = message_du_greffier(reglages, {}, messages)
    avec = message_du_greffier(
        reglages, {}, messages, aujourd_hui="Nous sommes le mercredi 14 octobre 2026."
    )
    assert avec.startswith("# Aujourd'hui\nNous sommes le mercredi 14 octobre 2026.\n\n# La fiche actuelle")
    assert avec.endswith(sans)
    assert sans.startswith("# La fiche actuelle")


@pytest.mark.asyncio
async def test_une_passe_du_greffier_donne_l_annee_au_modele():
    modele = _Modele({})
    montage = _Montage(modele)
    with patch.object(
        module, "date_du_jour", return_value="Nous sommes le mercredi 14 octobre 2026."
    ):
        await montage.greffier.une_passe()
    assert modele.lus, "le modèle du greffier n'a rien reçu"
    assert modele.lus[-1].startswith("# Aujourd'hui\nNous sommes le mercredi 14 octobre 2026.")


@pytest.mark.asyncio
async def test_sans_rien_simuler_la_passe_porte_l_annee_en_cours():
    modele = _Modele({})
    await _Montage(modele).greffier.une_passe()
    assert str(datetime.now(FUSEAU).year) in modele.lus[-1].split("\n")[1]
