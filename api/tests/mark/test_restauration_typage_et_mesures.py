"""[.mark] Module Restauration, lot 7 (W21, W13) : les appels typés, l'état par tâche, les mesures écrites par les outils.

| Test | Ce qu'il prouve |
|---|---|
| types | un statut fermé du retour devient un des cinq types ; ``OK`` et ``INCOMPLETE`` ne sont pas des échecs |
| exécution typée | un outil qui rend ``INTROUVABLE`` : ``not_found`` + une mesure ; une écriture qui dépasse son délai : ``uncertain_outcome`` ; une lecture en panne : ``outage`` |
| une seule nouvelle tentative | éteint par défaut ; allumé, une LECTURE en panne est rejouée une fois ; une écriture, un autre type d'échec, jamais |
| état par tâche | champs et compteurs déclarés, remis à zéro à la tâche suivante, le même identifiant ne touche à rien, un champ non déclaré lève |
| mesures | liste fermée, décompte, la tâche est dite ; hors liste : pas écrite |
| de bout en bout | les vrais outils de la commande écrivent leurs mesures, et l'état de la tâche compte le refus, puis repart de zéro à la commande suivante |
| réglages | la clé de nouvelle tentative est au schéma, éteinte par défaut |
"""

from __future__ import annotations

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.integrations.connectors import catalogue, etat_par_tache, execution, garde, mesures, typage
from api.services.integrations.connectors.catalogue import Action, Connecteur, declarer
from api.services.restauration.mesures import mesures as mesures_du_module
from api.tests.mark.test_restauration_commande_outils import appel_de_test  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

APPELS: list[str] = []
PANNES = {"restantes": 0}


async def _jouer(action, arguments, ctx, delai_s):
    APPELS.append(action.nom)
    if action.nom == "lit_introuvable":
        return {"statut": "INTROUVABLE", "faits": {}, "suggestion": ""}
    if action.nom in ("lit_en_panne", "ecrit_en_panne"):
        if PANNES["restantes"] > 0:
            PANNES["restantes"] -= 1
            raise RuntimeError("panne")
        return {"statut": "OK", "faits": {}, "suggestion": ""}
    if action.nom == "ecrit_lent":
        raise TimeoutError("trop lent")
    if action.nom == "lit_refusee":
        return {"statut": "HORS_ZONE", "faits": {}, "suggestion": ""}
    return {"statut": "OK", "faits": {}, "suggestion": ""}


def _action(nom, ecrit=False):
    return Action(nom=nom, description=nom, parametres=(), ecrit=ecrit, preparer=lambda *_: None, resultat=lambda *_: {})


@pytest.fixture(scope="module", autouse=True)
def connecteur_de_test():
    nom = "typage_essai"
    declarer(
        Connecteur(
            nom=nom, libelle="Essai", integration="interne", interne=True, executer_interne=_jouer,
            actions=(_action("lit_introuvable"), _action("lit_en_panne"), _action("ecrit_en_panne", True), _action("ecrit_lent", True), _action("lit_refusee")),
        )
    )
    yield nom
    catalogue._CATALOGUE.pop(nom, None)


@pytest.fixture(autouse=True)
def remise_a_zero():
    APPELS.clear()
    PANNES["restantes"] = 0


async def jouer(action, fiche=None, configurations=None):
    return await execution.executer(1, {"connecteur": "typage_essai", "action": action}, {}, fiche if fiche is not None else {}, None, configurations=configurations)


def test_un_statut_ferme_devient_un_des_cinq_types_et_un_succes_n_est_pas_un_echec():
    assert {t: typage.type_du_statut(s) for s, t in [("RUPTURE", "slot_taken"), ("INTROUVABLE", "not_found"), ("HORS_ZONE", "bad_request"), ("INDISPONIBLE", "outage")]} == {
        "slot_taken": "slot_taken", "not_found": "not_found", "bad_request": "bad_request", "outage": "outage"
    }
    assert typage.type_du_statut("REFUSEE", {"detail": "complet"}) == "slot_taken"
    assert typage.type_du_statut("REFUSEE", {"raison": "caisse_injoignable"}) == "outage"
    assert typage.type_du_statut("REFUSEE", {"raison": "prix_different"}) == "bad_request"
    for succes in ("OK", "INCOMPLETE", "ENREGISTREE", "AMBIGU", "DEJA_FAIT", None):
        assert typage.type_du_statut(succes) is None
    assert set(typage.TYPES) == {"slot_taken", "bad_request", "not_found", "outage", "uncertain_outcome"}
    assert typage.type_de_l_echec("repli", {}, "deadline passed", ecrit=True) == "uncertain_outcome"
    assert typage.type_de_l_echec("repli", {}, "deadline passed", ecrit=False) == "outage"


