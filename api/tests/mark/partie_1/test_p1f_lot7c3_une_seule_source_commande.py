"""[.mark] Fusion C1 + C2 : un texte de secours de la commande n'a qu'une source (``services.commande.textes_de_secours``) ; le catalogue de la base ne le recopie pas. Rien ne change à l'oreille."""

from __future__ import annotations

from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.commande import textes_de_secours as TS


def test_le_catalogue_de_la_base_ne_recopie_ni_la_rupture_ni_le_moyen_refuse():
    assert not hasattr(TSC, "indisponible") and not hasattr(TSC, "moyen_non_accepte")
    assert TS.n_est_plus_disponible({"nom": "Œuf"}) == "Œuf n'est plus disponible."


def test_la_fermeture_sans_heure_de_reprise_dit_la_phrase_de_la_commande():
    assert TSC.ferme_a_cette_heure({}) == TS.pas_de_commande_en_ce_moment({}) == "Nous ne prenons pas de commande en ce moment."
    assert TSC.ferme_a_cette_heure({"rouvre_dit": "dix-huit heures"}).startswith("À cette heure nous sommes fermés.")


def test_le_moyen_non_accepte_de_la_porte_reprend_celui_de_la_base_puis_dit_ceux_qui_sont_pris():
    faits = {"acceptes_dits": ["carte", "espèces"]}
    assert TS.moyen_refuse(faits) == "Ce moyen de paiement n'est pas accepté."
    assert TS.moyen_non_accepte(faits) == f"{TS.moyen_refuse(faits)} On prend : carte et espèces."
