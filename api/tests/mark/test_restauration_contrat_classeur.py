"""[.mark] Module Restauration, lot 2 : la couche d'accès tient le contrat comptoir ↔ classeur, sans fuite de SQL ni de vocabulaire.

| Test | Ce qu'il prouve |
|---|---|
| fonctions du contrat | ``restauration.py`` expose EXACTEMENT les 17 fonctions du contrat, asynchrones, avec la connexion en premier et les arguments du contrat |
| statuts fermés | la liste des statuts rendus aux outils est celle du contrat (§ 5) ; un statut hors liste est refusé à la construction |
| aucune session hors de la couche | aucune requête sur les tables ``resto_*`` en dehors de la couche d'accès, des migrations et des tests |
| vocabulaire | aucun mot de restaurant dans les mécanismes communs (heure, plages, capacité, recherche) ; le balayeur est éprouvé sur un cas rouge |
| de bout en bout | la couche s'appelle par la façade seule : importer, commander, changer de statut, retrouver, purger |
"""

from __future__ import annotations

import inspect
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge, restauration
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE, JEUDI_MIDI

RACINE = Path(restauration.__file__).resolve().parents[2]  # api/

# § 4 du contrat : fonction -> arguments, dans l'ordre (la connexion d'abord, sauf mention).
CONTRAT = {
    "carte_du_restaurant": ["connexion", "etablissement_id", "moment"],
    "version_carte": ["connexion", "etablissement_id"],
    "ruptures_du_restaurant": ["connexion", "etablissement_id", "moment"],
    "etat_caisse": ["connexion", "etablissement_id"],
    "etat_combine": ["connexion", "etablissement_id", "type_", "moment"],
    "chercher_dans_la_liste": ["connexion", "liste", "texte", "etablissement_id"],
    "client_par_numero": ["connexion", "etablissement_id", "telephone"],
    "enregistrer_commande": ["connexion", "etablissement_id", "brouillon", "jeton_relecture"],
    "changer_statut": ["connexion", "etablissement_id", "numero", "de", "vers", "source"],
    "statut_commande": ["connexion", "etablissement_id", "numero", "telephone", "jour"],
    "commandes_planifiees": ["connexion", "etablissement_id", "du", "au"],
    "disponibilites_capacite": ["connexion", "etablissement_id", "jour", "couverts", "duree_minutes"],
    "remises_applicables": ["connexion", "etablissement_id", "panier", "moment", "client"],
    "ecrire_consigne_client": ["connexion", "etablissement_id", "telephone", "consigne"],
    "importer_carte": ["connexion", "etablissement_id", "carte_commune", "source"],
    "poser_rupture": ["connexion", "etablissement_id", "code_caisse", "disponible", "fin", "source"],
    "purger": ["connexion", "avant"],
}
# § 5 du contrat.
STATUTS_DU_CONTRAT = {
    "OK", "RETENU", "AMBIGU", "INTROUVABLE", "INCOMPLETE", "ENREGISTREE", "TRANSMISE", "REFUSEE", "DEJA_FAIT", "FERME", "PAUSE_TYPE",
    "LIVRAISON_TERMINEE", "HORS_ZONE", "MINIMUM_NON_ATTEINT", "RUPTURE", "CHOIX_OBLIGATOIRE", "MAXIMUM_ATTEINT", "HORS_CARTE",
    "MOYEN_NON_ACCEPTE", "PLAFOND_TITRE_RESTAURANT", "INDISPONIBLE", "ARGUMENT_INVALIDE",
}
RAISONS_DU_CONTRAT = {"produit_inconnu", "prix_different", "restaurant_ferme", "remise_inconnue", "caisse_injoignable", "autre"}


def test_la_facade_expose_exactement_les_fonctions_du_contrat():
    assert sorted(restauration.__all__) == sorted(CONTRAT)
    for nom, arguments in CONTRAT.items():
        fonction = getattr(restauration, nom)
        assert inspect.iscoroutinefunction(fonction), nom
        parametres = [p for p in inspect.signature(fonction).parameters if not p.startswith("_")]
        # les arguments du contrat sont les premiers, dans l'ordre ; ce qui suit est facultatif (mot-clé)
        assert parametres[: len(arguments)] == arguments, (nom, parametres)
        for p in list(inspect.signature(fonction).parameters.values())[len(arguments):]:
            assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is not inspect.Parameter.empty, (nom, p.name)


def test_les_statuts_rendus_aux_outils_sont_ceux_du_contrat_et_fermes():
    assert STATUTS_DU_CONTRAT <= restauration.STATUTS
    assert restauration.STATUTS - STATUTS_DU_CONTRAT == {"INTERDIT"}  # le seul de plus : le retour de changer_statut (§ 4)
    assert restauration.RAISONS_REFUS == RAISONS_DU_CONTRAT
    assert restauration.Resultat("OK").faits == {}
    with pytest.raises(ValueError):
        restauration.Resultat("PEUT_ETRE")
    with pytest.raises(Exception):  # noqa: B017 - figé
        restauration.Resultat("OK").statut = "RETENU"  # type: ignore[misc]


TABLES = re.compile(r"\bresto_(categorie|produit|declinaison|groupe_choix|option|formule|surcouche|rupture|etat_caisse|reglage_type|zone|commande|commande_ligne|message_recu|liaison|compteur_jour|client|remise|envoi|reglage|salle|table|service|duree_groupe|regle_reservation|reservation|journal|recap_jour|version_carte)\b")


def _fichiers_python():
    for chemin in RACINE.rglob("*.py"):
        relatif = chemin.relative_to(RACINE).as_posix()
        if relatif.startswith(("tests/", "alembic/", ".venv")) or "__pycache__" in relatif:
            continue
        yield relatif, chemin


