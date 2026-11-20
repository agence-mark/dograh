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
