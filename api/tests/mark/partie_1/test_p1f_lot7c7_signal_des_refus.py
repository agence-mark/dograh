"""[.mark] Lot 7b-C7, A0 : le test de garde du signal, complété des textes encore pleins (la base de la commande, le règlement, la fin, le suivi, la réservation).

Evan, 25/11 : « ce n'est pas juste une suppression ». Un texte de secours n'est vidé que quand ce qu'il apprend à la personne (le statut, la raison ou le manque qui distingue le refus,
puis chaque valeur) est dans ce que le modèle reçoit (``aides_signal.signal``). Même mécanique que ``test_p1f_lot7c7_signal_du_secours`` (``aides_signal.Cas``) ; un fait qui manque
encore est un xfail strict (``raises=AssertionError``) qui passe au vert dans le commit du fait : F3 (le minimum), F4 (plusieurs commandes au suivi), F5 (le jour ambigu de la
réservation), F6 (le groupe trop grand, l'offre de message). ``test_la_table_*_est_fidele_au_texte`` prouve que la table dit ce que disait le texte (elle sort avec les textes).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients import restauration_reservation as RR
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.actions_communes.resultat import Resultat
from api.services.commande import porte, textes_de_secours as TS
from api.services.commande.moteur import enregistrement, lecture, reglement
from api.services.commande.moteur.socle import STATUTS_PERDUS, Appelant
from api.services.commande.phrases_du_manque import Manque, phrase_du_manque
from api.services.reservation import moteur as RESA_MOTEUR
from api.services.reservation import textes_de_secours as TSR
from api.services.restauration.carte_et_allergenes import textes_de_secours as TSA
from api.services.restauration.carte_et_allergenes import voir_un_article as V_
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.partie_1.aides_signal import Carte, Cas, article_de_carte, controler, fidele, jouer, pareilles, parametres
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

base_essai, base_prete, commerce, salle = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce, _RESA.salle  # les fixtures des classeurs, reprises par affectation
PARIS = _RESA.PARIS
TEL = _RESA.TEL


def _manque_du_catalogue(manque: Manque):
    """Le texte d'un manque de la base : la phrase du catalogue des manques (``phrases_du_manque``), qui ne lit aucun fait."""
    return lambda _faits: phrase_du_manque(manque)


# ── la base de la commande : la carte (calcul pur) ────────────────────────────────────────────────────────────────────────────────────────────────


def _option(ref: str, nom: str, **plus) -> dict:
    return {"id": ref, "groupe_id": "G", "nom": nom, "code_caisse": ref.upper(), "prix": 100, "par_defaut": False, "retirable": False, "vendable": True, **plus}


def _groupe(nom: str, options: list[dict], *, mini: int = 0, maxi: int = 3, par_option: int = 3) -> dict:
    return {"id": "G", "nom": nom, "min": mini, "max": maxi, "max_par_option": par_option, "role": "supplement", "defaut": [], "parent_option_id": None, "options": options}


def _produit(code: str, nom: str, groupes: list[str]) -> dict:
    return {"id": "P-" + code, "nom": nom, "categorie_id": "C", "ingredients": [], "alcool": False, "groupes": groupes, "tva_par_mode": {},
            "declinaisons": [{"id": "D-" + code, "nom": "Unique", "code_caisse": code, "prix": 1000, "vendable": True, "prix_par_mode": None}]}


def _carte(groupes: list[dict] | None = None, formules: list[dict] | None = None, extra: list[dict] | None = None) -> dict:
    return {"produits": [_produit("PIZZA", "Pizza", [g["id"] for g in groupes or []]), *(extra or [])], "groupes": groupes or [], "formules": formules or [], "categories": []}


def _refus_de_la_carte(carte: dict, ligne: dict, ruptures: set[str] | None = None):
    def jouer_():
        _, _, erreur = RC._lignes(RC._Panier(carte, "emporter", ruptures or set()), [ligne])
        assert erreur is not None
        return erreur
    return jouer_


def _pizza(choix: list[dict], **plus) -> dict:
    return {"code_caisse": "PIZZA", "quantite": 1, "choix": choix, **plus}


def _c(code: str, quantite: int = 1, **plus) -> dict:
    return {"option_code": code, "quantite": quantite, "choix": [], **plus}


SUPPLEMENTS = _groupe("Suppléments", [_option("oeuf", "Œuf"), _option("fromage", "Fromage")])
LIGNES_DU_MENU = [{"nom": "Plat", "codes": ["PLAT"]}, {"nom": "Dessert", "codes": ["DESSERT"]}]


def _menu(lignes: list[dict]) -> dict:
    formule = {"id": "F", "nom": "Menu", "code_caisse": "MENU", "prix": 1400, "vendable": True, "categorie_id": None, "lignes": lignes}
    return _carte(formules=[formule], extra=[_produit("PLAT", "Plat", []), _produit("DESSERT", "Dessert", [])])


def _du_menu(choix: list[dict]) -> dict:
    return {"code_caisse": "MENU", "quantite": 1, "choix": choix}


ALTERNATIVES = [{"nom": "Plat", "codes": ["PLAT", "DESSERT"], "alternatives": [{"codes": ["PLAT"], "quantite": 2}, {"codes": ["DESSERT"], "quantite": 2}]}]

