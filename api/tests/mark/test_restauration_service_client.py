"""[.mark] Module Restauration, lot 7 (W44, W23, E-15) : le connecteur interne ``service`` : infos pratiques par sujets, message laissé avec son urgence, passage de main sur motif.

Par la vraie exécution d'une action de connecteur (``execution.executer``) ; la lecture de la connaissance est remplacée par un enregistreur (jamais la base ni un tiers).

| Test | Ce qu'il prouve |
|---|---|
| infos pratiques | un sujet de la liste fermée rend le texte de SON document ; sans document ou vide : « je ne peux pas vous le confirmer », jamais inventé ; hors liste : refus ; cloisonné par organisation |
| urgence | ``normale`` par défaut, ``urgente`` seulement dite ; hors liste : refusée, rien n'est écrit ; une demande par appel ; l'après-appel dit l'urgence |
| passage de main | plainte et problème réel : ``PASSER`` ; tout autre motif : une demande de rappel, jamais un transfert ; le réglage ne peut que restreindre |
| mesures | chaque geste est mesuré |
| catalogue | le connecteur est au catalogue, ses trois outils, les listes fermées en choix |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.apres_appel import rappels
from api.services.integrations.connectors import catalogue, execution, mesures
from api.services.service_client import action as service

TEXTES = {"doc-horaires": "Ouvert tous les jours de midi à 14 h et de 19 h à 22 h.", "doc-vide": "   "}
LUS: list[tuple] = []


class FauxClient:
    async def get_full_text_documents(self, organization_id, document_uuids):
        LUS.append((organization_id, tuple(document_uuids)))
        if organization_id != 7:                                  # cloisonnement : un document d'une autre organisation n'est jamais lu
            return []
        return [SimpleNamespace(full_text=TEXTES[u]) for u in document_uuids if u in TEXTES]


@pytest.fixture(autouse=True)
def connaissance(monkeypatch):
    LUS.clear()
    monkeypatch.setattr("api.db.db_client", FauxClient())


SUJETS = {"horaires": "doc-horaires", "paiement": "doc-vide"}


EQUIPE = {"runtime_configuration": {"equipe": {"cles": ["alice"], "etablissement": "casa"}}}  # ce que le code estampille quand l'équipe a des personnes


async def jouer(action, arguments, fiche=None, reglages=None, organisation=7, equipe=True):
    config = {"connecteur": "service", "action": action, "reglages": reglages if reglages is not None else {"sujets": SUJETS}}
    appel = {"caller_number": "06 12 34 56 78", **(EQUIPE if equipe else {})}
    return await execution.executer(organisation, config, arguments, fiche if fiche is not None else {}, None, appel=appel)


async def test_un_sujet_rend_le_texte_de_son_document_et_sans_document_il_ne_peut_pas_confirmer():
    fiche: dict = {}
    r = await jouer("infos_pratiques", {"sujet": "horaires"}, fiche)
    assert r.statut == "ok" and r.donnees["statut"] == "OK" and r.donnees["faits"]["texte"].startswith("Ouvert tous les jours")
    assert LUS == [(7, ("doc-horaires",))]                       # lu en entier, par son uuid, jamais une recherche approchée
    for sujet in ("paiement", "animaux"):                         # document vide, sujet sans document
        r = await jouer("infos_pratiques", {"sujet": sujet}, fiche)
        assert (r.donnees["statut"], r.donnees["suggestion"]) == ("INCONNU", "Je ne peux pas vous le confirmer.") and "texte" not in r.donnees["faits"]
    assert [(m["mesure"], m["detail"]) for m in mesures.lues(fiche)] == [("service.info_inconnue", "paiement"), ("service.info_inconnue", "animaux")]


async def test_un_sujet_hors_liste_est_refuse_et_une_autre_organisation_ne_lit_rien():
    r = await jouer("infos_pratiques", {"sujet": "meteo"})
    assert r.statut == "erreur" or r.donnees["statut"] == "ARGUMENT_INVALIDE"                  # refusé par le choix fermé, ou par le code
    assert LUS == []
    autre = await jouer("infos_pratiques", {"sujet": "horaires"}, organisation=8)
    assert autre.donnees["statut"] == "INCONNU" and LUS == [(8, ("doc-horaires",))]            # son organisation, jamais celle d'un autre


# test_l_urgence_vient_d_une_liste_fermee… : supprimé au lot 6 (D49), la fiche du service pose l'urgence en booléen (``urgent``) et le prénom revient au greffier ; sens repris par partie_1/test_l06_parole.py::test_service_message_une_fois_issue_et_mesure


# test_le_passage_de_main_… : supprimé au lot 6 (D49), la fiche du service ne transfère pas (la réclamation est un message, B12) ; la cible du passage est tenue par partie_1/test_l06_parole.py::test_passer_a_egal_a_la_version_finale, le message par partie_1/test_l06_parole.py::test_service_message_une_fois_issue_et_mesure


# test_sans_ligne_d_equipe_le_passage_de_main_ne_promet_personne : supprimé au lot 6 (D49), plus de passage de main dans la fiche du service : une plainte est un message laissé, jamais « je vous passe quelqu'un » ; sens repris par partie_1/test_l06_parole.py::test_service_message_une_fois_issue_et_mesure


def test_le_connecteur_est_au_catalogue_avec_ses_listes_fermees():
    connecteur, _ = catalogue.trouver("service", "infos_pratiques")
    # lot 3 : la fiche du service remplace laisser_un_message et passage_de_main ; 20/11 (ab1e332b) : les quatre lectures de l'accueil s'y ajoutent
    assert [a.nom for a in connecteur.actions] == ["fiche", "infos_pratiques", "ouverture_en_ce_moment", "heure_annoncee", "remises_disponibles", "envoyer_un_sms"]
    choix = {(a.nom, p.nom): p.choix for a in connecteur.actions for p in a.parametres if p.choix}
    assert set(service.SUJETS) <= set(choix[("infos_pratiques", "sujet")])  # lot 3 : la liste de l'accueil y ajoute « autre »
    assert catalogue.categorie_de(connecteur) == "Nos connecteurs"