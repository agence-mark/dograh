"""[.mark] Lot « façon Tala par motif », T2 et T3 : les cinq contrôles de rédaction K1 à K5 (règles pures) et la règle ``longueur``.

Chaque règle est vue rouge quand elle est débranchée ; « Éteint » = aucun défaut ; « Prévient » (défaut) = AVERTISSEMENT ;
« Bloque » = BLOQUANT (K1 à K4) ; K5 n'est JAMAIS bloquant. Textes d'essai génériques : aucun mot de métier.
"""

from __future__ import annotations

from api.services.builder.controle import regles
from api.services.builder.controle.regles import AVERTISSEMENT, BLOQUANT, Entree, ObjetConnu, OutilConnu


def noeud(identifiant, type_, nom, prompt="", **donnees):
    return {"id": identifiant, "type": type_, "position": {"x": 0, "y": 0}, "data": {"name": nom, "prompt": prompt, **donnees}}


def lien(a, b, label="x", condition="y"):
    return {"id": f"{a}-{b}", "source": a, "target": b, "data": {"label": label, "condition": condition}}


def graphe(*noeuds_, liens=None):
    return {"nodes": list(noeuds_), "edges": liens if liens is not None else [lien("1", "2")]}


def sain(prompt="Accueille la personne et demande ce dont elle a besoin."):
    return graphe(noeud("1", "startCall", "Départ", prompt), noeud("2", "endCall", "Fin", "Dis au revoir poliment."))


def codes(defauts, gravite=None):
    return {d.code for d in defauts if gravite is None or d.gravite == gravite}


def controle(g, **plus):
    return regles.controler(Entree(graphe=g, **plus))


# --- K1 valeur_en_dur ------------------------------------------------------------------------------------------------


def test_k1_un_montant_un_delai_chiffre_ou_un_prenom_en_exemple_previennent():
    for prompt in (
        "Dis que la visite coûte 45 euros.",
        "Annonce un rappel sous 48 heures.",
        "Dis que le tarif est de 12,50 € par mois.",
        "Salue la personne, par exemple Marie, puis demande ce dont elle a besoin.",
    ):
        defauts = [d for d in controle(sain(prompt)) if d.code == "valeur_en_dur"]
        assert defauts and all(d.gravite == AVERTISSEMENT for d in defauts), prompt
        assert defauts[0].etape == "Départ" and defauts[0].extrait


def test_k1_une_variable_ou_un_texte_sans_valeur_ne_previent_pas():
    assert "valeur_en_dur" not in codes(controle(sain("Dis que la visite coûte {{prix}} et que le rappel arrive sous {{delai}}.")))
    assert "valeur_en_dur" not in codes(controle(sain("Accueille la personne et demande ce dont elle a besoin.")))


def test_k1_complete_fait_en_dur_sans_la_remplacer():
    prompt = "Dis que la visite coûte 45 euros. Les tarifs : Visite | quarante-cinq euros par personne"
    defauts = controle(sain(prompt), objets=[ObjetConnu("tarifs", "Visite | quarante-cinq euros par personne")])
    assert {"valeur_en_dur", "fait_en_dur"} <= codes(defauts)


def test_k1_les_trois_positions():
    g = sain("Dis que la visite coûte 45 euros.")
    assert "valeur_en_dur" not in codes(controle(g, redaction={"valeur_en_dur": "eteint"}))
    assert "valeur_en_dur" in codes(controle(g, redaction={"valeur_en_dur": "previent"}), AVERTISSEMENT)
    assert "valeur_en_dur" in codes(controle(g, redaction={"valeur_en_dur": "bloque"}), BLOQUANT)


# --- K2 verbe_ecran --------------------------------------------------------------------------------------------------


def test_k2_un_verbe_d_ecran_dans_un_prompt_vocal_previent():
    for prompt in ("Demande à la personne de cliquer sur le lien.", "Dis que le récapitulatif s'affiche à l'écran.", "Tell the caller to click the button."):
        defauts = [d for d in controle(sain(prompt)) if d.code == "verbe_ecran"]
        assert defauts and defauts[0].gravite == AVERTISSEMENT, prompt


def test_k2_un_prompt_sans_verbe_d_ecran_et_l_extinction():
    assert "verbe_ecran" not in codes(controle(sain("Dis que tu envoies un message avec le lien.")))
    assert "verbe_ecran" not in codes(controle(sain("Demande de cliquer sur le lien."), redaction={"verbe_ecran": "eteint"}))
    assert "verbe_ecran" in codes(controle(sain("Demande de cliquer sur le lien."), redaction={"verbe_ecran": "bloque"}), BLOQUANT)


# --- K3 action_sans_outil ----------------------------------------------------------------------------------------------

ECRIVAIN = OutilConnu("u-ecrit", "Enregistrer", "http_api", "POST")
LECTEUR = OutilConnu("u-lit", "Chercher", "http_api", "GET")


def etape_avec(prompt, *uuids):
    return graphe(
        noeud("1", "startCall", "Départ", "Accueille."),
        noeud("3", "agentNode", "Travail", prompt, tool_uuids=list(uuids)),
        noeud("2", "endCall", "Fin", "Au revoir."),
        liens=[lien("1", "3"), lien("3", "2")],
    )


def test_k3_une_action_promise_sans_aucun_outil_previent():
    defauts = [d for d in controle(etape_avec("Réserve le créneau puis enregistre la demande.")) if d.code == "action_sans_outil"]
    assert defauts and defauts[0].gravite == AVERTISSEMENT and defauts[0].etape == "Travail"


