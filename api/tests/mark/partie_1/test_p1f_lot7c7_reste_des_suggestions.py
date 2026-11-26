"""[.mark] C7 B5, la suite : les dernières phrases que le moteur de la commande composait encore n'ont plus de texte ; ce qu'elles apprenaient reste dans les faits.

Décisions d'Evan 25/11 : le code ne compose aucune phrase, le modèle parle (8 h 45, 9 h) ; « pas juste une suppression » (10 h) : chaque test refait le texte d'avant à partir des
seuls faits du retour. Rien ne change à l'oreille : ces textes ne partaient plus au modèle (C4, C5), seuls les tests les lisaient.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.commande import moteur
from api.services.commande import panier as P
from api.services.commande.moteur import articles, lecture
from api.services.commande.resultat import Resultat
from api.services.mots_dits import chiffres_en_lettres, phrase_nette
from api.services.commande.moteur import mode_et_adresse
from api.services.commande.moteur.socle import Appelant
from api.services.mots_dits import liste_dite
from api.services.restauration.source_commande import SourceClasseur, resolution_du_jour_et_de_l_heure
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_base_client as _BASE

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile

ADRESSE_AVANT = "Quelle est l'adresse de livraison ?"  # le texte d'avant (``phrase_du_manque(Manque.ADRESSE_ET_COMMUNE)``), refait du seul manque


@pytest.fixture
def vierge(commerce):
    return _PANIER.Appel(commerce)


def _question_du_mode_d_avant(faits: dict) -> str:
    """Le texte d'avant (``_phrase_des_modes``), refait des seuls faits : les modes dits."""
    return f"{liste_dite(faits['modes_dits']).capitalize()} ?"


def _sans_texte_au_manque(r, manque: str) -> None:
    assert r.suggestion == "" and r.manque == manque, r


# ── les questions du mode et de la zone (prealables.py, mode_et_adresse.py, la source) ─────────────────────────────────────────


async def test_un_mode_inconnu_n_a_plus_de_question_composee_et_porte_les_modes_dits(vierge):
    r = await vierge.mode("trottinette")
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "mode")
    assert r.faits["modes"] == list(vierge.source.modes)  # voisin : les codes restent
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_l_etat_d_un_mode_inconnu_n_a_plus_de_question_composee(vierge):
    r = await moteur.etat_ouverture(vierge.source, vierge.p, vierge.regles, "trottinette")
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "mode")
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_l_heure_annoncee_sans_mode_lisible_n_a_plus_de_question_composee(vierge):
    r = await moteur.heure_annoncee(vierge.source, vierge.p, vierge.regles, "trottinette")
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "mode")
    assert _question_du_mode_d_avant(r.faits) == "À emporter, en livraison ou sur place ?"


async def test_la_livraison_sans_zone_demande_l_adresse_par_le_seul_manque(vierge):
    r = await vierge.mode("livraison")
    assert r.statut == "OK"
    _sans_texte_au_manque(r, "zone")


async def test_l_ordre_impose_demande_la_zone_par_le_seul_manque_a_la_fin(commerce):
    a = _PANIER.Appel(commerce, ordre_impose=True)
    await a.mode("livraison")
    r = await moteur.finaliser(a.source, a.p, a.regles, Appelant())
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "zone")


async def test_l_heure_annoncee_en_livraison_sans_zone_demande_la_zone_par_le_seul_manque(vierge):
    r = await moteur.heure_annoncee(vierge.source, vierge.p, vierge.regles, "livraison")
    assert r.statut == "INCOMPLETE"
    _sans_texte_au_manque(r, "zone")


async def test_une_adresse_vide_se_redemande_par_le_seul_manque(vierge):
    await vierge.mode("livraison")
    r = await mode_et_adresse.verifier_adresse(vierge.source, vierge.p, vierge.regles, None)
    assert r.statut == "ARGUMENT_INVALIDE"
    _sans_texte_au_manque(r, "adresse")


def test_la_source_n_a_plus_de_question_de_la_zone():
    """La question de la zone ne vit plus dans la source : le manque (``zone``, ``adresse``) la porte, le modèle la pose (Evan 25/11 8 h 45)."""
    assert not hasattr(SourceClasseur, "question_de_la_zone")


# ── le message, l'heure retenue (message.py, source_commande.py) ───────────────────────────────────────────────────────────────


async def test_un_message_sans_quoi_se_redemande_par_le_seul_manque(vierge):
    """Le texte d'avant, « Quel message voulez-vous recevoir ? », ne disait que le manque ``quoi``."""
    r = await moteur.envoyer_un_message(vierge.source, vierge.p, vierge.regles, Appelant(), None, None)
    assert r.statut == "ARGUMENT_INVALIDE" and r.faits == {}
    _sans_texte_au_manque(r, "quoi")


def test_le_jour_et_l_heure_retenus_n_ont_plus_de_texte_et_se_disent_par_leurs_faits():
    r = resolution_du_jour_et_de_l_heure("demain", "dix-neuf heures", datetime(2026, 11, 17, 10, 50, tzinfo=ZoneInfo("Europe/Paris")))
    assert r.statut == "RETENU" and r.suggestion == "", r
    assert f"{r.faits['jour_dit']} à {r.faits['heure_dite']}." == "mercredi dix-huit novembre à dix-neuf heures.", r.faits  # le texte d'avant, refait des faits