CAS_DE_LA_CARTE: list[Cas] = [
    Cas("choix_hors_produit", TSC.choix_hors_produit, _refus_de_la_carte(_carte([SUPPLEMENTS]), _pizza([_c("INCONNU")])), "F", [], "HORS_CARTE"),
    Cas("quantite_de_choix_invalide", TSC.quantite_de_choix_invalide, _refus_de_la_carte(_carte([SUPPLEMENTS]), _pizza([_c("OEUF", 0)])), "F", [], "quantite"),
    Cas("choix_en_rupture", TS.n_est_plus_disponible, _refus_de_la_carte(_carte([SUPPLEMENTS]), _pizza([_c("OEUF")]), {"OEUF"}), "F", pareilles("Œuf"), "RUPTURE"),
    Cas("option_trop_de_fois", TSC.option_trop_de_fois, _refus_de_la_carte(_carte([_groupe("Suppléments", [_option("oeuf", "Œuf")], par_option=1)]), _pizza([_c("OEUF", 2)])),
        "F", [("Œuf", "Œuf"), ("1", "1")], "MAXIMUM_ATTEINT"),
    Cas("choix_obligatoire", TSC.choix_obligatoire, _refus_de_la_carte(_carte([_groupe("Cuisson", [_option("saignant", "Saignant")], mini=1)]), _pizza([])), "F",
        pareilles("Cuisson"), "CHOIX_OBLIGATOIRE"),
    Cas("pas_plus_pour", TSC.pas_plus_pour, _refus_de_la_carte(_carte([{**SUPPLEMENTS, "max": 1}]), _pizza([_c("OEUF"), _c("FROMAGE")])), "F",
        [("Suppléments", "Suppléments"), ("1", "1")], "MAXIMUM_ATTEINT"),
    Cas("formule_quantite_de_choix_invalide", TSC.quantite_de_choix_invalide, _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PLAT", 0)])), "F", [], "quantite"),
    Cas("choix_hors_formule", TSC.choix_hors_formule, _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PIZZA")])), "F", [], "choix_hors_liste"),
    Cas("element_de_formule_indisponible", TSC.element_de_formule_indisponible, _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PLAT")]), {"PLAT"}), "F", [], "RUPTURE"),
    Cas("pas_plus_pour_la_formule", TSC.pas_plus_pour, _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PLAT", 2)])), "F", [("Plat", "Plat"), ("1", "1")],
        "MAXIMUM_ATTEINT"),
    Cas("ligne_de_formule_obligatoire", TSC.choix_obligatoire, _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PLAT")])), "F", pareilles("Dessert"),
        "CHOIX_OBLIGATOIRE"),
    Cas("ne_peut_pas_retirer_dans_la_formule", TSC.ne_peut_pas_retirer,
        _refus_de_la_carte(_menu(LIGNES_DU_MENU), _du_menu([_c("PLAT", retires=["sauce"]), _c("DESSERT")])), "F", pareilles("sauce"), "HORS_CARTE"),
    Cas("une_seule_alternative", TSC.une_seule_alternative, _refus_de_la_carte(_menu(ALTERNATIVES), _du_menu([_c("PLAT"), _c("DESSERT")])), "F", [], "alternatives_melangees"),
    Cas("quantite_invalide", TSC.quantite_invalide, _refus_de_la_carte(_carte(), {"code_caisse": "PIZZA", "quantite": 0}), "F", [], "quantite"),
    Cas("produit_hors_carte", TSC.produit_hors_carte, _refus_de_la_carte(_carte(), {"code_caisse": "FANTOME", "quantite": 1}), "F", [], "HORS_CARTE"),
    Cas("produit_en_rupture", TS.n_est_plus_disponible, _refus_de_la_carte(_carte(), {"code_caisse": "PIZZA", "quantite": 1}, {"PIZZA"}), "F", pareilles("Pizza"), "RUPTURE"),
    Cas("prix_different", TSC.prix_different, _refus_de_la_carte(_carte(), {"code_caisse": "PIZZA", "quantite": 1, "prix_unitaire": 1}), "F", [], "prix_different"),
    Cas("ne_peut_pas_retirer", TSC.ne_peut_pas_retirer, _refus_de_la_carte(_carte(), {"code_caisse": "PIZZA", "quantite": 1, "retires": ["olives"]}), "F", pareilles("olives"),
        "HORS_CARTE"),
]


# ── la base de la commande : ce qui manque à la demande, le règlement (calcul pur) ─────────────────────────────────────────────────────────────────────


def _demande(**plus) -> dict:
    return {"mode": "emporter", "lignes": [{"code_caisse": "X"}], "client": {"telephone": TEL}, **plus}


def _manque_de(brouillon: dict, jeton: str | None = "relu-1"):
    return lambda: RC._manques_de_la_demande(brouillon, jeton, JEUDI_MIDI)


def _reglages(**module) -> dict:
    return {"moyens_paiement": ["carte", "especes", "titre_restaurant"], "plafond_titre": 2500, "module": {"titre_alcool_exclu": False, "titre_sans_rendu": False, **module}}


def _regle(moyens: list[dict], total: int = 2000, calculees: list[dict] | None = None, reglages: dict | None = None, **paiement):
    return lambda: RC._controler_le_reglement({"paiement": {"moyens": moyens, **paiement}}, reglages or _reglages(), total, calculees or [])


ALCOOL = [{"alcool": True, "prix_unitaire": 1000, "quantite": 1}, {"alcool": False, "prix_unitaire": 1000, "quantite": 1}]

CAS_DE_LA_DEMANDE: list[Cas] = [
    Cas("mode_non_compris", TSC.mode_non_compris, _manque_de({"mode": "pigeon", "lignes": [{}]}), "F", [], "mode"),
    Cas("manque_les_articles", _manque_du_catalogue(Manque.ARTICLES), _manque_de(_demande(lignes=[])), "F", [], "lignes"),
    Cas("manque_le_telephone", _manque_du_catalogue(Manque.TELEPHONE), _manque_de(_demande(client={})), "F", [], "telephone"),
    Cas("manque_l_adresse", _manque_du_catalogue(Manque.ADRESSE_ET_COMMUNE), _manque_de(_demande(mode="livraison")), "F", [], "adresse"),
    Cas("situer_l_adresse", TSC.situer_l_adresse, _manque_de(_demande(mode="livraison", adresse={"commune": "Senlis"})), "F", [], "zone"),
    Cas("relire_la_commande", TSC.relire_la_commande, _manque_de(_demande(), None), "F", [], "relecture"),
    Cas("origine_invalide", TSC.origine_invalide, _manque_de(_demande(cree_par="pigeon")), "F", [], "cree_par"),
    Cas("heure_non_valable", TSC.heure_non_valable, _manque_de(_demande(heure_voulue=JEUDI_MIDI.replace(hour=9))), "F", [], "heure_voulue"),
    Cas("prenom_trop_long", TSC.prenom_trop_long, _manque_de(_demande(client={"telephone": TEL, "prenom": "x" * 61})), "F", [], "prenom"),
    Cas("manque_le_paiement", _manque_du_catalogue(Manque.PAIEMENT), _regle([]), "F", [], "paiement"),
    Cas("reglement_invalide", TSC.reglement_invalide, _regle([{"moyen": "carte"}]), "F", [], "paiement"),
    Cas("moyen_refuse", TS.moyen_refuse, _regle([{"moyen": "cheque", "montant": 2000}]), "F", [], "MOYEN_NON_ACCEPTE"),
    Cas("plafond_titre_depasse", TSC.plafond_titre_depasse, _regle([{"moyen": "titre_restaurant", "montant": 2600}], total=2600), "F", [], "PLAFOND_TITRE_RESTAURANT"),
    Cas("titre_et_alcool", TSC.titre_et_alcool, _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, ALCOOL, _reglages(titre_alcool_exclu=True)), "F", [], "alcool"),
    Cas("titre_sans_rendu", TSC.titre_sans_rendu,
        _regle([{"moyen": "titre_restaurant", "montant": 2000}], 2000, None, _reglages(titre_sans_rendu=True), rendu_sur="titre_restaurant"), "F", [], "sans_rendu"),
    Cas("montant_de_paiement_invalide", TSC.montant_de_paiement_invalide, _regle([{"moyen": "carte", "montant": -5}]), "F", [], "ARGUMENT_INVALIDE"),
    Cas("reglement_incomplet", TSC.reglement_incomplet, _regle([{"moyen": "carte", "montant": 1000}]), "F", [], "INCOMPLETE"),
]


# ── la base de la commande : la zone, le mode, l'heure voulue, la remise, la commande introuvable (le classeur) ─────────────────────────────────────────────


async def _regler(commerce, **colonnes):
    for colonne, valeur in colonnes.items():
        await commerce.c.execute(f"UPDATE mark.resto_reglage_type SET {colonne} = $2 WHERE site_id = $1 AND type = 'emporter'", commerce.a, valeur)


def _creneau(voulue, moment=JEUDI_MIDI, **reglage):
    async def jouer_(commerce, _mp):
        await _regler(commerce, **reglage)
        return await RC.creneau_refuse(commerce.c, commerce.a, "emporter", voulue, moment, PARIS)
    return jouer_


async def _hors_zone(commerce, _mp):
    return (await RC._zone_de_livraison(commerce.c, commerce.a, 999999, 3000))[2]


async def _minimum_non_atteint(commerce, _mp):
    return (await RC._zone_de_livraison(commerce.c, commerce.a, commerce.zones["Proches"], 200))[2]


async def _mode_au_chiffrage(commerce, _mp):
    return await RC.chiffrer_panier(commerce.c, commerce.a, "pigeon", [])


async def _ferme_maintenant(commerce, _mp):
    from api.db.bases_clients import horloge
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        return await RC.creneau_refuse(commerce.c, commerce.a, "emporter", None, JEUDI_MIDI.replace(hour=16), PARIS)


async def _creneau_complet(commerce, mp):
    async def libre(*_):
        return JEUDI_MIDI + timedelta(minutes=30)
    mp.setattr(RC, "creneau_complet", libre)
    return await _creneau(JEUDI_MIDI + timedelta(minutes=15), planifiee_permise=True)(commerce, mp)


async def _remise_inconnue(commerce, _mp):
    return await _CLASSEUR.enregistrer(commerce, _CLASSEUR.brouillon(remises=[{"ref": "INCONNUE"}]))


async def _commande_introuvable(commerce, _mp):
    return await RC.statut_commande(commerce.c, commerce.a, telephone="+33600000000")


CAS_DU_CLASSEUR: list[Cas] = [
    Cas("hors_zone_sans_commune", TSC.hors_zone, _hors_zone, "F", [], "HORS_ZONE"),
    Cas("minimum_non_atteint", TSC.minimum_non_atteint, _minimum_non_atteint, "F", [("quinze euros", "quinze euros")], "MINIMUM_NON_ATTEINT"),  # F3 porté (C7 B6)
    Cas("mode_non_compris_au_chiffrage", TSC.mode_non_compris, _mode_au_chiffrage, "F", [], "mode"),
    Cas("pas_de_commande_pour_plus_tard", TSC.pas_de_commande_pour_plus_tard, _creneau(JEUDI_MIDI + timedelta(hours=1)), "F", [], "plus_tard_refuse"),
    Cas("commandes_jusqu_a", TSC.commandes_jusqu_a, _creneau(JEUDI_MIDI + timedelta(days=3), planifiee_permise=True, jours_a_l_avance=1), "F",
        pareilles("vendredi treize novembre"), "heure_voulue"),
    Cas("trop_tot", TSC.trop_tot, _creneau(JEUDI_MIDI + timedelta(minutes=30), planifiee_permise=True, delai_minimal=60), "F", [], "trop_tot"),
    Cas("ferme_a_cette_heure", TSC.ferme_a_cette_heure, _creneau(JEUDI_MIDI + timedelta(hours=4), planifiee_permise=True), "F", pareilles("dix-huit heures"), "FERME"),
    Cas("ferme_maintenant", TSC.ferme_a_cette_heure, _ferme_maintenant, "F", [], "FERME"),
    Cas("creneau_complet", TSC.creneau_complet, _creneau_complet, "F", pareilles("douze heures trente"), "creneau_plein"),
    Cas("remise_non_applicable", TSC.remise_non_applicable, _remise_inconnue, "F", [], "remise_inconnue"),
    Cas("commande_introuvable_de_la_base", TSC.commande_introuvable, _commande_introuvable, "F", [], "INTROUVABLE"),
]


# ── le moteur de la commande : le règlement, la fin, le suivi, l'heure proposée refusée ───────────────────────────────────────────────────────────────


def _regler_au_moteur(**dit):
    async def jouer_(appel, _mp):
        await appel.ajouter("coca")
        return (await reglement.regler(appel.source, appel.p, 2000, **dit))[1]
    return jouer_


async def _numero_illisible(appel, _mp):
    return enregistrement.noter_le_client(appel.p, telephone="pas un numéro", prenom=None)


def _etat_ferme(**en_plus):
    async def etat(_mode):
        return {"ouvert": False, "statut": "FERME", "raison": "ferme", "reprise": None, "reprise_dite": None, "prochaine_ouverture": None,
                "planifiee_permise": False, **en_plus}
    return etat


async def _proposition_a_la_fin(appel, mp):
    async def quand_dit(_h):
        return "dix-huit heures"
    await appel.ajouter("coca")
    await appel.mode()
    mp.setattr(appel.source, "etat", _etat_ferme(planifiee_permise=True, prochaine_ouverture=datetime(2026, 11, 25, 17, tzinfo=timezone.utc)))
    mp.setattr(appel.source, "quand_dit", quand_dit, raising=False)
    return await enregistrement.finaliser(appel.source, appel.p, appel.regles, Appelant(telephone_affiche=TEL))


def _retrouver(*commandes: dict, statut: str = "OK", numero: str | None = "12"):
    async def jouer_(appel, mp):
        async def retrouver(numero=None, telephone=None):
            return Resultat(statut, {"commandes": list(commandes)} if statut == "OK" else {}, "")
        mp.setattr(appel.source, "retrouver", retrouver)
        return await lecture.retrouver_commande(appel.source, appel.p, appel.regles, Appelant(), numero)
    return jouer_


def _commande(statut: str = "envoyee", numero_court: str = "12", quand_dit: str | None = "dix-neuf heures") -> dict:
    return {"numero_court": numero_court, "statut": statut, "mode": "emporter", "quand_dit": quand_dit}


async def _heure_proposee_refusee(appel, _mp):
    return await porte._repondre_a_l_heure_proposee(appel.source, appel.p, appel.regles, Appelant(), {}, "refuse", None, None)


PERDU = sorted(STATUTS_PERDUS)[0]

CAS_DU_MOTEUR: list[Cas] = [
    Cas("moyen_non_accepte", TS.moyen_non_accepte, _regler_au_moteur(moyen="cheque"), "F", lambda r: pareilles(*r.faits["acceptes_dits"]), "MOYEN_NON_ACCEPTE"),
    Cas("quel_montant", TS.quel_montant, _regler_au_moteur(moyen="carte", part="pas un montant"), "F", [], "montant_illisible"),
    Cas("et_le_reste", TS.et_le_reste, _regler_au_moteur(moyen="carte", part=10), "F", [], "paiement_reste"),
    Cas("sur_quel_reglement", TS.sur_quel_reglement, _regler_au_moteur(moyen="carte", rendu_sur=50), "F", [], "especes"),
    Cas("billet_insuffisant", TS.billet_insuffisant, _regler_au_moteur(moyen="especes", rendu_sur=5), "F", [], "cinq euros"),
    Cas("numero_pas_compris", TS.numero_pas_compris, _numero_illisible, "F", [], "numero_illisible"),
    Cas("je_vous_la_prepare_pour", TS.je_vous_la_prepare_pour, _proposition_a_la_fin, "F", pareilles("dix-huit heures"), "heure_proposee"),
    Cas("quel_numero_de_commande", TS.quel_numero_de_commande, _retrouver(numero=None), "S", [], "reference"),
    Cas("commande_introuvable", TS.commande_introuvable, _retrouver(statut="INTROUVABLE"), "S", [], "numero"),
    Cas("commandes_plusieurs", TS.commandes_plusieurs, _retrouver(_commande(), _commande(numero_court="14", quand_dit="vingt heures")), "S",
        [("12", "12"), ("dix-neuf heures", "dix-neuf heures"), ("14", "14"), ("vingt heures", "vingt heures")], "AMBIGU"),  # F4 porté (C7 B4)
    Cas("commande_pas_passee", TS.commande_pas_passee, _retrouver(_commande(PERDU)), "S", [], PERDU),
    Cas("commande_annulee", TS.commande_annulee, _retrouver(_commande("annulee")), "S", [], "annulee"),
    Cas("pour_quel_jour_alors", TS.pour_quel_jour_alors, _heure_proposee_refusee, "F", [], "heure_manquante"),
]


# ── la composition d'un article (``voir_un_article``) ───────────────────────────────────────────────────────────────────────────────────────────────

REINE = {"nom": "Reine", "ingredients": ["jambon", "champignons"], "signalements": [], "declinaisons": [], "groupes": [], "regimes": []}

CAS_DE_L_ARTICLE: list[Cas] = [
    Cas("composition_d_un_article", TSA.composition_d_un_article,
        lambda: V_.voir_produit(Carte([article_de_carte("Reine", [], ["jambon", "champignons"])], fiche=REINE), {"mode": "sur_place", "lignes": []}, None, "Reine"), "F",
        pareilles("Reine", "jambon", "champignons"), "OK"),
]


# ── la réservation : la base ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _creer(retire: str | None = None, **plus):
    async def jouer_(salle_, _mp):
        brouillon = _RESA.demande(**plus)
        if retire:
            brouillon.pop(retire)
        return await RR.creer_reservation(salle_.c, salle_.a, brouillon)
    return jouer_


async def _complet(salle_, _mp):
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        await _RESA.creer(salle_, couverts=couverts, telephone=tel, appel_id=f"p{i}")
    return await _RESA.creer(salle_, telephone="+33600000009", appel_id="p9")


async def _type_ferme(salle_, _mp):
    await salle_.c.execute("INSERT INTO mark.resto_reglage_type (site_id, type, ouvert) VALUES ($1, 'reservation', false)", salle_.a)
    return await _RESA.creer(salle_)


async def _passee(salle_, _mp):
    from api.db.bases_clients import horloge
    n = (await _RESA.creer(salle_)).faits["numero"]
    with horloge.remplacer(salle_.base, _RESA.SAMEDI_20H + timedelta(minutes=5)):
        return await RR.modifier_reservation(salle_.c, salle_.a, n, {"couverts": 3})


async def _plus_modifiable(salle_, _mp):
    n = (await _RESA.creer(salle_)).faits["numero"]
    await RR.annuler_reservation(salle_.c, salle_.a, n)
    return await RR.modifier_reservation(salle_.c, salle_.a, n, {"couverts": 3})


async def _deja_reservee(salle_, _mp):
    await _RESA.creer(salle_)
    return await _RESA.creer(salle_)


async def _deja_comme_cela(salle_, _mp):
    n = (await _RESA.creer(salle_)).faits["numero"]
    return await RR.modifier_reservation(salle_.c, salle_.a, n, {"prenom": "Alice"})


async def _deja_annulee_de_la_base(salle_, _mp):
    n = (await _RESA.creer(salle_)).faits["numero"]
    await RR.annuler_reservation(salle_.c, salle_.a, n)
    return await RR.annuler_reservation(salle_.c, salle_.a, n)


def _propositions(r) -> list[tuple[str, str]]:
    return pareilles(*[p["quand_dit"] for p in r.faits.get("propositions") or []])


A_FAIRE_DU_GROUPE = "dis-lui qu'un groupe de cette taille se règle avec l'équipe et propose de laisser un message à l'équipe"  # la consigne d'aujourd'hui (``groupe_trop_grand`` de la base)
GROUPE = [(A_FAIRE_DU_GROUPE, "c'est l'équipe qui s'en occupe")]

CAS_DE_LA_SALLE: list[Cas] = [
    Cas("passe", TSR.refus_de_la_base, _creer(debut=datetime(2026, 11, 12, 11, 0, tzinfo=PARIS)), "Rv", [], "passe"),
    Cas("trop_tot_reservation", TSR.refus_de_la_base, _creer(debut=datetime(2026, 11, 12, 12, 30, tzinfo=PARIS)), "Rv", [], "trop_tot"),
    Cas("trop_loin", TSR.refus_de_la_base, _creer(debut=datetime(2026, 12, 25, 20, 0, tzinfo=PARIS)), "Rv", [], "trop_loin"),
    Cas("hors_service", TSR.refus_de_la_base, _creer(debut=datetime(2026, 11, 14, 15, 0, tzinfo=PARIS)), "Rv", _propositions, "hors_service"),
    Cas("type_ferme", TSR.refus_de_la_base, _type_ferme, "Rv", [], "type_ferme"),
    Cas("ferme", TSR.refus_de_la_base, lambda _s, _m: RR._refus("ferme"), "Rv", [], "ferme"),
    Cas("complet", TSR.refus_de_la_base, _complet, "Rv", _propositions, "complet"),
    Cas("groupe_trop_grand_avant_le_jour", TSR.refus_de_la_base, lambda s, _m: RR.groupe_trop_grand(s.c, s.a, 25), "Rv", GROUPE, "groupe_trop_grand"),
    Cas("groupe_trop_grand_de_la_capacite", TSR.refus_de_la_base, lambda s, _m: RR.capacite_du_jour(s.c, s.a, _RESA.SAMEDI_20H.date(), 7), "Rv", GROUPE, "groupe_trop_grand",
        manque="F6 : la consigne d'offre de message n'est posée qu'avant le jour (groupe_trop_grand), pas à la capacité du jour"),
    Cas("groupe_trop_grand_a_l_enregistrement", TSR.refus_de_la_base, _creer(couverts=7), "Rv", GROUPE, "groupe_trop_grand",
        manque="F6 : la consigne d'offre de message n'est posée qu'avant le jour (groupe_trop_grand), pas à l'enregistrement"),
    Cas("passee", TSR.refus_de_la_base, _passee, "Rv", [], "passee"),
    Cas("plus_modifiable", TSR.refus_de_la_base, _plus_modifiable, "Rv", [], "plus_modifiable"),
    Cas("combien_de_personnes_a_la_base", TSR.combien_de_personnes, _creer("couverts"), "Rv", [], "couverts"),
    Cas("quel_jour_et_quelle_heure_a_la_base", TSR.quel_jour_et_quelle_heure, _creer("debut"), "Rv", [], "debut"),
    Cas("a_quel_nom_a_la_base", TSR.a_quel_nom_je_mets_la_reservation, _creer("prenom"), "Rv", [], "prenom"),
    Cas("nom_trop_long", TSR.nom_trop_long, _creer(prenom="A" * 61), "Rv", [], "ARGUMENT_INVALIDE"),
    Cas("numero_illisible_a_la_base", TSR.numero_illisible, _creer(telephone="pas un numéro"), "Rv", [], "numero_illisible"),
    Cas("quel_numero_a_la_base", TSR.quel_numero, _creer("telephone"), "Rv", [], "telephone"),
    Cas("note_trop_longue", TSR.note_trop_longue, _creer(note="n" * 201), "Rv", [], "note"),
    Cas("deja_reservee", TSR.deja_reservee, _deja_reservee, "Rv", pareilles("samedi quatorze novembre à vingt heures"), "DEJA_FAIT"),
    Cas("deja_comme_cela", TSR.deja_comme_cela, _deja_comme_cela, "Rv", [], "DEJA_FAIT"),
    Cas("deja_annulee_de_la_base", TSR.deja_annulee, _deja_annulee_de_la_base, "Rv", [], "annulee"),
    Cas("sous_quel_nom_et_quel_jour_a_la_base", TSR.sous_quel_nom_et_quel_jour, lambda s, _m: RR.retrouver_reservation(s.c, s.a), "Rv", [], "reference"),
    Cas("pas_de_reservation", TSR.pas_de_reservation, lambda s, _m: RR.retrouver_reservation(s.c, s.a, telephone=TEL), "Rv", [], "INTROUVABLE"),
]


# ── la réservation : le moteur ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _au_moteur(geste: str, *, appelant: str | None = TEL, cible: bool = False, annulee: bool = False, derniere: bool = False, deux: bool = False, **dit):
    async def jouer_(salle_, mp):
        essai = EssaiReservation(salle_, mp, appelant=appelant)
        if cible or annulee or derniere or deux:
            numero = (await _RESA.creer(salle_)).faits["numero"]
            essai.etat["cible" if not derniere else "derniere"] = numero
            if annulee:
                essai.etat["annulees"] = [numero]
            if deux:
                essai.etat.pop("cible", None)
                await _RESA.creer(salle_, appel_id="deux", debut=_RESA.SAMEDI_20H.replace(day=15, hour=19), couverts=3)
        if geste == "disponibilites":
            return await RESA_MOTEUR.disponibilites(essai.source, essai.etat, dit.get("jour"), dit.get("personnes"))
        return await getattr(RESA_MOTEUR, geste)(essai.source, essai.etat, essai.moteur_appelant, **dit)
    return jouer_


DEUX_JEUDIS = [{"jour": "2026-11-19", "jour_dit": "jeudi dix-neuf novembre"}, {"jour": "2026-11-26", "jour_dit": "jeudi vingt-six novembre"}]


def _texte_des_jeudis(_faits) -> str:
    """Le texte que la source rend pour un jour ambigu : il se refait des candidats de la source, que la réservation ne montre pas au modèle (F5)."""
    return TSC.jour_ambigu({"candidats": DEUX_JEUDIS})


class _SourceDuSamedi:
    """Une source dont le seul jour est samedi 14 novembre 2026 et dont les créneaux libres sont ceux qu'on lui donne ; ``ambigu`` : le jour dit est deux jeudis."""

    def __init__(self, creneaux: list[datetime], heure_dite: bool = True, ambigu: bool = False):
        self.creneaux, self.heure_dite, self.ambigu = creneaux, heure_dite, ambigu

    async def resoudre_une_date(self, texte, heure):
        if self.ambigu:
            return Resultat("AMBIGU", {"candidats": DEUX_JEUDIS}, _texte_des_jeudis({}), "jour")
        vingt = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)
        faits = {"jour": "2026-11-14", "jour_dit": "samedi quatorze novembre", "heure_dite": "vingt heures"}
        return Resultat("RETENU", {**faits, "heure_voulue": vingt.isoformat()} if self.heure_dite else faits)

    async def disponibilites(self, jour, personnes):
        return Resultat("OK", {"creneaux": [{"debut": d, "fin": d + timedelta(hours=1)} for d in self.creneaux]})


def _a(heure: int) -> datetime:
    return datetime(2026, 11, 14, heure, 0, tzinfo=PARIS)


def _sans_salle(source: _SourceDuSamedi, geste: str, *, appelant: str | None = TEL, **dit):
    async def jouer_():
        if geste == "disponibilites":
            return await RESA_MOTEUR.disponibilites(source, {}, dit.get("jour"), dit.get("personnes"), dit.get("heure"))
        return await getattr(RESA_MOTEUR, geste)(source, {"brouillon": {}}, RESA_MOTEUR.Appelant(appelant, None), **dit)
    return jouer_


def _heures(r) -> list[tuple[str, str]]:
    return pareilles(*[c.get("heure_dite") for c in r.faits.get("creneaux") or r.faits.get("propositions") or []])


JEUDIS = pareilles("jeudi dix-neuf novembre", "jeudi vingt-six novembre")
QUAND = "samedi quatorze novembre à vingt heures"

CAS_DU_MOTEUR_DE_LA_RESERVATION: list[Cas] = [
    Cas("combien_de_personnes_au_moteur", TSR.combien_de_personnes, _au_moteur("reserver", jour="samedi"), "Rv", [], "personnes"),
    Cas("quel_jour_au_moteur", TSR.quel_jour, _au_moteur("reserver", personnes=2), "Rv", [], "jour"),
    Cas("a_quel_nom_au_moteur", TSR.a_quel_nom_je_mets_la_reservation, _au_moteur("reserver", personnes=2, jour="samedi", heure="vingt heures"), "Rv", [], "prenom"),
    Cas("quel_numero_au_moteur", TSR.quel_numero, _au_moteur("reserver", appelant=None, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice"), "Rv", [], "telephone"),
    Cas("numero_illisible_au_moteur", TSR.numero_illisible,
        _au_moteur("reserver", appelant=None, personnes=2, jour="samedi", heure="vingt heures", prenom="Alice", telephone="pas un numéro"), "Rv", [], "numero_illisible"),
    Cas("sous_quel_nom_et_quel_jour_au_moteur", TSR.sous_quel_nom_et_quel_jour, _au_moteur("retrouver_une_reservation", appelant=None), "Rv", [], "numero_masque"),
    Cas("quelle_heure", TSR.quelle_heure, _au_moteur("modifier", cible=True, jour="dimanche"), "Rv", [], "heure"),
    Cas("que_change_je", TSR.que_change_je, _au_moteur("modifier", cible=True), "Rv", [], "changement"),
    Cas("deja_une_reservation_dans_cet_appel", TSR.deja_une_reservation_dans_cet_appel, _au_moteur("reserver", derniere=True, personnes=3), "Rv", [],
        "deja_une_reservation_dans_cet_appel"),
    Cas("aucune_reservation_a_venir", TSR.aucune_reservation_a_venir, _au_moteur("retrouver_une_reservation", nom="Zoé"), "Rv", [], "INTROUVABLE"),
    Cas("une_reservation_trouvee", TSR.une_reservation_trouvee, _au_moteur("retrouver_une_reservation", cible=True, nom="Alice"), "Rv", [(QUAND, QUAND), ("2", "deux")], "OK"),
    Cas("plusieurs_a_choisir", TSR.plusieurs_a_choisir, _au_moteur("retrouver_une_reservation", deux=True, nom="Alice"), "RvQ",
        lambda r: pareilles(*[c["dit"] for c in r.faits["candidats"]]), "AMBIGU"),
    Cas("laquelle_de_la_reservation", TSR.laquelle, _au_moteur("retrouver_une_reservation", deux=True, nom="Alice"), "RvQ", [], "AMBIGU"),
    Cas("deja_annulee_au_moteur", TSR.deja_annulee, _au_moteur("annuler", annulee=True), "Rv", [], "deja_annulee"),
    Cas("rien_ne_change", TSR.rien_ne_change, _au_moteur("modifier", cible=True, personnes=2), "Rv", [(QUAND, QUAND), ("2", "deux")], "inchangee"),
]

CAS_DU_MOTEUR_SANS_SALLE: list[Cas] = [
    Cas("jour_ambigu_a_la_recherche", _texte_des_jeudis, _sans_salle(_SourceDuSamedi([], ambigu=True), "retrouver_une_reservation", appelant=None, jour="jeudi"), "Rv",
        JEUDIS, "jour", manque="F5 : la recherche redemande le jour sans les jours possibles (candidats retirés)"),
    Cas("jour_ambigu_a_la_reservation", _texte_des_jeudis, _sans_salle(_SourceDuSamedi([], ambigu=True), "reserver", personnes=2, jour="jeudi"), "Rv",
        JEUDIS, "jour", manque="F5 : les jours possibles sont dans candidats, que la réservation cache"),
    Cas("quel_jour_introuvable", TSR.quel_jour, lambda: RESA_MOTEUR.disponibilites(_SourceSansJour(), {}, "samedi", 2), "Rv", [], "jour"),
    Cas("complets_ce_jour", TSR.complets_ce_jour, _sans_salle(_SourceDuSamedi([]), "disponibilites", jour="samedi", personnes=2), "Rv", [], "complet"),
    Cas("complets_ce_jour_pour_le_soir", TSR.complets_ce_jour, _sans_salle(_SourceDuSamedi([_a(12)], heure_dite=False), "disponibilites", jour="samedi soir", personnes=2),
        "Rv", pareilles("soir"), "complet"),
    Cas("il_y_a_de_la_place", TSR.il_y_a_de_la_place, _sans_salle(_SourceDuSamedi([_a(19), _a(20), _a(21)]), "disponibilites", jour="samedi", personnes=2,
                                                                  heure="vingt heures"), "Rv", _heures, "OK"),
    Cas("refus_complet_sans_creneau", TSR.refus_complet_du_moteur, _sans_salle(_SourceDuSamedi([]), "reserver", personnes=2, jour="samedi", heure="vingt heures",
                                                                              prenom="Alice"), "Rv", [], "complet"),
    Cas("refus_complet_avec_les_plus_proches", TSR.refus_complet_du_moteur,
        _sans_salle(_SourceDuSamedi([_a(19), _a(21)]), "reserver", personnes=2, jour="samedi", heure="vingt heures", prenom="Alice"), "Rv", _heures, "complet"),
]


class _SourceSansJour:
    """Une date retenue sans jour lisible : le seul moyen d'atteindre le « pour quel jour ? » d'un jour introuvable."""

    async def resoudre_une_date(self, texte, heure):
        return Resultat("RETENU", {})


# ── les tests : un par famille de fixtures ───────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def appel(commerce):
    a = _PANIER.Appel(commerce)
    await a.mode()
    return a


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_CARTE + CAS_DE_LA_DEMANDE + CAS_DE_L_ARTICLE + CAS_DU_MOTEUR_SANS_SALLE))
async def test_le_signal_porte_ce_que_le_secours_d_un_calcul_pur_disait(cas):
    controler(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", parametres(CAS_DU_CLASSEUR))
async def test_le_signal_porte_ce_que_le_secours_de_la_base_de_la_commande_disait(cas, commerce, monkeypatch):
    controler(cas, await jouer(cas.scenario, commerce, monkeypatch))


@pytest.mark.parametrize("cas", parametres(CAS_DU_MOTEUR))
async def test_le_signal_porte_ce_que_le_secours_du_moteur_de_la_commande_disait(cas, appel, monkeypatch):
    controler(cas, await jouer(cas.scenario, appel, monkeypatch))


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_SALLE + CAS_DU_MOTEUR_DE_LA_RESERVATION))
async def test_le_signal_porte_ce_que_le_secours_de_la_reservation_disait(cas, salle, monkeypatch):
    controler(cas, await jouer(cas.scenario, salle, monkeypatch))