def test_k3_un_outil_qui_ne_fait_que_lire_ne_suffit_pas_mais_un_outil_qui_ecrit_oui():
    outils = {ECRIVAIN.uuid: ECRIVAIN, LECTEUR.uuid: LECTEUR}
    assert "action_sans_outil" in codes(controle(etape_avec("Enregistre la demande.", "u-lit"), outils=outils))
    assert "action_sans_outil" not in codes(controle(etape_avec("Enregistre la demande.", "u-ecrit"), outils=outils))
    assert "action_sans_outil" not in codes(controle(etape_avec("Demande le nom de la personne."), outils=outils))


def test_k3_etend_outil_d_ecriture_sans_relecture_sans_le_remplacer():
    outils = {ECRIVAIN.uuid: ECRIVAIN}
    defauts = controle(etape_avec("Enregistre la demande.", "u-ecrit"), outils=outils)
    assert "outil_d_ecriture_sans_relecture" in codes(defauts)  # le cas « outil sans relecture » reste la règle d'avant
    assert "action_sans_outil" not in codes(defauts)


def test_k3_les_trois_positions():
    g = etape_avec("Enregistre la demande.")
    assert "action_sans_outil" not in codes(controle(g, redaction={"action_sans_outil": "eteint"}))
    assert "action_sans_outil" in codes(controle(g, redaction={"action_sans_outil": "bloque"}), BLOQUANT)


# --- K4 sortie_non_citee -------------------------------------------------------------------------------------------------


def deux_sorties(prompt):
    return graphe(
        noeud("1", "startCall", "Accueil", prompt),
        noeud("3", "agentNode", "Rendez-vous", "Prends le rendez-vous."),
        noeud("4", "agentNode", "Réclamation", "Écoute la réclamation."),
        noeud("2", "endCall", "Fin", "Au revoir."),
        liens=[lien("1", "3", "Veut un rendez-vous"), lien("1", "4", "Se plaint"), lien("3", "2"), lien("4", "2")],
    )


def test_k4_deux_sorties_de_travail_dont_aucune_n_est_citee_previennent():
    defauts = [d for d in controle(deux_sorties("Accueille la personne.")) if d.code == "sortie_non_citee"]
    assert len(defauts) == 1 and defauts[0].gravite == AVERTISSEMENT and defauts[0].etape == "Accueil"


def test_k4_une_etape_visee_citee_par_son_nom_ou_par_le_libelle_de_la_liaison_ne_previent_pas():
    assert "sortie_non_citee" not in codes(controle(deux_sorties("Accueille, puis passe à l'étape Rendez-vous ou Réclamation.")))
    assert "sortie_non_citee" not in codes(controle(deux_sorties("Accueille. Si la personne se plaint, oriente-la.")))


def test_k4_une_seule_sortie_de_travail_ne_previent_pas_et_les_positions():
    assert "sortie_non_citee" not in codes(controle(sain()))
    assert "sortie_non_citee" not in codes(controle(deux_sorties("Accueille."), redaction={"sortie_non_citee": "eteint"}))
    assert "sortie_non_citee" in codes(controle(deux_sorties("Accueille."), redaction={"sortie_non_citee": "bloque"}), BLOQUANT)


# --- K5 poids_agent ---------------------------------------------------------------------------------------------------------


def test_k5_le_poids_est_calcule_sur_les_vrais_textes_etape_par_etape():
    g = graphe(
        noeud("0", "globalNode", "Global", "G" * 100),
        noeud("1", "startCall", "Accueil", "A" * 50),
        noeud("3", "agentNode", "Travail", "T" * 300),
        noeud("2", "endCall", "Fin", "F" * 10),
        liens=[lien("1", "3", "ab", "c" * 20), lien("3", "2", "xyz", "d" * 40), lien("3", "1", "q", "r" * 9)],
    )
    poids = {p.etape: p for p in regles.poids_par_etape(g)}
    accueil, travail = poids["Accueil"], poids["Travail"]
    assert (accueil.general, accueil.texte, accueil.conditions, accueil.nb_conditions) == (100, 50, 22, 1)
    assert (travail.general, travail.texte, travail.conditions, travail.nb_conditions) == (100, 300, 43 + 10, 2)
    assert travail.total == 100 + 300 + 53
    assert regles.poids_par_etape(g)[0].etape == "Travail"  # du plus lourd au plus léger


def test_k5_sans_seuil_aucun_defaut_seuil_depasse_avertissement_jamais_blocage():
    g = sain("A" * 400)
    assert "poids_agent" not in codes(controle(g))  # vide = aucun seuil
    defauts = [d for d in controle(g, poids_max=200) if d.code == "poids_agent"]
    assert defauts and all(d.gravite == AVERTISSEMENT for d in defauts)
    assert "poids_agent" not in codes(controle(g, poids_max=200, redaction={"poids_agent": "eteint"}))
    # Même une position « bloque » écrite à la main ne bloque pas : K5 n'a que Éteint et Prévient.
    assert codes(controle(g, poids_max=200, redaction={"poids_agent": "bloque"}), BLOQUANT) == set()
    assert "poids_agent" not in codes(controle(g, poids_max=100000))


# --- longueur : avertissement, plafond lu dans le réglage -------------------------------------------------------------------


def test_longueur_est_un_avertissement_muet_sans_plafond():
    long = "Parle avec des phrases courtes. " * 20
    assert "longueur" not in codes(controle(sain(long)))  # vide = aucun seuil
    defauts = [d for d in controle(sain(long), plafond=100) if d.code == "longueur"]
    assert defauts and defauts[0].gravite == AVERTISSEMENT
    assert "longueur" not in codes(controle(sain(long), plafond=5000))