# ── les remises et la carte lues (articles.py, lecture.py) : la remise est un fait, son montant aussi en lettres ─────────────────


def _remise_d_avant(remise: dict) -> str:
    """Le texte d'avant (``phrase_d_une_remise_appliquee``), refait des seuls faits de la remise : le texte du restaurant, sinon son nom et son montant dit."""
    if remise.get("texte_de_l_offre"):
        return phrase_nette(chiffres_en_lettres(remise["texte_de_l_offre"]))
    return f"Bonne nouvelle : {phrase_nette(chiffres_en_lettres(remise['nom']))}, cela vous fait {remise['montant_dit']} de moins."


class _SourceDesRemises:
    modes = ("emporter",)

    def __init__(self, phrase: str | None = None, en_cours: list | None = None):
        self.remise = {"ref": "R1", "nom": "Bienvenue", "montant": 230, "phrase": phrase}
        self.en_cours = en_cours or []

    async def codes_de_remise(self):
        return [{"code": "BIENVENUE", "ref": "R1", "nom": "Bienvenue", "phrase": self.remise["phrase"]}]

    async def remises_en_cours(self):
        return self.en_cours


def _panier_pret() -> dict:
    p = P.nouveau()
    p.update({"mode": "emporter", "lignes": [{"n": 1, "nom": "Margherita", "code": "m", "quantite": 1, "choix": [], "retires": []}]})
    return p


def _chiffre(source, sous_total: int = 2300):
    async def chiffrer(_source, _p, _regles):
        return Resultat("OK", {"remises": [source.remise], "sous_total": sous_total, "lignes": []}, "")
    return chiffrer


@pytest.mark.parametrize("phrase", [None, "10 % de moins sur la commande"])
async def test_le_code_de_remise_applique_n_a_plus_de_texte_et_porte_sa_remise_en_lettres(monkeypatch, phrase):
    """Client « J'ai le code BIENVENUE. » / le retour ne compose plus « Bonne nouvelle : Bienvenue, cela vous fait deux euros trente de moins. » ; la réduction est aussi dite en lettres."""
    source = _SourceDesRemises(phrase)
    monkeypatch.setattr(articles, "chiffrer_le_panier", _chiffre(source))
    r = await articles.poser_le_code_de_remise(source, _panier_pret(), moteur.Reglages(), "BIENVENUE", False)
    assert r.statut == "OK" and r.suggestion == "", r
    assert r.faits["reduction"] == 230 and r.faits["reduction_dite"] == "deux euros trente", r.faits  # voisin : le montant brut reste
    remise = {"nom": r.faits["remise"], "montant_dit": r.faits["reduction_dite"], **({"texte_de_l_offre": r.faits["texte_de_l_offre"]} if "texte_de_l_offre" in r.faits else {})}
    assert _remise_d_avant(remise) == ("Bonne nouvelle : Bienvenue, cela vous fait deux euros trente de moins." if phrase is None else "dix pour cent de moins sur la commande")


@pytest.mark.parametrize("phrase", [None, "10 % de moins sur la commande"])
async def test_la_remise_appliquee_lue_n_a_plus_de_texte_et_porte_son_montant_en_lettres(monkeypatch, phrase):
    source = _SourceDesRemises(phrase)
    monkeypatch.setattr(lecture, "chiffrer_le_panier", _chiffre(source))
    r = await lecture.remises_disponibles(source, _panier_pret(), moteur.Reglages())
    assert r.faits["moment"] == "appliquee" and r.suggestion == "", r
    remise = r.faits["remise"]
    assert remise["montant"] == 230 and remise["montant_dit"] == "deux euros trente", remise
    assert _remise_d_avant(remise) == ("Bonne nouvelle : Bienvenue, cela vous fait deux euros trente de moins." if phrase is None else "dix pour cent de moins sur la commande")


async def test_le_seuil_presque_atteint_porte_ce_qui_manque_en_lettres(monkeypatch):
    """Le texte d'avant disait le montant qui manque ; le fait brut était en centimes (L) : il passe aussi en lettres (``manque_dit``)."""
    source = _SourceDesRemises(en_cours=[{"ref": "S1", "nom": "Frites offertes", "phrase": None, "minimum": 2000}])
    source.remise = {"ref": "AUTRE", "nom": "x", "montant": 0, "phrase": None}

    async def chiffrer(_source, _p, _regles):
        return Resultat("OK", {"remises": [], "sous_total": 1950, "lignes": []}, "")
    monkeypatch.setattr(lecture, "chiffrer_le_panier", chiffrer)
    r = await lecture.remises_disponibles(source, _panier_pret(), moteur.Reglages())
    assert r.faits["moment"] == "seuil_presque_atteint" and r.faits["remise"]["manque"] == 50 and r.faits["remise"]["manque_dit"] == "cinquante centimes", r.faits


async def test_la_carte_lue_n_a_plus_de_texte(vierge, monkeypatch):
    """Le texte du jour (tel que saisi) et « je ne peux pas vous le confirmer » (``renseigne`` faux) sont des faits de la carte : le retour n'a plus de texte."""
    async def carte(_mode):
        return {"rubriques": [], "du_moment": [{"article": "Plat du jour", "renseigne": False}]}
    monkeypatch.setattr(vierge.source, "carte_a_lire", carte)
    r = await lecture.voir_la_carte(vierge.source, vierge.p, vierge.regles)
    assert r.suggestion == "" and r.faits["du_moment"][0]["renseigne"] is False, r
