"""[.mark] Chantier Partie 1, lot 19 bis, étape D : installation et futurs clients (note d'audit 3 de Pierre, § S, et S10 trouvé au déploiement de l'étape A).

Un test vu rouge par ligne (S1 à S10), sur la vraie porte, la vraie diffusion et la vraie installation (aucun appel à un modèle ni à un tiers).
"""

from __future__ import annotations

import pytest

from api.db.bases_clients.restauration_formulaire import horaires_en_texte
from api.services.pipecat.etat_ouverture import vers_expression_osm


# --------------------------------------------------------------------------- S10


def test_horaires_du_formulaire_jour_ferme_ecrit():
    """S10 : un jour fermé du formulaire s'écrit « dimanche : fermé » (source : ``horaires_en_texte`` n'écrivait que les jours ouverts, le lecteur
    exige les sept jours : « jours sans ligne : dimanche », un restaurant refusé au démarrage) ; le texte écrit est relu sans erreur ; un jour sans plage
    (liste vide) est un jour fermé aussi."""
    texte = horaires_en_texte({str(j): [["11:00", "14:00"], ["18:00", "22:30"]] for j in range(1, 7)})
    lignes = texte.splitlines()
    assert len(lignes) == 7 and lignes[6] == "dimanche : fermé", texte
    vers_expression_osm(texte)  # le lecteur du moteur accepte les sept jours
    avec_vide = horaires_en_texte({"1": [["09:00", "12:00"]], "2": []})
    assert avec_vide.splitlines()[1] == "mardi : fermé" and len(avec_vide.splitlines()) == 7
    vers_expression_osm(avec_vide)


# --------------------------------------------------------------------------- S9

from api.db import db_client  # noqa: E402
from api.db.bases_clients import connexion as schema  # noqa: E402
from api.services.gabarits import installation as I  # noqa: E402
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: E402,F401
from api.tests.mark.partie_1.test_l17_gabarit import FORMULAIRE_COMPLET, installe  # noqa: E402,F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402,F401


async def test_deux_restaurants_du_meme_nom(installe):
    """S9 : un second restaurant de même nom (donc de même clé) dans l'organisation est REFUSÉ, avec l'agent qui tient la clé ; le premier garde son
    adresse, ses zones et ses agents (source : ``ecrire_le_formulaire`` réécrivait l'établissement par ``ON CONFLICT (cle)``, le premier groupe servait
    l'autre adresse). Une clé libre n'est tenue par personne ; la reprise de la même installation (clé déjà notée au progrès) saute le contrôle."""
    autre_adresse = {**FORMULAIRE_COMPLET, "adresse": {"voie": "1 rue Autre", "code_postal": "60100", "commune": "Creil", "insee": "60175"}}
    with pytest.raises(I.ErreurInstallation) as refus:
        await I.installer(installe.user, installe.org, autre_adresse)
    assert refus.value.code == "gabarit_restaurant_deja_installe"
    assert refus.value.precisions == [str(installe.application["workflow_id"])]
    c = await schema.connecter(installe.base)
    try:
        assert await c.fetchval("SELECT adresse_commune FROM mark.site WHERE cle = $1", installe.application["formulaire"]["cle"]) == "Pont-Sainte-Maxence"
    finally:
        await c.close()
    cle = installe.application["formulaire"]["cle"]
    assert await I.application_qui_tient_la_cle(installe.org, "restauration", cle) == installe.application["workflow_id"]
    assert await I.application_qui_tient_la_cle(installe.org, "restauration", "autre-cle") is None