def test_aucune_requete_sur_les_tables_du_classeur_hors_de_la_couche_d_acces():
    couche = re.compile(r"^db/bases_clients/restauration[a-z_]*\.py$")
    fuites = []
    for relatif, chemin in _fichiers_python():
        if couche.match(relatif):
            continue
        for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
            if TABLES.search(ligne):
                fuites.append(f"{relatif}:{numero}: {ligne.strip()[:100]}")
    assert fuites == [], fuites
    # le balayeur voit bien une fuite (cas rouge connu)
    assert TABLES.search('await c.execute("SELECT * FROM mark.resto_commande")') and TABLES.search("DELETE FROM mark.resto_client WHERE")
    assert not TABLES.search("nom_de_la_table = 'restaurant'")


# Les mécanismes communs : jamais un mot de restaurant (les noms d'objets vivent dans le module et dans les données).
MECANISMES_COMMUNS = ["db/bases_clients/horloge.py", "db/bases_clients/plages.py", "db/bases_clients/capacite.py", "db/bases_clients/remises_moteur.py", "db/bases_clients/annonce_heure.py", "db/bases_clients/zones_de_service.py", "db/bases_clients/dates_futures.py",
                       "db/bases_clients/recherche_liste.py",
                       "db/bases_clients/recherche_liste_moteur.py",
                       "db/bases_clients/recherche_liste_banc.py", "db/bases_clients/recherche_liste_index.py"]
MOTS_INTERDITS = re.compile(
    r"restaura|pizza|burger|\bmenu|cuisine|\bplat\b|boisson|serveur|repas|\bsalle|couvert|livraison|emporter|caisse|ticket|rupture|allerg|commande|\bcarte|\bchef\b|\bdessert",
    re.IGNORECASE,
)


def _mots(texte: str) -> list[str]:
    return sorted({m.group(0).lower() for m in MOTS_INTERDITS.finditer(texte)})


def test_aucun_mot_de_restaurant_dans_les_mecanismes_communs():
    for relatif in MECANISMES_COMMUNS:
        mots = _mots((RACINE / relatif).read_text(encoding="utf-8"))
        # le seul mot toléré : le nom du module qui porte l'en-tête de chaque fichier
        assert set(mots) <= {"restaura"}, (relatif, mots)
        corps = (RACINE / relatif).read_text(encoding="utf-8")
        assert not re.search(r"restaura(?!tion)", corps, re.IGNORECASE), relatif  # « Restauration » seulement, jamais « restaurant »
    # le balayeur rougit sur un cas connu
    assert _mots("def creneaux_pour_les_couverts(table, pizza): ...") == ["couvert", "pizza"]
    assert _mots("la commande part en cuisine pour la livraison") == ["commande", "cuisine", "livraison"]
    assert _mots("des unités, des occupations, un effectif, des créneaux, une plage de jours") == []


# --------------------------------------------------------------------------- #
# Par la façade seule
# --------------------------------------------------------------------------- #


async def test_la_facade_suffit_de_l_import_a_la_purge(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        a = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'a', 'a', 'Europe/Paris' FROM mark.entreprise RETURNING id")
        with horloge.remplacer(base_prete, JEUDI_MIDI - timedelta(days=40)):
            bilan = await restauration.importer_carte(c, a, CARTE, "caisse")
            assert bilan["ajoutes"] > 0 and bilan["sans_code_caisse"] == []
            assert (await restauration.chercher_dans_la_liste(c, "carte", "Coca-Cola", a)).statut == "RETENU"
            r = await restauration.enregistrer_commande(
                c, a, {"mode": "emporter", "client": {"telephone": "+33612345678", "prenom": "Alice"},
                       "lignes": [{"code_caisse": "BOI-COCA-COLA-33-CL"}], "paiement": {"moyens": [{"moyen": "carte", "montant": 200}]}}, "relu",
            )
            assert r.statut == "ENREGISTREE"
            numero = r.faits["numero"]
            assert (await restauration.changer_statut(c, a, numero, "nouvelle", "envoyee", "agent")).statut == "OK"
            assert (await restauration.statut_commande(c, a, numero=numero)).faits["commandes"][0]["statut"] == "envoyee"
            assert (await restauration.client_par_numero(c, a, "+33612345678"))["nb_commandes"] == 1
            assert (await restauration.etat_combine(c, a, "emporter", JEUDI_MIDI - timedelta(days=40)))["ouvert"] is True
            assert await restauration.version_carte(c, a) >= 1 and await restauration.etat_caisse(c, a) is None
            assert (await restauration.poser_rupture(c, a, "BOI-COCA-COLA-33-CL", False, None, "agent")).statut == "OK"
            assert len(await restauration.ruptures_du_restaurant(c, a)) == 1
            assert (await restauration.ecrire_consigne_client(c, a, "+33612345678", "Sonnez deux fois")).statut == "OK"
            assert (await restauration.remises_applicables(c, a, {"mode": "emporter", "sous_total": 200}, JEUDI_MIDI)) == []
            assert (await restauration.commandes_planifiees(c, a, JEUDI_MIDI - timedelta(days=41), JEUDI_MIDI))["nombre"] == 0
            assert (await restauration.carte_du_restaurant(c, a))["version"] >= 1
            assert (await restauration.disponibilites_capacite(c, a, JEUDI_MIDI.date(), 2)).manque == "duree"
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            purge = await restauration.purger(c, JEUDI_MIDI - timedelta(days=30))
        assert purge["commandes"] == 1 and purge["recapitulatif"] == 1
        assert (await restauration.statut_commande(c, a, numero=numero)).statut == "INTROUVABLE"
    finally:
        await c.close()