# Retirés avec les textes (lot B) : la table dit bien ce que disaient les textes.
@pytest.mark.parametrize("cas", CAS_DE_LA_CARTE + CAS_DE_LA_DEMANDE + CAS_DE_L_ARTICLE + CAS_DU_MOTEUR_SANS_SALLE, ids=lambda c: c.nom)
async def test_la_table_d_un_calcul_pur_est_fidele_au_texte(cas):
    fidele(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", CAS_DU_CLASSEUR, ids=lambda c: c.nom)
async def test_la_table_de_la_base_de_la_commande_est_fidele_au_texte(cas, commerce, monkeypatch):
    fidele(cas, await jouer(cas.scenario, commerce, monkeypatch))


@pytest.mark.parametrize("cas", CAS_DU_MOTEUR, ids=lambda c: c.nom)
async def test_la_table_du_moteur_de_la_commande_est_fidele_au_texte(cas, appel, monkeypatch):
    fidele(cas, await jouer(cas.scenario, appel, monkeypatch))


@pytest.mark.parametrize("cas", CAS_DE_LA_SALLE + CAS_DU_MOTEUR_DE_LA_RESERVATION, ids=lambda c: c.nom)
async def test_la_table_de_la_reservation_est_fidele_au_texte(cas, salle, monkeypatch):
    fidele(cas, await jouer(cas.scenario, salle, monkeypatch))


# ── A3 : la base de la commande n'écrit plus aucun texte de secours (le modèle formule d'après le statut, le manque et les faits) ─────────────────────────

@pytest.mark.parametrize("cas", CAS_DE_LA_CARTE + CAS_DE_LA_DEMANDE, ids=lambda c: c.nom)
async def test_aucun_refus_de_la_base_de_la_commande_n_ecrit_de_texte(cas):
    r = await jouer(cas.scenario)
    assert r.suggestion == "", r


@pytest.mark.parametrize("cas", CAS_DU_CLASSEUR, ids=lambda c: c.nom)
async def test_aucun_refus_du_classeur_de_la_commande_n_ecrit_de_texte(cas, commerce, monkeypatch):
    r = await jouer(cas.scenario, commerce, monkeypatch)
    assert r.suggestion == "", r


# ── R1 (audit du lot A) : les deux refus de la base qui avaient gardé l'ancienne forme de ``_refus`` ──────────────────────────────────────────────────────

async def test_un_article_au_poids_sans_poids_se_refuse_incomplet_manque_poids(essai_de):
    """Avant : un article au poids sans poids faisait planter l'outil (``TypeError``) ; après : refus INCOMPLETE, manque ``poids``, raison ``poids_a_dire``, aucun texte."""
    from api.tests.mark.partie_1.aides_briques import brique, objets_charges

    e = await brique(essai_de, "QTE1")
    await objets_charges(e)
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-HOUMOUS-UNIQUE", "quantite": 1}])
    assert r.statut == "INCOMPLETE" and r.manque == "poids" and r.faits["raison"] == "poids_a_dire" and r.suggestion == "", r


async def test_un_interdit_de_la_ligne_n_a_pas_de_manque(essai_de):
    """Avant : le texte vide tombait dans ``manque`` (``''``) ; après : ``None``, comme tout refus qui ne manque de rien."""
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "PRX8")
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TENDERS-UNIQUE", "quantite": 5, "choix": []}])
    assert r.statut == "INTERDIT" and r.manque is None and r.suggestion == "", r


async def test_un_interdit_de_l_option_n_a_pas_de_manque(essai_de):
    """RP1 : l'option truffe refusée à ce moment (brique PRX1) : INTERDIT sans manque ni texte (``restauration_commande.py:207``)."""
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "PRX1")
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCE-TRUFFE", "quantite": 1}]}])
    assert r.statut == "INTERDIT" and r.faits["raison"] == "indisponible_a_ce_moment" and r.manque is None and r.suggestion == "", r
