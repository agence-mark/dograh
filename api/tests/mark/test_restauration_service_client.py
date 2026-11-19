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


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
async def test_l_urgence_vient_d_une_liste_fermee_normale_par_defaut_une_demande_par_appel():
    fiche: dict = {}
    r = await jouer("laisser_un_message", {"objet": "Rappeler pour la privatisation", "prenom": "Alice", "nom": "Durand"}, fiche)  # M102 : qui appelle
    assert (r.donnees["statut"], r.donnees["faits"]["urgence"]) == ("OK", "normale")
    entree = fiche[rappels.CLE_RAPPEL][0]
    assert (entree["origine"], entree["urgence"], entree["numero"], entree["objet"]) == (rappels.ORIGINE_AGENT, "normale", "+33612345678", "Rappeler pour la privatisation")
    assert "URGENT" not in rappels.resume_du_rappel(entree)
    r = await jouer("laisser_un_message", {"objet": "Un client attend sur place", "urgence": "urgente"}, fiche)
    assert r.donnees["faits"]["urgence"] == "urgente" and len(fiche[rappels.CLE_RAPPEL]) == 1       # la nouvelle remplace l'ancienne
    assert "URGENT" in rappels.resume_du_rappel(fiche[rappels.CLE_RAPPEL][0])
    avant = list(fiche[rappels.CLE_RAPPEL])
    r = await jouer("laisser_un_message", {"objet": "x", "urgence": "tres_urgente"}, fiche)
    assert (r.statut == "erreur" or r.donnees["statut"] == "ARGUMENT_INVALIDE") and fiche[rappels.CLE_RAPPEL] == avant   # hors liste : rien n'est écrit
    sans_objet = await jouer("laisser_un_message", {"urgence": "urgente"}, {})
    assert sans_objet.statut == "erreur" or sans_objet.donnees["statut"] == "INCOMPLETE"
    assert mesures.compte(fiche).get("service.message_laisse") == 2


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
async def test_le_passage_de_main_seulement_sur_plainte_ou_probleme_reel_sinon_un_rappel():
    for motif in ("plainte", "probleme_reel"):
        fiche: dict = {}
        r = await jouer("passage_de_main", {"motif": motif, "objet": "x"}, fiche)
        assert (r.donnees["statut"], r.donnees["faits"]["motif"]) == ("PASSER", motif) and rappels.CLE_RAPPEL not in fiche
        assert mesures.compte(fiche) == {"service.passage_de_main": 1}
    fiche = {}
    r = await jouer("passage_de_main", {"motif": "autre", "objet": "Veut parler au patron"}, fiche)
    assert r.donnees["statut"] == "RAPPEL_NOTE" and fiche[rappels.CLE_RAPPEL][0]["motif"] == "autre" and mesures.compte(fiche) == {"service.message_laisse": 1}
    # le réglage de l'outil ne peut que restreindre : seule la plainte passe, le problème réel devient un rappel
    fiche = {}
    r = await jouer("passage_de_main", {"motif": "probleme_reel"}, fiche, reglages={"motifs": ["plainte"]})
    assert r.donnees["statut"] == "RAPPEL_NOTE"
    r = await jouer("passage_de_main", {"motif": "plainte"}, {}, reglages={"motifs": ["plainte", "autre", "n_importe_quoi"]})
    assert r.donnees["statut"] == "PASSER"
    r = await jouer("passage_de_main", {"motif": "autre"}, {}, reglages={"motifs": ["plainte", "autre"]})
    assert r.donnees["statut"] == "RAPPEL_NOTE"                      # « autre » n'est jamais un motif de passage, même écrit dans le réglage


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
async def test_sans_ligne_d_equipe_le_passage_de_main_ne_promet_personne():
    """SA-18, C12 : une plainte sans personne à joindre dans l'appel devient une demande de rappel, jamais « je vous passe quelqu'un »."""
    fiche: dict = {}
    r = await jouer("passage_de_main", {"motif": "plainte", "objet": "Pizza arrivée froide"}, fiche, equipe=False)
    assert r.donnees["statut"] == "RAPPEL_NOTE" and "passe quelqu'un" not in r.donnees["suggestion"]
    assert fiche[rappels.CLE_RAPPEL][0]["motif"] == "plainte"


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
def test_le_connecteur_est_au_catalogue_avec_ses_listes_fermees():
    connecteur, _ = catalogue.trouver("service", "infos_pratiques")
    assert [a.nom for a in connecteur.actions] == ["infos_pratiques", "laisser_un_message", "passage_de_main"]
    choix = {(a.nom, p.nom): p.choix for a in connecteur.actions for p in a.parametres if p.choix}
    assert choix[("infos_pratiques", "sujet")] == tuple(service.SUJETS) and choix[("laisser_un_message", "urgence")] == ("normale", "urgente")
    assert choix[("passage_de_main", "motif")] == ("plainte", "probleme_reel", "autre")
    assert catalogue.categorie_de(connecteur) == "Nos connecteurs"
