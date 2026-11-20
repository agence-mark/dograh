"""[.mark] Chantier Partie 1, lot 17 : le formulaire du restaurateur en trois niveaux (D10, D21, D22), prouvé complet.

* **A** bloque la CRÉATION : les missions cochées (liste fermée), le nom, l'adresse avec sa commune (code INSEE), les services ouverts, et, en
  livraison, le minimum de chaque zone avec sa zone ;
* **B** ne bloque pas la création ; son absence est signalée au fork et au portail, et **bloque la publication** par un test obligatoire
  généré (``tests_generes.py``, D56 : aucun contrôle neuf) ; les missions cochées décident ce qui est requis ;
* **C** n'est jamais bloquant ; l'agent dit qu'il ne peut pas le confirmer.

**Prouvé complet** : ``INVENTAIRE`` range chaque colonne de chaque table de configuration lue par le module (commande, réservation,
établissement, zones, caisse) en A, B ou C, ou la dit hors du formulaire avec sa raison (identifiant, état vivant, donnée générée) ; les tables
d'exploitation (écrites par les appels) sont dites telles. Le test d'inventaire lit le schéma réel de la base du client et le code des modules :
une colonne ou une table nouvelle que personne n'a rangée le fait échouer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MISSIONS = ("prise_de_commande", "prise_de_reservation", "suivi_reclamation_message", "transfert_d_appel", "renseignements")
SERVICES = ("emporter", "livraison", "sur_place")
ALLERGENES = ("renseignes", "renvoyer_vers_le_restaurant")
# Les moyens du module (``schemas/restauration_ecran.MoyenDePaiement``) que le restaurateur coche ; « en ligne » ne se dit pas au téléphone.
MOYENS = ("carte", "especes", "titre_restaurant", "cheque", "carte_livraison")
INSEE = re.compile(r"^(\d{5}|2[AB]\d{3})$")

# Les valeurs par défaut du niveau C (jamais bloquant). Le prénom par défaut est à trancher par Evan (a-trancher.md, lot 17).
PAR_DEFAUT: dict[str, Any] = {"prenom_assistante": "Léa", "type_d_etablissement": "un restaurant", "style": "chaleureux", "lieu_des_tables": "salle"}

A, B, C = "A", "B", "C"


@dataclass(frozen=True)
class Donnee:
    cle: str
    niveau: str
    libelle: str
    si_missions: tuple[str, ...] = ()  # requise seulement si l'une de ces missions est cochée (B)
    si_services: tuple[str, ...] = ()  # requise seulement si l'un de ces services est ouvert


DONNEES: dict[str, Donnee] = {
    d.cle: d
    for d in (
        # A : la création
        Donnee("missions", A, "Les missions de l'agent"),
        Donnee("nom_etablissement", A, "Le nom de l'établissement"),
        Donnee("adresse", A, "L'adresse, avec sa commune"),
        Donnee("services", A, "Les services ouverts"),
        Donnee("zones.minimum", A, "Le minimum de commande de chaque zone", si_services=("livraison",)),
        # B : la publication
        Donnee("horaires", B, "Les horaires par service"),
        Donnee("temps_de_preparation", B, "Le temps de préparation par service", si_missions=("prise_de_commande",)),
        Donnee("zones.frais_et_delai", B, "Les frais et le délai de chaque zone", si_services=("livraison",)),
        Donnee("carte", B, "La carte", si_missions=("prise_de_commande",)),
        Donnee("moyens_paiement", B, "Les moyens de paiement acceptés", si_missions=("prise_de_commande",)),
        Donnee("transfert", B, "Le numéro ou la règle de passage à une personne", si_missions=("transfert_d_appel",)),
        Donnee("reservation.capacite", B, "La capacité", si_missions=("prise_de_reservation",)),
        Donnee("reservation.duree", B, "La durée d'une table", si_missions=("prise_de_reservation",)),
        Donnee("reservation.creneaux", B, "Les créneaux de réservation", si_missions=("prise_de_reservation",)),
        Donnee("allergenes", B, "Les allergènes, ou « renvoyer les questions d'allergie vers le restaurant »", si_missions=("prise_de_commande",)),
        # C : jamais bloquant (§ 2 bis du plan, et ce que les lots 15 et 16 et le lot des manques ont ajouté)
        Donnee("prenom_assistante", C, "Le prénom de l'assistante"),
        Donnee("type_d_etablissement", C, "Le type d'établissement (« une pizzeria »)"),
        Donnee("style", C, "Le style de l'agent (liste fermée)"),
        Donnee("lieu_des_tables", C, "Où l'on mange (salle, terrasse)"),
        Donnee("minimum_general", C, "Le minimum de commande hors zone"),
        Donnee("gratuite_livraison", C, "La gratuité de la livraison"),
        Donnee("zones.details", C, "Les communes exclues d'une zone"),
        Donnee("carte.details", C, "Ingrédients, régimes, descriptions, formules, menus"),
        Donnee("offres", C, "Offres, ventes en plus et remises"),
        Donnee("precommande", C, "La précommande"),
        Donnee("minutes_en_plus", C, "Les minutes en plus les soirs chargés, et la fin du service ce soir"),
        Donnee("titres_et_alcool", C, "Plafond des titres-restaurant, alcool"),
        Donnee("tva", C, "La TVA"),
        Donnee("consigne_allergie", C, "La consigne d'allergie du restaurant, le halal"),
        Donnee("reservation.plan", C, "Salles, tables et règles fines de la réservation"),
        Donnee("caisse", C, "La caisse et ses seuils"),
        Donnee("numeros_et_annonces", C, "Téléphone, second numéro, annonces de fermeture et de pause, fuseau, fermetures datées"),
        Donnee("reglages_du_module", C, "Numéro court, notes libres, pause avec la caisse, sources, moitiés"),
    )
}


def _hors(raison: str) -> tuple[str, str]:
    return ("-", raison)


ID = _hors("identifiant technique")
VIVANT = _hors("état vivant, tenu par le code et l'écran du jour")
DATE = _hors("date d'écriture")
GENERE = _hors("écrit par le code (installation, lexique, synchronisation)")

# table -> colonne -> (niveau, clé de la donnée) ou ("-", raison)
INVENTAIRE: dict[str, dict[str, tuple[str, str]]] = {
    "site": {
        "id": ID, "entreprise_id": ID, "cle": ID, "ordre": ID, "actif": GENERE, "numero_appele": _hors("téléphonie, posée à la mise en service"),
        "nom": (A, "nom_etablissement"), "adresse": (A, "adresse"), "adresse_cp": (A, "adresse"), "adresse_insee": (A, "adresse"),
        "adresse_commune": (A, "adresse"), "adresse_voie": (A, "adresse"), "horaires_texte": (B, "horaires"),
        "numero_transfert": (B, "transfert"), "telephone": (C, "numeros_et_annonces"), "second_numero": (C, "numeros_et_annonces"),
        "fuseau": (C, "numeros_et_annonces"), "annonce_fermeture": (C, "numeros_et_annonces"), "annonce_pause": (C, "numeros_et_annonces"),
        "termes_lexique": GENERE, "etat_force": VIVANT, "etat_force_jusqu_a": VIVANT,
    },
    "horaire": {"id": ID, "site_id": ID, "jour": (B, "horaires"), "ouverture": (B, "horaires"), "fermeture": (B, "horaires")},
    "fermeture": {"id": ID, "site_id": ID, "du": (C, "numeros_et_annonces"), "au": (C, "numeros_et_annonces"), "motif": (C, "numeros_et_annonces")},
    "resto_reglage": {
        "site_id": ID, "maj_le": DATE, "module_actif": GENERE, "moyens_paiement": (B, "moyens_paiement"),
        "allergies_renvoyees_au_restaurant": (B, "allergenes"), "plafond_titre_restaurant": (C, "titres_et_alcool"),
        "titre_alcool_exclu": (C, "titres_et_alcool"), "titre_sans_rendu": (C, "titres_et_alcool"), "consigne_allergie": (C, "consigne_allergie"),
        "halal_restaurant": (C, "consigne_allergie"), "conservation_client_mois": (C, "reglages_du_module"), "prefixe_numero_court": (C, "reglages_du_module"),
        "numero_mode": (C, "reglages_du_module"), "prefixe_mixte": (C, "reglages_du_module"), "notes_libres": (C, "reglages_du_module"),
        "pause_caisse_pause_telephone": (C, "reglages_du_module"), "sources": (C, "reglages_du_module"), "moities_prix": (C, "reglages_du_module"),
    },
    "resto_reglage_type": {
        "site_id": ID, "maj_le": DATE, "type": (A, "services"), "ouvert": (A, "services"), "delai_minimal": (B, "temps_de_preparation"),
        "delai_annonce": (B, "temps_de_preparation"), "planifiee_permise": (C, "precommande"), "jours_a_l_avance": (C, "precommande"),
        "fin_par_jour": (C, "precommande"), "annonce": (C, "precommande"), "capacite_quart_heure": (C, "minutes_en_plus"),
        "minutes_ajoutees": (C, "minutes_en_plus"), "fin_aujourd_hui": (C, "minutes_en_plus"), "pause_jusqu_a": VIVANT, "ajout_jusqu_a": VIVANT,
        "fin_aujourd_hui_le": VIVANT, "fin_aujourd_hui_a": VIVANT,
    },
    "resto_zone": {
        "id": ID, "site_id": ID, "ordre": ID, "maj_le": DATE, "couleur": _hors("couleur de l'écran"), "nom": (A, "zones.minimum"),
        "forme": (A, "zones.minimum"), "communes": (A, "zones.minimum"), "rayon_km": (A, "zones.minimum"), "cercle_km": (A, "zones.minimum"),
        "minimum": (A, "zones.minimum"), "frais": (B, "zones.frais_et_delai"), "delai": (B, "zones.frais_et_delai"), "exclues": (C, "zones.details"),
        "gratuite_des": (C, "gratuite_livraison"), "minutes_ajoutees": (C, "minutes_en_plus"), "ajout_jusqu_a": VIVANT,
    },
    "resto_temps_recurrent": {
        "id": ID, "site_id": ID, "maj_le": DATE, "type": (C, "minutes_en_plus"), "jours": (C, "minutes_en_plus"), "debut": (C, "minutes_en_plus"),
        "fin": (C, "minutes_en_plus"), "minutes_ajoutees": (C, "minutes_en_plus"),
    },
    "resto_service": {
        "id": ID, "site_id": ID, "maj_le": DATE, "nom": (B, "reservation.creneaux"), "jours": (B, "reservation.creneaux"),
        "debut": (B, "reservation.creneaux"), "fin": (B, "reservation.creneaux"), "pas_minutes": (B, "reservation.creneaux"),
    },
    "resto_regle_reservation": {
        "site_id": ID, "maj_le": DATE, "couverts_simultanes": (B, "reservation.capacite"), "delai_minimal": (C, "reservation.plan"),
        "jours_a_l_avance": (C, "reservation.plan"), "couverts_max_groupe": (C, "reservation.plan"), "couverts_max_creneau": (C, "reservation.plan"),
    },
    "resto_duree_groupe": {
        "id": ID, "site_id": ID, "maj_le": DATE, "couverts_min": (B, "reservation.duree"), "couverts_max": (B, "reservation.duree"),
        "duree_minutes": (B, "reservation.duree"),
    },
    "resto_salle": {"id": ID, "site_id": ID, "ordre": ID, "maj_le": DATE, "nom": (C, "reservation.plan"), "plan": (C, "reservation.plan")},
    "resto_table": {
        "id": ID, "site_id": ID, "maj_le": DATE, "salle_id": (C, "reservation.plan"), "nom": (C, "reservation.plan"), "couverts_min": (C, "reservation.plan"),
        "couverts_max": (C, "reservation.plan"), "x": (C, "reservation.plan"), "y": (C, "reservation.plan"), "assemblable_avec": (C, "reservation.plan"),
        "actif": (C, "reservation.plan"),
    },
    "resto_liaison": {
        "site_id": ID, "maj_le": DATE, "prise": (C, "caisse"), "point_de_vente": (C, "caisse"), "mode_passif": (C, "caisse"),
        "alerte_sans_reponse_min": (C, "caisse"), "releve_messages_min": (C, "caisse"), "etat": VIVANT, "derniere_erreur": VIVANT,
        "derniere_synchro": VIVANT, "derniere_releve": VIVANT, "avertissements": VIVANT,
    },
    # La carte : B si la prise de commande est cochée (son cœur : articles, prix, choix) ; le reste en C ; les allergènes en B (D22).
    "resto_categorie": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ordre": (C, "carte.details"), "ref": (B, "carte"), "nom": (B, "carte"),
        "parent_ref": (C, "carte.details"), "masque": (C, "carte.details"), "role": (C, "offres"), "inclus": (C, "carte.details"),
        "disponibilite": (C, "carte.details"),
    },
    "resto_produit": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ordre": (C, "carte.details"), "ref": (B, "carte"), "nom": (B, "carte"),
        "categorie_ref": (B, "carte"), "groupes_refs": (B, "carte"), "numero": (C, "carte.details"), "description": (C, "carte.details"),
        "ingredients": (C, "carte.details"), "allergenes": (B, "allergenes"), "allergenes_etat": (B, "allergenes"), "allergenes_source": (B, "allergenes"),
        "regimes": (C, "carte.details"), "epice": (C, "carte.details"), "nutrition": (C, "carte.details"), "origine": (C, "carte.details"),
        "tva_par_mode": (C, "tva"), "masque": (C, "carte.details"), "disponibilite": (C, "carte.details"), "modes": (C, "carte.details"),
        "alcool": (C, "titres_et_alcool"), "degre": (C, "titres_et_alcool"), "frais": (C, "carte.details"), "max_par_commande": (C, "carte.details"),
        "delai_minimal_heures": (C, "carte.details"), "personnes_min": (C, "carte.details"), "unite": (C, "carte.details"),
        "prix_par_unite": (C, "carte.details"), "arrondi": (C, "carte.details"), "lot_de_vente": (C, "carte.details"),
    },
    "resto_declinaison": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ordre": (C, "carte.details"), "ref": (B, "carte"),
        "produit_ref": (B, "carte"), "nom": (B, "carte"), "code_caisse": (B, "carte"), "prix": (B, "carte"), "prix_par_mode": (C, "carte.details"),
        "disponibilite": (C, "carte.details"), "masque": (C, "carte.details"), "type": (C, "carte.details"), "libelle_question": (C, "carte.details"),
        "quotas": (C, "carte.details"),
    },
    "resto_groupe_choix": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ordre": (C, "carte.details"), "ref": (B, "carte"), "nom": (B, "carte"),
        "min": (B, "carte"), "max": (B, "carte"), "max_par_option": (C, "carte.details"), "defaut_refs": (C, "carte.details"),
        "parent_option_ref": (C, "carte.details"), "role": (C, "carte.details"), "masque": (C, "carte.details"), "inclus": (C, "carte.details"),
        "prix_au_dela": (C, "carte.details"), "si_option": (C, "carte.details"),
    },
    "resto_option": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ordre": (C, "carte.details"), "ref": (B, "carte"),
        "groupe_ref": (B, "carte"), "nom": (B, "carte"), "code_caisse": (B, "carte"), "prix": (B, "carte"), "par_defaut": (C, "carte.details"),
        "retirable": (C, "carte.details"), "masque": (C, "carte.details"), "prix_par_declinaison": (C, "carte.details"), "prix_retrait": (C, "carte.details"),
        "disponibilite": (C, "carte.details"), "modes": (C, "carte.details"), "prix_par_mode": (C, "carte.details"), "allergenes": (B, "allergenes"),
        "allergenes_etat": (B, "allergenes"), "allergenes_source": (B, "allergenes"),
    },
    "resto_formule": {
        "id": ID, "site_id": ID, "portee": ID, "source": GENERE, "maj_le": DATE, "ref": (C, "carte.details"), "nom": (C, "carte.details"),
        "code_caisse": (C, "carte.details"), "prix": (C, "carte.details"), "categorie_ref": (C, "carte.details"), "lignes": (C, "carte.details"),
        "supplement": (C, "carte.details"), "disponibilite": (C, "carte.details"), "masque": (C, "carte.details"), "numero": (C, "carte.details"),
        "modes": (C, "carte.details"), "age_max": (C, "carte.details"), "public": (C, "carte.details"), "personnes": (C, "carte.details"),
        "tailles": (C, "carte.details"), "par_lot": (C, "carte.details"),
    },
    "resto_surcouche": {
        "id": ID, "site_id": ID, "maj_le": DATE, "objet": ID, "ref": ID, "lexique": GENERE, "produit_source": GENERE, "produit_maj_le": DATE,
        "synonymes": (C, "carte.details"), "synonymes_a_relire": (C, "carte.details"), "etoile": (C, "offres"), "phrase": (C, "carte.details"),
        "ingredients": (C, "carte.details"), "allergenes_ecrits": (B, "allergenes"), "allergenes": (B, "allergenes"), "alcool": (C, "titres_et_alcool"),
        "genre": (C, "carte.details"), "nom_commun": (C, "carte.details"), "du_moment": (C, "offres"), "texte_du_jour": (C, "offres"),
    },
    "resto_remise": {
        "id": ID, "site_id": ID, "maj_le": DATE, "source": GENERE, "ref": (C, "offres"), "nom": (C, "offres"), "mecanisme": (C, "offres"),
        "declencheur": (C, "offres"), "effet": (C, "offres"), "perimetre": (C, "offres"), "cumul": (C, "offres"), "limite": (C, "offres"),
        "phrase": (C, "offres"), "moment": (C, "offres"), "debut": (C, "offres"), "fin": (C, "offres"), "etat": (C, "offres"),
        "ref_caisse": (C, "offres"), "code": (C, "offres"),
    },
}

# Écrites par les appels et la caisse, jamais par le restaurateur : aucune n'est une donnée du formulaire.
TABLES_D_EXPLOITATION: dict[str, str] = {
    "resto_commande": "les commandes enregistrées par les appels",
    "resto_commande_ligne": "les lignes des commandes enregistrées",
    "resto_client": "les clients reconnus par les appels",
    "resto_reservation": "les réservations enregistrées par les appels",
    "resto_compteur_jour": "le compteur des numéros du jour",
    "resto_version_carte": "la version de la carte, tenue par le code",
    "resto_rupture": "les ruptures du jour (état vivant, caisse ou écran)",
    "resto_plan_soir": "le plan des tables du soir (écran du jour)",
    "resto_remise_offre": "les offres dites pendant les appels",
}

# Les modules dont le test d'inventaire lit le code (les cinq de la fiche, et ceux à qui ils confient leurs requêtes).
MODULES_LUS = (
    "api/db/bases_clients/restauration_carte.py",
    "api/db/bases_clients/restauration_zone.py",
    "api/db/bases_clients/restauration_reglage.py",
    "api/services/restauration/source_commande.py",
    "api/services/restauration/source_reservation.py",
    "api/db/bases_clients/restauration_commande.py",
    "api/db/bases_clients/restauration_reservation.py",
    "api/db/bases_clients/restauration_temps.py",
)


def niveau_de(cle: str) -> str:
    return DONNEES[cle].niveau


# --------------------------------------------------------------------------- le contrôle d'un formulaire


@dataclass
class Controle:
    a_manquer: list[str] = field(default_factory=list)  # données A absentes ou fausses : la création est refusée
    b_manquer: list[str] = field(default_factory=list)  # données B requises absentes : signalées, la publication est bloquée
    signalements: list[str] = field(default_factory=list)  # ce qui n'est pas compris (une règle inconnue) : signalé, jamais bloquant

    @property
    def creation_permise(self) -> bool:
        return not self.a_manquer


def completer(formulaire: Mapping[str, Any]) -> dict[str, Any]:
    """Le formulaire avec les valeurs par défaut du niveau C (rien d'écrit par-dessus ce qui est dit)."""
    sortie = {**PAR_DEFAUT, **{k: v for k, v in dict(formulaire).items() if v is not None}}
    return sortie


def requise(d: Donnee, missions: set[str], services: set[str]) -> bool:
    if d.si_missions and not (missions & set(d.si_missions)):
        return False
    return not (d.si_services and not (services & set(d.si_services)))


def _texte(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _a(f: Mapping[str, Any]) -> list[str]:
    manque: list[str] = []
    missions = f.get("missions")
    if not isinstance(missions, list) or not missions or any(m not in MISSIONS for m in missions):
        manque.append("missions")
    if not _texte(f.get("nom_etablissement")):
        manque.append("nom_etablissement")
    adresse = f.get("adresse") if isinstance(f.get("adresse"), Mapping) else {}
    if not (_texte(adresse.get("commune")) and INSEE.match(str(adresse.get("insee") or "")) and _texte(adresse.get("voie"))):
        manque.append("adresse")
    services = f.get("services")
    if not isinstance(services, list) or not services or any(s not in SERVICES for s in services):
        manque.append("services")
    if isinstance(services, list) and "livraison" in services:
        zones = f.get("zones") or []
        if not zones or any(not _texte(z.get("nom")) or not isinstance(z.get("minimum"), int) or z["minimum"] < 0 for z in zones if isinstance(z, Mapping)):
            manque.append("zones.minimum")
    return manque


def _b_present(cle: str, f: Mapping[str, Any], faits: Mapping[str, Any]) -> bool:
    """Une donnée B est présente dans le formulaire, ou déjà dans la base du client (``faits``, lus à l'installation)."""
    if faits.get(cle):
        return True
    if cle == "horaires":
        h = f.get("horaires")  # par jour (1 = lundi) : [["11:00", "14:00"], ...]
        return isinstance(h, Mapping) and any(h.values())
    if cle == "temps_de_preparation":
        t = f.get("temps_de_preparation") or {}
        return isinstance(t, Mapping) and all(isinstance(t.get(s), int) for s in set(f.get("services") or ()) & {"emporter", "livraison"})
    if cle == "zones.frais_et_delai":
        zones = f.get("zones") or []
        return bool(zones) and all(isinstance(z.get("frais"), int) and isinstance(z.get("delai"), int) for z in zones)
    if cle == "carte":
        return bool(f.get("carte"))
    if cle == "moyens_paiement":
        m = f.get("moyens_paiement")
        return isinstance(m, list) and bool(m) and all(x in MOYENS for x in m)
    if cle == "transfert":
        return _texte((f.get("transfert") or {}).get("numero"))
    if cle == "reservation.capacite":
        return isinstance((f.get("reservation") or {}).get("capacite"), int)
    if cle == "reservation.duree":
        return isinstance((f.get("reservation") or {}).get("duree_minutes"), int)
    if cle == "reservation.creneaux":
        return bool((f.get("reservation") or {}).get("creneaux"))
    if cle == "allergenes":
        return f.get("allergenes") in ALLERGENES
    return False


def controler(formulaire: Mapping[str, Any], faits: Mapping[str, Any] | None = None) -> Controle:
    """Le contrôle du formulaire : A (la création), B selon les missions et les services (la publication). ``faits`` : ce que la base du client
    porte déjà (une carte synchronisée, des horaires venus de la caisse) ; une donnée déjà là n'est jamais redemandée."""
    f = completer(formulaire)
    faits = faits or {}
    controle = Controle(a_manquer=_a(f))
    missions = set(f.get("missions") or ()) if isinstance(f.get("missions"), list) else set()
    services = set(f.get("services") or ()) if isinstance(f.get("services"), list) else set()
    for d in DONNEES.values():
        if d.niveau == B and requise(d, missions, services) and not _b_present(d.cle, f, faits):
            controle.b_manquer.append(d.cle)
    for regle in f.get("regles_inconnues") or []:
        controle.signalements.append(f"regle_inconnue:{str(regle)[:80]}")
    return controle
