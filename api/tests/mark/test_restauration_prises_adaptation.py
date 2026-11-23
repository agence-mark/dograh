"""[.mark] Module Restauration, lot 3 : une règle par capacité absente (``adaptation.py``), prouvée, et aucun code par fournisseur.

| Test | Ce qu'il prouve |
|---|---|
| état | sans lecture de l'état, le portail et la fiche établissement font foi |
| étapes | sans « acceptée », l'outil rend ``TRANSMISE`` ; avec elle, ``OK`` seulement une fois la commande prise en charge |
| veille | notification signée, interrogation, ou rien, d'après la fiche |
| imbrication | les choix imbriqués sont aplatis pour la prise qui n'en a pas ; gardés pour celle qui en a |
| second téléphone | le second numéro va dans la note de commande ; gardé tel quel quand la prise le représente |
| paiement mixte | écrit dans la note quand la prise ne porte qu'un paiement ; gardé sinon |
| retrait | les ingrédients retirés passent dans la note de la ligne quand la prise n'a pas de ``removed`` |
| anti-doublon, clients, remises | recherche avant renvoi, client de notre base seulement, portail maître des remises |
| rien de modifié | l'argument n'est jamais modifié |
| pas de fournisseur ailleurs | aucun fichier du module, hors ``prises/``, ne compare à un nom de fournisseur : le reste du système lit la fiche |
"""

from __future__ import annotations

import copy
import dataclasses
import re
from pathlib import Path

from api.db.bases_clients import restauration
from api.services.restauration.caisse.prises import adaptation as a
from api.services.restauration.caisse.prises.fiches import HUBRISE, IMPRIMANTE, PORTAIL, TEST, TEST_SANS_ACCEPTEE

RACINE = Path(restauration.__file__).resolve().parents[2]  # api/


def _commande() -> dict:
    return {
        "numero": "n", "mode": "livraison", "note": "Sonnez deux fois",
        "client": {"telephone": "+33600000001", "prenom": "Camille", "second_numero": {"numero": "+33600000002", "qui": "Paul", "pourquoi": "livreur"}},
        "lignes": [
            {"code_caisse": "PIZ", "nom": "Pizza", "prix_unitaire": 1000, "quantite": 1, "note": "bien cuite", "retires": ["olives", "oignons"],
             "choix": [{"option_code": "A", "quantite": 1, "choix": [{"option_code": "B", "quantite": 2, "choix": [{"option_code": "C", "quantite": 1}]}]}, {"option_code": "D", "quantite": 1}]},
        ],
        "paiement": {"moyens": [{"moyen": "carte", "montant": 1500}, {"moyen": "especes", "montant": 505}]},
    }


def test_sans_lecture_de_l_etat_le_portail_et_la_fiche_etablissement_font_foi():
    assert a.source_de_l_etat(HUBRISE) == "caisse" and a.source_de_l_etat(TEST) == "caisse" and a.source_de_l_etat(PORTAIL) == "caisse"
    assert a.source_de_l_etat(IMPRIMANTE) == "portail"
    assert a.source_de_l_etat(dataclasses.replace(HUBRISE, etat_restaurant="envoye")) == "portail"  # écrit seulement : on ne le lit pas


def test_sans_etape_acceptee_l_outil_rend_transmise_jamais_acceptee():
    assert a.statut_pour_l_outil(TEST_SANS_ACCEPTEE, "recue") == "TRANSMISE"
    assert a.statut_pour_l_outil(TEST_SANS_ACCEPTEE, "acceptee") == "TRANSMISE"  # même si la prise le dit : elle ne sait pas le faire (fiche)
    assert a.statut_pour_l_outil(IMPRIMANTE, "imprimee") == "TRANSMISE" and a.statut_pour_l_outil(IMPRIMANTE, None) == "TRANSMISE"
    assert a.statut_pour_l_outil(HUBRISE, "recue") == "TRANSMISE" and a.statut_pour_l_outil(HUBRISE, "inconnu") == "TRANSMISE"
    assert a.statut_pour_l_outil(HUBRISE, "acceptee") == "OK" and a.statut_pour_l_outil(HUBRISE, "prete") == "OK"
    assert a.statut_pour_l_outil(HUBRISE, "refusee") == "TRANSMISE"


def test_la_veille_suit_la_fiche():
    assert a.mode_de_veille(HUBRISE) == "notification"
    assert a.mode_de_veille(IMPRIMANTE) == "interrogation"
    assert a.mode_de_veille(PORTAIL) == "aucun"


def test_les_choix_imbriques_sont_aplatis_pour_la_prise_sans_imbrication():
    avant = _commande()
    envoyee = a.adapter_commande(HUBRISE, avant)
    assert [c["option_code"] for c in envoyee["lignes"][0]["choix"]] == ["A", "B", "C", "D"]
    assert all("choix" not in c for c in envoyee["lignes"][0]["choix"])
    assert [(c["option_code"], c["quantite"]) for c in envoyee["lignes"][0]["choix"]] == [("A", 1), ("B", 2), ("C", 1), ("D", 1)]  # quantités gardées
    gardee = a.adapter_commande(IMPRIMANTE, avant)  # l'imprimante imprime l'imbrication
    assert gardee["lignes"][0]["choix"] == avant["lignes"][0]["choix"]
    assert avant == _commande()  # jamais modifié


