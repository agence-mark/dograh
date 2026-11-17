"""[.mark] Module Restauration, lot 5, étape 4 : le connecteur interne « Commande », le module au registre, les réglages d'agent.

| Test | Ce qu'il prouve |
|---|---|
| seize outils | le connecteur déclare exactement les seize outils du plan (sept du lot 5, quatre du lot 6, cinq du lot 7), aucun paramètre ne porte une organisation, une base ni un établissement |
| module | une entrée au registre, ses clés d'agent existent au schéma ; un module coupé ne laisse AUCUN outil dans l'appel |
| réglages | lus dans la configuration de l'agent, une valeur absente ou mauvaise retombe sur le défaut |
| vrai gestionnaire | par le gestionnaire d'un outil ``integration`` : le panier vit dans la fiche de l'appel, la relecture arrive « mot pour mot » (conseil de l'outil), le réglage de l'outil gagne |
| cloisonnement | un identifiant d'établissement envoyé par le modèle est coupé ; l'établissement est celui de l'appel |
| mécanisme commun | une AUTRE source (un catalogue de pièces) joue le même moteur sans y toucher ; aucun mot de restaurant dans le moteur commun |
| module coupé | un geste sur un module coupé rend un refus fermé, jamais un panier |
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.db.bases_clients import recherche_liste
from api.db.bases_clients.recherche_liste import Element
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.commande import moteur, panier, reglages, source as registre_des_sources
from api.services.commande.moteur import Reglages
from api.services.commande.resultat import Resultat
from api.services.integrations.connectors import catalogue
from api.services.integrations.connectors.outil import creer_gestionnaire
from api.services.modules.etat import outil_d_un_module_coupe
from api.services.modules.registre import PAR_CODE, cles_des_modules
from api.services.restauration import appel as lieu_de_l_appel
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401

OUTILS = ["etat_ouverture", "heure_annoncee", "verifier_adresse", "resoudre_une_date", "choisir_mode", "ajouter", "modifier", "retirer", "vider_commande", "voir_commande", "remises_disponibles", "voir_produit", "reconnaitre_le_client", "retrouver_commande", "envoyer_un_message", "finaliser"]
RACINE = Path(moteur.__file__).resolve().parents[1]  # api/services/


# --------------------------------------------------------------------------- #
# Le connecteur, le module, les réglages
# --------------------------------------------------------------------------- #


def test_le_connecteur_declare_les_seize_outils_du_plan_sans_identifiant_du_modele():
    c = catalogue.connecteur("commande")
    assert c is not None and c.interne and c.executer_interne is not None
    assert [a.nom for a in c.actions] == OUTILS
    for action in c.actions:
        noms = {p.nom for p in action.parametres}
        assert not noms & {"organization_id", "organisation", "base", "etablissement", "etablissement_id", "site", "site_id", "zone_id"}, action.nom
    assert [a.nom for a in c.actions if a.ecrit] == ["finaliser"]  # les quatre outils du lot 6 lisent seulement  # seul l'enregistrement écrit hors de l'appel
    assert catalogue.categorie_de(c) == "Nos connecteurs"


def test_le_module_est_au_registre_avec_ses_cles_d_agent_au_schema():
    module = PAR_CODE["commande"]
    assert module.interrupteur == "commande_sur_catalogue" and module.connecteurs == ("commande",)
    assert [b.code for b in module.besoins] == ["liste", "zone", "commande"]
    cles = module.cles_de_l_agent()
    assert set(cles) <= set(WorkflowConfigurationDefaults.model_fields) and set(cles) <= set(cles_des_modules())
    assert WorkflowConfigurationDefaults().commande_moities_prix == "plus_chere"


def test_un_module_coupe_ne_laisse_aucun_outil_dans_l_appel():
    outil = SimpleNamespace(category="integration", definition={"type": "integration", "config": {"connecteur": "commande", "action": "ajouter"}})
    assert outil_d_un_module_coupe(outil, {"commande_sur_catalogue": False}) is True
    assert outil_d_un_module_coupe(outil, {"commande_sur_catalogue": True}) is False
    assert outil_d_un_module_coupe(outil, {}) is False  # défaut : allumé
    assert outil_d_un_module_coupe(outil, None) is False  # moteur sans configuration : rien n'est retiré, comme avant


def test_les_reglages_sont_lus_dans_la_configuration_de_l_agent_et_retombent_sur_le_defaut():
    assert reglages.reglages_de_la_commande({"commande_sur_catalogue": False}) is None
    assert reglages.reglages_de_la_commande(None) == Reglages()
    r = reglages.reglages_de_la_commande(
        {"commande_ordre_impose": False, "commande_vente_en_plus": False, "commande_notes_libres": False, "commande_moities_prix": "moyenne"}
    )
    assert (r.ordre_impose, r.vente_en_plus, r.notes_libres, r.regle_moities, r.relecture_en_deux_temps) == (False, False, False, "moyenne", True)
    mauvais = reglages.reglages_de_la_commande({"commande_moities_prix": "au_pif", "commande_ordre_impose": "peut-être"})
    assert (mauvais.regle_moities, mauvais.ordre_impose) == ("plus_chere", True)


# --------------------------------------------------------------------------- #
# Par le vrai gestionnaire d'un outil ``integration``
# --------------------------------------------------------------------------- #


@pytest.fixture
def appel_de_test(commerce, monkeypatch):
    """Un appel : la base du client de ``commerce`` et son établissement A servis par l'appel (le reste est le vrai chemin de l'outil)."""
    async def base_et_cle(ctx):
        return commerce.base, "a"

    monkeypatch.setattr("api.services.restauration.source_commande.base_et_cle_de_l_appel", base_et_cle)
    lances: list[tuple] = []  # l'envoi à la prise part en tâche de fond : ici on le ramasse, aucune tâche ne survit au test
    monkeypatch.setattr("api.services.restauration.source_commande.LANCEUR", lambda *a: lances.append(a))
    fiche: dict[str, Any] = {}
    moteur_double = SimpleNamespace(
        _gathered_context=fiche, _call_context_vars={"caller_number": "06 12 34 56 78"}, _workflow_run_id=4242, configurations_des_modules={},
    )

    async def organisation():
        return 7

    manager = SimpleNamespace(_engine=moteur_double, get_organization_id=organisation)

    async def jouer(action: str, config: dict | None = None, **arguments) -> dict:
        rendus: list[dict] = []

        async def rendre(valeur, *a, **k):
            rendus.append(valeur)

        outil = SimpleNamespace(
            name=action, description=None, definition={"type": "integration", "config": {"connecteur": "commande", "action": action, **(config or {})}}
        )
        await creer_gestionnaire(manager, outil, action)(SimpleNamespace(arguments=arguments, result_callback=rendre))
        assert len(rendus) == 1
        return rendus[0]

    return SimpleNamespace(jouer=jouer, fiche=fiche, moteur=moteur_double, commerce=commerce, lances=lances)


async def test_le_vrai_gestionnaire_garde_le_panier_dans_la_fiche_de_l_appel(appel_de_test):
    jouer = appel_de_test.jouer
    assert (await jouer("choisir_mode", mode="à emporter"))["statut"] == "OK"
    r = await jouer("ajouter", articles="une regina normale et un coca")
    assert r["statut"] == "OK" and r["faits"]["panier"]["articles"] == 2
    p = appel_de_test.fiche[panier.CLE]
    assert [(l["nom"], l["quantite"]) for l in p["lignes"]] == [("Regina Normale", 1), ("Coca-Cola", 1)]
    voir = await jouer("voir_commande")
    assert voir["statut"] == "OK" and voir["faits"]["total"] == 1490 and "Vous avez" in voir["suggestion"]
    assert "euro" in voir["suggestion"]


async def test_la_relecture_est_dite_par_le_code_par_conseil_de_l_outil_et_le_reglage_gagne(appel_de_test):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="emporter")
    await jouer("ajouter", articles="une regina normale et un coca")
    for _ in range(3):
        r = await jouer("finaliser", prenom="Alice", moyen="carte")
        if r.get("manque") == "relecture":
            break
    assert r["manque"] == "relecture" and r["statut"] == "INCOMPLETE"
    assert r["restitution"] == "dit_par_le_code" and r["texte_a_dire"] == r["suggestion"] and r["suggestion"].startswith("Je vous relis")
    assert "_restitution" not in r
    reformule = await jouer("finaliser", {"restitution": "reformule"}, moyen="especes")  # M106 : un rappel sans rien de nouveau ne relit plus
    assert reformule["restitution"] == "reformule" and "mêmes faits" in reformule["consigne_de_restitution"]


async def test_un_identifiant_d_etablissement_envoye_par_le_modele_est_coupe(appel_de_test):
    jouer = appel_de_test.jouer
    await jouer("choisir_mode", mode="emporter", etablissement_id=999, site_id=999, organization_id=1)
    r = await jouer("ajouter", articles="un coca", etablissement_id=999)
    assert r["statut"] == "OK"
    total = await appel_de_test.commerce.c.fetchval("SELECT count(*) FROM mark.site")
    assert total == 2  # l'établissement servi est A : le panier se chiffre sur SA carte, B n'a pas de carte


async def test_un_module_coupe_rend_un_refus_ferme_jamais_un_panier(appel_de_test):
    appel_de_test.moteur.configurations_des_modules = {"commande_sur_catalogue": False}
    r = await appel_de_test.jouer("ajouter", articles="un coca")
    assert r["statut"] == "INDISPONIBLE"
    assert panier.CLE not in appel_de_test.fiche


async def test_un_etablissement_introuvable_rend_indisponible_sans_casser_l_appel(appel_de_test, monkeypatch):
    async def inconnue(ctx):
        raise lieu_de_l_appel.LieuIntrouvable("Aucune base de client rattachée à cette organisation.")

    monkeypatch.setattr("api.services.restauration.source_commande.base_et_cle_de_l_appel", inconnue)
    r = await appel_de_test.jouer("voir_commande")
    assert r["statut"] == "INDISPONIBLE"


# --------------------------------------------------------------------------- #
# Mécanisme commun : une autre source, le même moteur
# --------------------------------------------------------------------------- #


class SourceDePieces:
    """Un catalogue de pièces détachées : aucun mot de restaurant, le moteur ne le sait pas."""

    modes = ("retrait",)
    libelles_des_modes = {"retrait": "au comptoir"}
    question_de_la_zone = "Où livrer ?"
    libelles_des_moyens = {"virement": "par virement"}
    CATALOGUE = {"P-FILTRE": ("Filtre à huile", 1250), "P-JOINT": ("Joint de culasse", 3400)}

    def exige_une_zone(self, mode):
        return False

    async def etat(self, mode):
        return {"ouvert": True, "statut": None, "raison": None, "reprise": None, "prochaine_ouverture": None, "delai_minutes": 0, "planifiee_permise": False, "phrase": ""}

    async def chercher(self, texte):
        t = recherche_liste.chercher([Element(ref, nom) for ref, (nom, _) in self.CATALOGUE.items()], texte)
        return Resultat(t["statut"], {"retenu": t["retenu"], "candidats": t["candidats"], "options": t.get("options", {})})

    async def article(self, ref, mode):
        nom, prix = self.CATALOGUE[ref]
        return {"id": ref, "nom": nom, "formule": False, "declinaisons": [{"code": ref, "nom": "Unique", "prix": prix, "vendable": True, "rupture": False}],
                "groupes": [], "retirables": [], "ingredients": []}

    async def chiffrer(self, mode, lignes, zone_id, regles):
        total = sum(self.CATALOGUE[l["code"]][1] * l["quantite"] for l in lignes)
        return Resultat("OK", {"lignes": [{"prix_unitaire": self.CATALOGUE[l["code"]][1]} for l in lignes], "sous_total": total, "frais": 0, "total": total})

    async def reglages(self):
        return {"moyens_paiement": ["virement"], "plafond_titre": None}

    async def client(self, telephone):
        return None

    async def consigne(self, telephone, texte):
        return Resultat("OK")

    async def enregistrer(self, brouillon, jeton):
        return Resultat("ENREGISTREE", {"numero": "N-1", "numero_court": "1", "heure_annoncee": None, "total": 0}, "C'est noté.")

    def statut_de_l_enregistrement(self):
        return "ENREGISTREE"

    async def annonce(self, mode, zone_id):
        return None


async def test_une_autre_source_joue_le_meme_moteur_sans_y_toucher():
    source, p, regles = SourceDePieces(), panier.nouveau(), Reglages(vente_en_plus=False)
    assert (await moteur.choisir_mode(source, p, regles, "au comptoir")).statut == "OK"
    r = await moteur.ajouter(source, p, regles, articles="deux filtres à huile et un joint de culasse")
    assert r.statut == "OK", r
    voir = await moteur.voir_commande(source, p, regles)
    assert voir.faits["total"] == 2 * 1250 + 3400 and "cinquante-neuf euros" in voir.suggestion
    appelant = moteur.Appelant("+33612345678", "x")
    lecture = await moteur.finaliser(source, p, regles, appelant, prenom="Marc", moyen="virement")
    assert lecture.manque == "relecture"
    fait = await moteur.finaliser(source, p, regles, appelant, confirmer=True)
    assert fait.statut == "ENREGISTREE"


async def test_le_registre_des_sources_nomme_la_source_de_l_outil():
    class Fabrique:
        def __init__(self, ctx, **options):
            self.ctx, self.options = ctx, options

        async def __aenter__(self):
            return SourceDePieces()

        async def __aexit__(self, *a):
            return False

    registre_des_sources.enregistrer_source("pieces", Fabrique)
    try:
        async with registre_des_sources.ouvrir("pieces", SimpleNamespace(), reglages_de_recherche=None) as s:
            assert s.modes == ("retrait",)
    finally:
        registre_des_sources._SOURCES.pop("pieces", None)
    with pytest.raises(KeyError):
        registre_des_sources.ouvrir("n_existe_pas", SimpleNamespace())


# Le vocabulaire : jamais un mot de restaurant dans le moteur commun (``resultat.py`` seul touche le classeur, par son nom).
MOTS_DU_METIER = re.compile(
    r"restaura(?!tion)|pizza|burger|cuisine|boisson|repas|couvert|dessert|ticket|caisse|allerg|titre_restaurant|\bchef\b|livraison|emporter|sur_place|\bregina|\bcoca|formaggi|\bcarte\b|\bmenu|serveur|\bplat\b|\bsalle",
    re.IGNORECASE,
)
FICHIERS_COMMUNS = ["__init__", "panier", "lecture", "source", "moteur", "parole", "reglages", "action"]


def test_aucun_mot_de_restaurant_dans_le_moteur_commun():
    for nom in FICHIERS_COMMUNS:
        corps = (RACINE / "commande" / f"{nom}.py").read_text(encoding="utf-8")
        assert [m.group(0) for m in MOTS_DU_METIER.finditer(corps)] == [], nom
    # le balayeur rougit sur un cas connu
    assert [m.group(0).lower() for m in MOTS_DU_METIER.finditer("la livraison d'une pizza en cuisine")] == ["livraison", "pizza", "cuisine"]
    assert MOTS_DU_METIER.search("un joint de culasse et un filtre") is None


_ = JEUDI_MIDI