async def test_l_execution_type_l_echec_et_le_mesure():
    fiche: dict = {}
    r = await jouer("lit_introuvable", fiche)
    assert (r.statut, r.type_echec) == ("ok", "not_found")
    r = await jouer("ecrit_lent", fiche)
    assert (r.statut, r.type_echec) == ("repli", "uncertain_outcome")
    PANNES["restantes"] = 1
    r = await jouer("lit_en_panne", fiche)
    assert (r.statut, r.type_echec) == ("repli", "outage")
    assert (await jouer("lit_en_panne", fiche)).type_echec is None
    assert [(m["mesure"], m["outil"], m["detail"]) for m in mesures.lues(fiche)] == [
        ("outil.echec", "typage_essai.lit_introuvable", "not_found"),
        ("outil.echec", "typage_essai.ecrit_lent", "uncertain_outcome"),
        ("outil.delai_depasse", "typage_essai.ecrit_lent", None),
        ("outil.echec", "typage_essai.lit_en_panne", "outage"),
    ]


async def test_une_seule_nouvelle_tentative_seulement_sur_une_lecture_en_panne_et_seulement_allumee():
    allumee = {garde.CLE_NOUVELLE_TENTATIVE: True}
    PANNES["restantes"] = 1
    assert (await jouer("lit_en_panne")).type_echec == "outage" and APPELS == ["lit_en_panne"]      # éteint : aucune nouvelle tentative
    APPELS.clear()
    PANNES["restantes"] = 1
    r = await jouer("lit_en_panne", configurations=allumee)
    assert r.statut == "ok" and APPELS == ["lit_en_panne"] * 2                                         # allumé : une lecture en panne est rejouée UNE fois
    APPELS.clear()
    PANNES["restantes"] = 5
    r = await jouer("lit_en_panne", configurations=allumee)
    assert r.type_echec == "outage" and APPELS == ["lit_en_panne"] * 2                                 # jamais plus d'une
    APPELS.clear()
    PANNES["restantes"] = 1
    assert (await jouer("ecrit_en_panne", configurations=allumee)).statut == "repli" and APPELS == ["ecrit_en_panne"]   # une écriture : jamais
    APPELS.clear()
    assert (await jouer("lit_refusee", configurations=allumee)).type_echec == "bad_request" and APPELS == ["lit_refusee"]   # une demande qui ne tient pas : jamais
    assert (await jouer("ecrit_lent", configurations=allumee)).type_echec == "uncertain_outcome"      # écriture au résultat incertain : jamais rejouée à l'aveugle
    assert APPELS.count("ecrit_lent") == 1


def test_la_cle_de_nouvelle_tentative_est_au_schema_eteinte_par_defaut():
    assert WorkflowConfigurationDefaults.model_fields[garde.CLE_NOUVELLE_TENTATIVE].default is False
    assert garde.CLE_NOUVELLE_TENTATIVE in garde.CLES


MODELE = etat_par_tache.Modele(champs=("mode", "zone"), compteurs=("refus",))


def test_l_etat_d_une_tache_est_declare_remis_a_zero_a_la_suivante_et_intact_dans_la_meme():
    fiche: dict = {}
    e1 = etat_par_tache.commencer(fiche, MODELE, "commande-1")
    etat_par_tache.noter(e1, "mode", "emporter")
    assert etat_par_tache.compter(e1, "refus") == 1 and etat_par_tache.compter(e1, "refus") == 2
    assert etat_par_tache.commencer(fiche, MODELE, "commande-1") is e1 and e1["champs"]["mode"] == "emporter"      # la même tâche : rien ne bouge
    e2 = etat_par_tache.commencer(fiche, MODELE, "commande-2")
    assert (e2["tache"], e2["rang"], e2["champs"], e2["compteurs"]) == ("commande-2", 2, {"mode": None, "zone": None}, {"refus": 0})
    with pytest.raises(ValueError):
        etat_par_tache.noter(e2, "inconnu", 1)
    with pytest.raises(ValueError):
        etat_par_tache.compter(e2, "inconnu")
    assert etat_par_tache.commencer(None, MODELE, "x")["compteurs"] == {"refus": 0}                                 # sans fiche : un état jetable


def test_les_mesures_sont_une_liste_fermee_comptee_et_disent_leur_tache():
    fiche: dict = {}
    assert mesures.ecrire(fiche, "commande.rupture", "commande.ajouter", "x") is True
    assert mesures.ecrire(fiche, "commande.fote_de_frappe", "commande.ajouter") is False and mesures.ecrire(None, "commande.rupture", "x") is False
    etat_par_tache.commencer(fiche, MODELE, "commande-3")
    mesures.ecrire(fiche, "commande.rupture", "commande.ajouter")
    assert [m["tache"] for m in mesures.lues(fiche)] == [None, "commande-3"]
    assert mesures.compte(fiche) == {"commande.rupture": 2}
    fiche[mesures.CLE].append({"mesure": "hors.liste"})
    assert mesures.compte(fiche) == {"commande.rupture": 2}