def test_le_second_numero_va_dans_la_note_quand_la_prise_n_a_qu_un_telephone():
    envoyee = a.adapter_commande(HUBRISE, _commande())
    assert envoyee["client"]["second_numero"] is None
    assert envoyee["note"] == "Sonnez deux fois | Second numéro : +33600000002 (Paul livreur)"  # HubRise porte plusieurs paiements : rien de mixte
    imprimee = a.adapter_commande(IMPRIMANTE, _commande())
    assert imprimee["client"]["second_numero"]["numero"] == "+33600000002" and imprimee["note"] == "Sonnez deux fois"
    sans_note = _commande()
    sans_note["note"] = None
    sans_note["paiement"] = {"moyens": []}
    assert a.adapter_commande(HUBRISE, sans_note)["note"] == "Second numéro : +33600000002 (Paul livreur)"


def test_le_paiement_mixte_est_ecrit_dans_la_note_quand_la_prise_n_en_porte_qu_un():
    sans_plusieurs = dataclasses.replace(HUBRISE, represente=HUBRISE.represente - {"plusieurs_paiements"})
    c = _commande()
    c["client"]["second_numero"] = None
    envoyee = a.adapter_commande(sans_plusieurs, c)
    assert envoyee["paiement"]["moyens"] == [] and "Paiement mixte : carte 15,00 € + especes 5,05 €" in envoyee["note"]
    # HubRise porte plusieurs paiements : gardés tels quels, rien dans la note
    gardee = a.adapter_commande(HUBRISE, c)
    assert len(gardee["paiement"]["moyens"]) == 2 and gardee["note"] == "Sonnez deux fois"
    unique = _commande()
    unique["paiement"] = {"moyens": [{"moyen": "carte", "montant": 2005}]}
    unique["client"]["second_numero"] = None
    assert a.adapter_commande(sans_plusieurs, unique)["paiement"]["moyens"] == unique["paiement"]["moyens"]  # un seul moyen : pas mixte


def test_les_ingredients_retires_passent_dans_la_note_de_la_ligne_sans_retrait():
    sans_retrait = dataclasses.replace(HUBRISE, represente=HUBRISE.represente - {"retrait"})
    envoyee = a.adapter_commande(sans_retrait, _commande())["lignes"][0]
    assert envoyee["retires"] == [] and envoyee["note"] == "bien cuite ; Sans : olives, oignons"
    assert a.adapter_commande(HUBRISE, _commande())["lignes"][0]["retires"] == ["olives", "oignons"]


def test_anti_doublon_clients_et_remises_suivent_la_fiche():
    assert a.doit_chercher_avant_renvoi(HUBRISE) and not a.doit_chercher_avant_renvoi(IMPRIMANTE) and not a.doit_chercher_avant_renvoi(PORTAIL)
    assert a.client_lu_par_la_prise(HUBRISE) and not a.client_lu_par_la_prise(IMPRIMANTE)
    assert a.maitre_des_remises(HUBRISE) == "caisse" and a.maitre_des_remises(IMPRIMANTE) == "portail"
    # changer la fiche change la règle : rien n'est lu ailleurs
    assert a.maitre_des_remises(dataclasses.replace(HUBRISE, remises_lues=False)) == "portail"
    assert a.doit_chercher_avant_renvoi(dataclasses.replace(IMPRIMANTE, anti_doublon="chercher_avant_renvoi"))


def test_une_commande_sans_rien_a_adapter_revient_identique():
    simple = {"numero": "n", "mode": "emporter", "client": {"telephone": "+33600000001"}, "lignes": [{"code_caisse": "X", "quantite": 1}], "paiement": {"moyens": []}}
    assert a.adapter_commande(HUBRISE, copy.deepcopy(simple)) == simple


# --------------------------------------------------------------------------- aucun code par fournisseur hors de ``prises/``

FOURNISSEUR = re.compile(r"""(==|!=|\bin\b|\bis\b)\s*[(\[{]?\s*["'](hubrise|imprimante|innovorder|tactill|zelty|popina)["']""", re.IGNORECASE)
LECTURE_DU_NOM = re.compile(r"""(prise|fournisseur)(\.nom|\[["']nom["']\])\s*(==|!=|in)\b""")


def _fichiers_du_module_hors_prises():
    yield from sorted((RACINE / "db" / "bases_clients").glob("restauration*.py"))
    yield from sorted((RACINE / "services" / "restauration").glob("*.py"))
    for sous_dossier in sorted(p for p in (RACINE / "services" / "restauration").iterdir() if p.is_dir() and p.name not in ("prises", "__pycache__")):
        yield from sorted(f for f in sous_dossier.rglob("*.py") if "prises" not in f.relative_to(sous_dossier).parts)  # la caisse range ses prises dans caisse/prises/


def _fautes(texte: str) -> list[str]:
    return [m.group(0) for m in FOURNISSEUR.finditer(texte)] + [m.group(0) for m in LECTURE_DU_NOM.finditer(texte)]


def test_aucun_fichier_du_module_hors_des_prises_ne_compare_a_un_nom_de_fournisseur():
    fichiers = list(_fichiers_du_module_hors_prises())
    assert fichiers, "le balayeur ne voit aucun fichier"
    fautes = {f.name: _fautes(f.read_text(encoding="utf-8")) for f in fichiers}
    assert {n: x for n, x in fautes.items() if x} == {}
    # le balayeur rougit sur des cas connus
    assert _fautes('if prise == "hubrise":') and _fautes("if prise.nom == 'imprimante'") and _fautes('if nom in ("zelty", "x")')
    assert _fautes('if cap.annulation:') == []
