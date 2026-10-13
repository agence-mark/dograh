"""[.mark] Garantie : la voix dit une adresse mail en mots (plan courriel-dicte, lot 2).

Au lot 0, l'agent écrivait l'adresse de trois façons (runs 324, 330, 386) et elle partait telle
quelle à la voix. Écrite en mots juste avant la voix, la relecture est la même d'un appel à
l'autre ; la conversation, elle, garde ce que le modèle a écrit.
"""

from __future__ import annotations

import pytest

from api.services.epellation.voix import courriels_pour_la_voix, dire_courriel
from api.services.pipecat.courriels_pour_la_voix import courriels_en_mots
from api.services.pipecat.service_factory import construire_remplacements_de_voix


@pytest.mark.parametrize(
    "adresse,dite",
    [
        ("evan.vdk@outlook.fr", "evan point v d k arobase outlook point f r"),
        ("evan.jourde@gmail.com", "evan point jourde arobase gmail point com"),
        (
            "contact@boulangerie-lemoine.fr",
            "contact arobase boulangerie tiret lemoine point f r",
        ),
        (
            "jean@mairie-creil.gouv.fr",
            "jean arobase mairie tiret creil point gouv point f r",
        ),
        (
            "marie_dupont75@hotmail.fr",
            "marie tiret bas dupont 75 arobase hotmail point f r",
        ),
        ("paul+devis@laposte.net", "paul plus devis arobase laposte point net"),
        ("Evan.VDK@Outlook.FR", "evan point v d k arobase outlook point f r"),
        ("jb@free.eu", "j b arobase free point e u"),
    ],
)
def test_ladresse_dite_en_mots(adresse, dite):
    assert dire_courriel(adresse) == dite


def test_dans_une_phrase_seule_ladresse_change():
    assert (
        courriels_pour_la_voix(
            "D'accord, je relis : **Evan.vdk@outlook.fr**. C'est bien ça ?"
        )
        == "D'accord, je relis : **evan point v d k arobase outlook point f r**. C'est bien ça ?"
    )
    texte = "Rendez-vous à 14 h, au 12 rue Danton."
    assert courriels_pour_la_voix(texte) is texte


async def test_les_chiffres_de_ladresse_sont_dits_par_les_nombres_apres():
    """🔴 R1 : la vraie chaîne des transformations de la voix, dans son ordre."""
    texte = "Je relis : jean75@orange.fr, au 03 44 22 10 60."
    for _, transformation in construire_remplacements_de_voix({}, True):
        texte = await transformation(texte, "sentence")
    assert texte == (
        "Je relis : jean soixante-quinze arobase orange point f r, "
        "au zéro trois, quarante-quatre, vingt-deux, dix, soixante."
    )


def test_un_agent_non_francais_ou_mot_a_mot_ne_la_recoit_pas():
    assert courriels_en_mots not in [
        t for _, t in construire_remplacements_de_voix({}, False)
    ]
    assert (
        construire_remplacements_de_voix({"tts_text_aggregation_mode": "token"}, True)
        == []
    )


async def test_une_erreur_rend_le_texte_tel_quel(monkeypatch):
    """⛔ Pipecat perd l'audio de la phrase quand une transformation lève."""
    from api.services.pipecat import courriels_pour_la_voix as module

    def casse(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "courriels_pour_la_voix", casse)
    assert await courriels_en_mots("evan@gmail.com") == "evan@gmail.com"
