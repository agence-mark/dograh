"""[.mark] SA-18, lot C (C16) : un émoji n'est jamais dit à la voix, quel que soit l'agent (filtre du flux du cerveau).

Aux essais du 17/11, « 😊 » passait dans une phrase d'au revoir.
"""

import pytest

from api.services.pipecat.texte_du_cerveau import FluxNettoye, sans_emojis
from api.tests.mark.test_verite_des_actions import _morceau


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Merci, à bientôt 😊", "Merci, à bientôt "),
        ("Parfait ! 😊 Votre commande est prête.", "Parfait ! Votre commande est prête."),
        ("Bon appétit 🍕🍝 !", "Bon appétit !"),
        ("Merci 👍🏽 à vous", "Merci à vous"),
        ("Drapeau 🇫🇷 ici", "Drapeau ici"),
        ("Rien à retirer, même avec → une flèche.", "Rien à retirer, même avec → une flèche."),
        ("Un prix de 12,90 € et un numéro 06 12.", "Un prix de 12,90 € et un numéro 06 12."),
    ],
)
def test_les_emojis_partent_les_blancs_se_reduisent_a_un(texte, attendu):
    assert sans_emojis(texte) == attendu


def test_un_morceau_sans_blanc_autour_n_en_gagne_pas():
    assert sans_emojis("😊") == "" and sans_emojis("Oui😊") == "Oui"


async def test_le_flux_du_cerveau_rend_un_texte_sans_emoji():
    async def flux():
        for t in ("Merci ", "😊", " à bientôt."):
            yield _morceau(t)

    sortie = [m.choices[0].delta.content async for m in FluxNettoye(flux(), [], False)]
    assert "😊" not in "".join(sortie) and "".join(sortie).replace("  ", " ").strip() == "Merci à bientôt."