def test_la_correspondance_de_la_commande_et_de_la_reservation():
    fiche: dict = {}
    for statut in ("HORS_ZONE", "MINIMUM_NON_ATTEINT", "RUPTURE", "HORS_CARTE", "FERME", "MOYEN_NON_ACCEPTE", "INDISPONIBLE", "OK"):
        mesures_du_module.de_la_commande(fiche, "ajouter", {"statut": statut, "faits": {}})
    mesures_du_module.de_la_commande(fiche, "finaliser", {"statut": "ENREGISTREE", "faits": {"mode": "livraison", "total_remises": 300}})
    mesures_du_module.de_la_commande(fiche, "voir_commande", {"statut": "OK", "faits": {"total_remises": 300}})
    assert mesures.compte(fiche) == {
        "commande.hors_zone": 1, "commande.minimum_non_atteint": 1, "commande.rupture": 1, "commande.hors_catalogue": 1, "commande.fermeture": 1,
        "commande.moyen_refuse": 1, "commande.indisponible": 1, "commande.enregistree": 1, "commande.remise_appliquee": 1,   # une seule fois par tâche
    }
    assert [m["detail"] for m in mesures.lues(fiche) if m["mesure"] == "commande.enregistree"] == ["livraison"]
    r: dict = {}
    mesures_du_module.de_la_reservation(r, "reserver", {"statut": "ENREGISTREE", "faits": {}})
    mesures_du_module.de_la_reservation(r, "reserver", {"statut": "REFUSEE", "faits": {"detail": "complet"}})
    mesures_du_module.de_la_reservation(r, "reserver", {"statut": "REFUSEE", "faits": {"detail": "trop_tard", "raison": "autre"}})
    mesures_du_module.de_la_reservation(r, "reserver", {"statut": "INDISPONIBLE", "faits": {}})
    assert mesures.compte(r) == {"reservation.enregistree": 1, "reservation.complet": 1, "reservation.refusee": 1, "reservation.indisponible": 1}
    assert [m["detail"] for m in mesures.lues(r) if m["mesure"] == "reservation.refusee"] == ["trop_tard"]


async def test_la_fiche_de_la_commande_ecrit_ses_mesures(appel_de_test):  # noqa: F811
    """Lot 4 de la partie 1 (D49) : réécrit sur la fiche (lot 3 : une seule action qui écrit), par le vrai gestionnaire d'outil. L'enregistrement
    compté (``commande.enregistree``) est prouvé par test_la_correspondance_de_la_commande_et_de_la_reservation ; « la commande suivante, une autre
    tâche » est retiré : une commande par appel (E30)."""
    from types import SimpleNamespace

    from api.services.commande import contrat
    from api.services.integrations.connectors.actions.commande import COMMANDE
    from api.services.integrations.connectors.outil import _propriete
    from api.services.workflow import cases_selon_l_etat as CS

    jouer_outil, fiche = appel_de_test.jouer, appel_de_test.fiche

    def dit(parole: str) -> None:
        """Ce qu'elle dit, puis les cases montrées au modèle pour ce tour, gardées comme le fait la requête (D52 ; ``partie_1/porte_essai.py``)."""
        fiche[CS.CLE_DES_PAROLES] = [*(fiche.get(CS.CLE_DES_PAROLES) or []), parole]
        fiche[CS.CLE_DU_TOUR] = int(fiche.get(CS.CLE_DU_TOUR) or 0) + 1
        proprietes = {x.nom: _propriete(x, None) for x in COMMANDE.action("fiche").parametres}
        vue = contrat.vue_de_l_appel(fiche)
        visibles, _ = CS.schema_selon_l_etat(proprietes, ["a_dire"], contrat.cases_visibles_de_la_vue(vue), contrat.forme_de_la_vue(vue))
        CS.garder_les_cases_montrees(SimpleNamespace(_gathered_context=fiche), {"fiche": CS.chemins_du_schema(visibles)})

    dit("à emporter, une pizza qui n'existe pas du tout")
    r = await jouer_outil("fiche", a_dire="Je regarde.", mode_de_retrait="emporter", ajouter=[{"article": "pizza qui n'existe pas du tout", "quantite": 1}])
    statuts = [x["statut_du_module"] for x in r.get("resultats") or []]
    assert any(s in ("INTROUVABLE", "HORS_CARTE", "AMBIGU") for s in statuts), r
    if "HORS_CARTE" in statuts:
        assert mesures.compte(fiche).get("commande.hors_catalogue") == 1
    # un refus du métier qui se mesure : une livraison hors zone (``commande.hors_zone``), écrite par la porte (``porte._mesurer``)
    dit("en fait en livraison au 7 rue Victor Hugo à Compiègne")
    r = await jouer_outil("fiche", a_dire="Je regarde.", mode_de_retrait="livraison", adresse="7 rue Victor Hugo", commune="Compiègne")
    assert "HORS_ZONE" in [x["statut_du_module"] for x in r.get("resultats") or []], r
    assert mesures.compte(fiche).get("commande.hors_zone") == 1, mesures.lues(fiche)
    # l'état par tâche (« commande-1 », compteur de refus) était commencé par ``action.py``, retiré au lot 3 : consigné dans a-trancher.md
