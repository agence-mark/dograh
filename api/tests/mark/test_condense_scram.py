"""[.mark] Le condensé SCRAM-SHA-256 que l'api passe à la base pour le compte du portail (revue du
chantier cloture-code). La preuve qu'il ouvre la base : ``test_connexion_portail_et_logiciels.py``."""

import base64

from api.services.base_client.condense_scram import ITERATIONS, condense_scram


def test_le_condense_a_le_format_de_postgres_et_ne_contient_pas_le_mot_de_passe():
    mot_de_passe = "un-mot-de-passe-assez-long-0123456789"
    condense = condense_scram(mot_de_passe)
    methode, reste = condense.split("$", 1)
    iterations_et_sel, cles = reste.split("$")
    iterations, sel = iterations_et_sel.split(":")
    cle_stockee, cle_serveur = cles.split(":")
    assert methode == "SCRAM-SHA-256" and int(iterations) == ITERATIONS
    assert len(base64.b64decode(sel)) == 16
    assert len(base64.b64decode(cle_stockee)) == 32 and len(base64.b64decode(cle_serveur)) == 32
    assert mot_de_passe not in condense
    # Assez long pour le contrôle de la 015 (12 caractères au moins).
    assert len(condense) >= 12


def test_le_meme_sel_rend_le_meme_condense_un_sel_neuf_un_autre():
    sel = b"\x01" * 16
    assert condense_scram("abc", sel=sel) == condense_scram("abc", sel=sel)
    assert condense_scram("abc") != condense_scram("abc")
