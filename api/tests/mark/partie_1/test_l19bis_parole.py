"""[.mark] Chantier Partie 1, lot 19 bis, étape B : les petits correctifs de l'audit de Pierre (notes du 20/11), un test vu rouge chacun.

Allergie (A1, A3, A4), commande (C1 à C8), parole (P1 à P8), tours (T1 à T5), preuves (V1 à V10). Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

import json

from api.services.actions_communes import conversation as CONV
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait, oui_au_numero_dicte  # noqa: F401


# --------------------------------------------------------------------------- A1, A3, A4


async def test_deux_allergies_deux_verifications(essai_de):
    """A1 : « gluten et arachides » : les DEUX allergènes sont vérifiés (avant : seul le premier code trouvé). La salade aux arachides validées est ``present`` ; le blocage est tenu."""
    carte = carte_de("briques/INF1")
    for p in carte["produits"]:
        if p["id"] == "P-SALADE":
            p["allergenes"] = ["arachides"]
    e = await essai_de("briques/INF1", carte=carte)
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salade", ajouter=[{"article": "salade verte", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "gluten et arachides"
    r = await e.tour("je suis allergique au gluten et aux arachides", note_generale="allergique au gluten et aux arachides")
    allergie = r["faits"]["allergie"]
    par_allergene = {a["allergene"]: a["articles"] for a in allergie["allergenes"]}
    assert par_allergene["les arachides"] == [{"article": "Salade verte", "etat": "present"}], allergie
    assert par_allergene["le gluten"] == [{"article": "Salade verte", "etat": "absent_de_la_fiche"}], allergie
    assert not e.p.get("enregistree")


def test_code_dit_au_mot_entier_et_tous_les_codes():
    """A1 : ``codes_dits`` rend tous les codes, au mot entier (« laitue », « semoule », « blettes », « noix de coco » ne sont pas des allergènes) ; un mot non reconnu est signalé."""
    from api.services.restauration.carte_et_allergenes.signalements import codes_dits, code_dit

    assert codes_dits("gluten et arachides") == (["gluten", "arachides"], False)
    assert codes_dits("intolérance au lactose et allergie aux arachides") == (["arachides", "lait"], False)  # dans l'ordre des quatorze
    assert codes_dits("laitue")[0] == [] and codes_dits("semoule")[0] == [] and codes_dits("blettes")[0] == [] and codes_dits("noix de coco")[0] == []
    assert codes_dits("gluten et kiwi") == (["gluten"], True)  # un mot d'allergie non reconnu : à confirmer par l'équipe
    assert code_dit("des cacahuètes") == "arachides" and code_dit("laitue") is None


async def test_sans_x_tient_compte_des_choix_obligatoires(essai_de):
    """A3 : Tacos (sans moutarde), sauce obligatoire parmi algérienne (moutarde), ketchup (sans), maison (inconnu) : « sans moutarde » ne le dit pas « sans », il dit « selon le choix »."""
    e = await essai_de("briques/INF2")
    r = await e.lecture(sujet="allergenes", a_eviter="sans moutarde")
    texte = fait(r)
    assert '"sans": []' in texte, texte
    assert '"selon_le_choix": ["Tacos"]' in texte, texte
    assert "ne contient pas de moutarde" not in texte, texte


async def test_allergene_hors_des_quatorze_a_confirmer(essai_de):
    """A4 : « de l'ail dans la salade ? » (hors des quatorze) : jamais « n'en déclare aucun » : inconnu, à confirmer par l'équipe."""
    e = await essai_de("briques/INF1")
    texte = fait(await e.lecture(sujet="allergenes", article="Salade verte", a_eviter="ail"))
    assert '"signalement": "inconnu"' in texte and "n'en déclare aucun" not in texte, texte



# --------------------------------------------------------------------------- C1 à C8


async def _jusqu_a_la_relecture(e) -> dict:
    """Mène la commande jusqu'à sa relecture posée (refuse ce que le code propose en route) et rend la question."""
    for _ in range(4):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            return q
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "relecture", e.retours[-1]
    return q


async def test_panier_change_apres_l_accord_relu_avant_enregistrement(essai_de):
    """C1 : relecture acceptée, puis un article ajouté : l'accord ne vaut plus (source : ``panier.toucher`` ne remettait pas ``relecture_acceptee`` à faux) ; la nouvelle
    relecture est posée et la commande n'est pas enregistrée avec l'article jamais annoncé."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert e.p["etape"] == "accordee"
    await e.tour("rajoutez un autre gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 2}])
    assert e.p["etape"] != "accordee", "l'accord de la relecture ne vaut plus : le panier a changé"
    await e.tour("non c'est tout", c_est_tout=True)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "relecture" and not e.p.get("enregistree"), (q, e.retours[-1])


async def _jusqu_a_l_enregistrement(e) -> None:
    """Le numéro (dicté) puis le prénom, tant que la commande n'est pas enregistrée."""
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")
    await oui_au_numero_dicte(e)


async def test_billet_puis_carte_enregistre(essai_de):
    """C3 : « un billet de cinquante » puis « finalement par carte » : le billet est effacé avec le moyen espèces (source : ``fin_dite.rendu_sur`` repartait à chaque fiche), la commande s'enregistre."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, en espèces, un billet de cinquante", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="especes", rendu_sur=50)
    r = await e.tour("finalement par carte", moyen_de_paiement="carte_bancaire")
    assert "Sur quel règlement le billet" not in fait(r), r
    assert not (e.p.get("reglement_voulu") or {}).get("rendu_sur") and not (e.p.get("paiement") or {}).get("rendu_sur")
    await _jusqu_a_l_enregistrement(e)
    assert e.p.get("enregistree"), e.retours[-1]


async def test_moyen_montre_apres_regler(essai_de):
    """C3 : le moyen posé par ``regler`` est celui que la vue et l'état lisent (avant : écrit sous ``moyen``, lu sous ``moyens[0]`` : jamais montré)."""
    from api.services.commande import contrat
    from api.services.commande.etat_pour_le_modele import _moyen_pose

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert contrat.vue_de_l_appel(e.fiche_de_l_appel).moyen == "carte"
    assert _moyen_pose(e.p)


async def test_refus_d_une_case_ne_fait_pas_refaire_le_reste(essai_de):
    """C6 : un mode hors liste + un ajout : l'ajout est pris, ``a_faire`` nomme la case refusée et dit que le reste est fait (avant : « rien n'est changé : refais la fiche sans … » : la fiche refaite doublait l'article)."""
    e = await brique(essai_de, "INF1")
    r = await e.tour("une reine, à la plage", mode_de_retrait="à la plage", ajouter=[{"article": "pizza reine", "quantite": 1}])
    assert "ajouter" in r["cases_executees"] and "mode_de_retrait" in r["cases_refusees"], r
    assert len(e.p["lignes"]) == 1
    assert "rien n'est changé" not in r["a_faire"], r["a_faire"]
    assert "mode_de_retrait" in r["a_faire"] and "ajouter" in r["a_faire"] and "déjà fait" in r["a_faire"], r["a_faire"]


async def test_quantite_nulle_ou_negative_refusee(essai_de):
    """C8 : ``quantite: 0`` ou ``-2`` n'ajoute plus « 1 » en silence (source : ``_article_de_la_fiche``) : refus ``quantite_inferieure_a_un`` ; un flottant entier (``2.0``) est deux."""
    e = await brique(essai_de, "INF1")
    for mauvaise in (0, -2):
        r = await e.tour("des reines", ajouter=[{"article": "pizza reine", "quantite": mauvaise}])
        assert not e.p["lignes"] and "quantite_inferieure_a_un" in fait(r), (mauvaise, r)
    await e.tour("deux reines", ajouter=[{"article": "pizza reine", "quantite": 2.0}])
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Pizza reine", 2)]



# --------------------------------------------------------------------------- P1 à P8


def test_chiffres_en_lettres_retenus():
    """P1 : la barrière des chiffres lit les chiffres dits en LETTRES (source : ``CHIFFRE`` ne voyait que ``\d``, ``€``, ``euros`` : l'heure « en lettres » du prompt passait toujours), par le lecteur de nombres commun
    (``forme.valeurs_et_places``) ; ce que la personne a dit reste exempté ; un « un » seul n'est pas un chiffre."""
    from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase

    for phrase in ("Votre commande sera prête à vingt heures quinze.", "Ça vous fera douze cinquante.", "Comptez trente minutes.", "Vous avez dix pour cent de remise."):
        assert chiffre_dans_la_phrase(phrase), phrase
    assert not chiffre_dans_la_phrase("Je vous mets une pizza, un instant, c'est noté.")
    assert not chiffre_dans_la_phrase("C'est noté pour vos deux Margherita à emporter.")  # un compte d'articles en lettres reste dit (banc et fork égaux)
    assert not chiffre_dans_la_phrase("Pour vingt heures, c'est noté.", paroles=["je voudrais venir vers vingt heures"])  # exempté : elle l'a dit
    assert chiffre_dans_la_phrase("Pour vingt heures, c'est noté.", paroles=["je voudrais venir vers dix-neuf heures"])


async def test_relance_retenue_sans_repli_jamais_dite(essai_de):
    """P2 : commande enregistrée, « finalement annulez », fiche refusée, puis une relance « c'est annulé » : retenue même quand le code n'a AUCUNE phrase de remplacement (avant : ``None`` et la
    relance partait à la voix, annulation jamais faite) ; ``RepliqueVerifiee`` retombe sur la phrase neutre du code."""
    from types import SimpleNamespace

    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    await _jusqu_a_l_enregistrement(e)
    assert e.p.get("enregistree")
    e.dit("finalement annulez")
    e.montrer()
    r = await e.fiche(moyen_de_paiement="bitcoin", _montrer=False)  # refus de la fiche (valeur hors liste)
    assert PAROLE.refus_de_la_fiche(r), r
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    v = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    assert v.controler("Je m'en occupe.") is not None
    relance = v.controler_la_relance("C'est fait, votre commande est bien annulée.")
    assert relance is not None and relance.raison == PAROLE.REPLI_A, relance


# --------------------------------------------------------------------------- T1 à T5


def _carte_de_perles() -> dict:
    """OPT3 (bubble tea, toppings), les perles en deux options : « avec des perles » est une hésitation sur l'OPTION, pas sur l'article."""
    carte = carte_de("briques/OPT3")
    for g in carte["groupes"]:
        if g["id"] == "G-TOPPINGS":
            base = g["options"][0]
            g["options"] = [{**base, "id": "G-TOPPINGS-Tapioca", "nom": "Perles de tapioca", "code_caisse": "G-TOPPINGS-TAPIOCA"},
                            {**base, "id": "G-TOPPINGS-Coco", "nom": "Perles de coco", "code_caisse": "G-TOPPINGS-COCO"},
                            *[o for o in g["options"] if o["nom"] == "Litchi"]]
            g["min"] = 0
    return carte


async def test_hesitation_sur_une_option_range_l_option(essai_de):
    """T1 : « un bubble tea avec des perles » : l'hésitation porte sur l'OPTION (tapioca ou coco) ; « tapioca » range l'option sur sa ligne (avant : ``article_dit`` posé sur tout AMBIGU : au « oui »
    le nom de l'option était cherché comme un ARTICLE). Une seule ligne, bubble tea avec perles de tapioca, aucun autre article."""
    e = await brique(essai_de, "OPT3", carte=_carte_de_perles())
    r = await e.tour("un bubble tea avec des perles", ajouter=[{"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "ambiguite" and set(q.get("choix") or []) == {"Perles de tapioca", "Perles de coco"}, (q, fait(r))
    r = await e.tour("tapioca", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["Perles de tapioca"]})
    assert [l["nom"] for l in e.p["lignes"]] == ["Bubble tea"], fait(r)
    assert "tapioca" in fait(e.p["lignes"][0]["choix"]).casefold(), e.p["lignes"]


async def test_cases_illisibles_phrase_du_code(essai_de, monkeypatch):
    """P8 : cases du tour illisibles : la requête ne part pas, mais le code DIT sa phrase (la question en attente, sinon ce qui manque, sinon « pas compris ») : avant, une ligne au journal et plus aucune
    réponse jusqu'au raccrochage."""
    from types import SimpleNamespace

    from pipecat.frames.frames import LLMContextFrame, TTSSpeakFrame
    from pipecat.processors.frame_processor import FrameDirection

    from api.services.pipecat import avant_la_requete as AR
    from api.services.pipecat.reponse_avalee import PHRASE_SI_LA_RELANCE_ECHOUE
    from api.services.workflow.cases_selon_l_etat import CasesIllisibles

    e = await brique(essai_de, "INF1")
    await e.tour("une reine", ajouter=[{"article": "pizza reine", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    moteur = SimpleNamespace(_gathered_context=e.fiche_de_l_appel)
    phrase = AR.phrase_si_les_cases_sont_illisibles(moteur)
    assert phrase == q["texte"].strip(), (phrase, q)  # la question en attente (la relecture), dite telle que le code la tient
    monkeypatch.setattr("api.services.actions_communes.repli.repli_dit_par_le_code", lambda *a, **k: None)
    assert AR.phrase_si_les_cases_sont_illisibles(moteur) == PHRASE_SI_LA_RELANCE_ECHOUE  # rien à redire : « pas compris »
    monkeypatch.undo()
    monkeypatch.setattr(AR, "preparer_la_requete", None, raising=False)

    async def illisible(*_a, **_k):
        raise CasesIllisibles("état illisible")

    monkeypatch.setattr(AR, "preparer_la_requete", illisible)
    dites: list = []
    processeur = AR.AvantLaRequete(moteur, object(), FrameDirection.DOWNSTREAM)

    async def pousser(trame, direction=FrameDirection.DOWNSTREAM):
        dites.append((trame, direction))

    monkeypatch.setattr(processeur, "push_frame", pousser)
    await processeur.process_frame(LLMContextFrame(context=SimpleNamespace(get_messages=lambda: [])), FrameDirection.DOWNSTREAM)
    assert len(dites) == 1 and isinstance(dites[0][0], TTSSpeakFrame) and dites[0][0].text == phrase, dites


def test_retour_a_l_accueil_apres_commande_parole_de_l_accueil():
    """P4 : quand AUCUN outil à cases n'est présenté (retour à l'accueil), les cases montrées du tour d'avant sont vidées (avant : elles restaient, et l'accueil était jugé comme la commande,
    sur le panier) ; le service déclare un dossier de parole vide."""
    from types import SimpleNamespace

    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.workflow import cases_selon_l_etat as CS
    from api.services.workflow import parole_de_la_fiche as PF

    fiche = {CS.CLE_DES_CASES_MONTREES: {"fiche": ["ajouter", "c_est_tout"]}}
    assert PF.porte_la_fiche(fiche)
    CS.contexte_avec_les_cases_de_l_etat(SimpleNamespace(_gathered_context=fiche), SimpleNamespace(tools=None, get_messages=lambda: []))
    assert not PF.porte_la_fiche(fiche), fiche
    service = connecteur("service")
    assert service.dossier_de_la_parole({}) == {} and service.objet_en_cours({}) is False and service.texte_du_manque({}, {}) is None


async def test_issue_commande_enregistree_jamais_ecrasee(essai_de):
    """P6 : commande enregistrée, puis un message laissé ou une réservation : l'issue de l'appel reste « commande enregistrée » (avant : le dernier geste écrasait le premier, la commande n'était plus comptée) ;
    seule l'annulation de la commande l'emporte."""
    from api.services.commande import porte
    from api.services.reservation import porte as porte_reservation

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    await _jusqu_a_l_enregistrement(e)
    assert e.fiche_de_l_appel.get("call_disposition") == "commande_enregistree"
    porte.poser_l_issue(e.ctx, "message_a_transmettre")
    porte_reservation.poser_l_issue(e.ctx, "reservation_enregistree")
    assert e.fiche_de_l_appel.get("call_disposition") == "commande_enregistree", e.fiche_de_l_appel.get("call_disposition")
    porte.poser_l_issue(e.ctx, "commande_annulee")
    assert e.fiche_de_l_appel.get("call_disposition") == "commande_annulee"


async def test_delai_depasse_a_l_enregistrement_commande_jointe_a_l_equipe(essai_de, monkeypatch):
    """P7 : la fiche coupée par son délai (annulation, ``CancelledError`` : jamais attrapée par ``except Exception``) joint la commande en cours au message de l'équipe, comme une panne, pour que la
    phrase d'échec qui promet un rappel soit vraie ; l'annulation est ensuite propagée."""
    import asyncio

    from api.services.apres_appel.rappels import CLE_RAPPEL, ORIGINE_COMMANDE
    from api.services.commande import porte

    e = await brique(essai_de, "INF1")
    await e.tour("une reine", ajouter=[{"article": "pizza reine", "quantite": 1}])

    async def lente(*_a, **_k):
        await asyncio.sleep(30)

    monkeypatch.setattr(porte, "executer_la_fiche", lente)
    e.dit("c'est tout")
    e.montrer()
    try:
        await asyncio.wait_for(e.fiche(c_est_tout=True, _montrer=False), timeout=0.5)
        raise AssertionError("la fiche aurait dû être coupée par son délai")
    except asyncio.TimeoutError:
        pass
    entrees = [x for x in e.fiche_de_l_appel.get(CLE_RAPPEL) or [] if x.get("origine") == ORIGINE_COMMANDE]
    assert len(entrees) == 1 and "eine" in entrees[0]["objet"], entrees
    assert e.fiche_de_l_appel.get("call_disposition") == "message_a_transmettre"


# --------------------------------------------------------------------------- V1 à V10


def _arete_de_porte(nom, fermable):
    from types import SimpleNamespace

    return SimpleNamespace(data=SimpleNamespace(fermee_si_action_ouverte=True if fermable else None), get_function_name=lambda: nom)


def _moteur_a_portes(fermable=True):
    from types import SimpleNamespace

    noeud = SimpleNamespace(out_edges=[_arete_de_porte("fin", fermable), _arete_de_porte("retour", False)])
    return SimpleNamespace(active_agent=SimpleNamespace(current_node=noeud), _gathered_context={})


def _contexte_a_trois_outils():
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.processors.aggregators.llm_context import LLMContext

    outils = [FunctionSchema(name=n, description="x", properties={}, required=[]) for n in ("fiche", "fin", "retour")]
    return LLMContext(messages=[{"role": "user", "content": "oui c'est parfait"}], tools=ToolsSchema(standard_tools=outils))


def _actions_ouvertes(monkeypatch, valeur: bool) -> None:
    from api.services.workflow import action_non_aboutie

    monkeypatch.setattr(action_non_aboutie, "actions_ouvertes", lambda moteur: [{"connecteur": "c", "outil": "fiche"}] if valeur else [])


def test_porte_fermee_tant_qu_une_commande_est_ouverte(monkeypatch):
    """V1 (P1 de l'ancien ``test_portes_fermees_par_l_etat``, remis) : une action ouverte : la porte réglée est retirée des outils de la requête, les autres restent."""
    from api.services.workflow import portes_fermees

    _actions_ouvertes(monkeypatch, True)
    copie = portes_fermees.contexte_sans_les_portes_fermees(_moteur_a_portes(), _contexte_a_trois_outils())
    assert copie is not None and [t.name for t in copie.tools.standard_tools] == ["fiche", "retour"]


def test_porte_ouverte_sans_action_ouverte_ni_porte_reglee(monkeypatch):
    """V1 (P2 et P3 remis) : aucune action ouverte : rien n'est retiré ; une porte non réglée n'est jamais fermée."""
    from api.services.workflow import portes_fermees

    _actions_ouvertes(monkeypatch, False)
    assert portes_fermees.contexte_sans_les_portes_fermees(_moteur_a_portes(), _contexte_a_trois_outils()) is None
    _actions_ouvertes(monkeypatch, True)
    assert portes_fermees.contexte_sans_les_portes_fermees(_moteur_a_portes(fermable=False), _contexte_a_trois_outils()) is None


async def test_porte_fermee_par_la_requete_avant_le_cerveau(monkeypatch):
    """V1 (+1) : la garde AGIT sur la requête qui part : ``preparer_la_requete`` (le chemin d'``avant_la_requete``) rend un contexte sans la porte de fin tant qu'une commande est ouverte
    (``test_l17_gabarit`` ne prouvait que le drapeau posé par le gabarit)."""
    from pipecat.frames.frames import LLMContextFrame

    from api.services.pipecat import avant_la_requete as AR

    _actions_ouvertes(monkeypatch, True)
    trame = await AR.preparer_la_requete(_moteur_a_portes(), object(), LLMContextFrame(context=_contexte_a_trois_outils()))
    assert [t.name for t in trame.context.tools.standard_tools] == ["fiche", "retour"], [t.name for t in trame.context.tools.standard_tools]


async def _accueil(essai_de, monkeypatch, nom, arguments):
    from types import SimpleNamespace

    from api.services.commande import porte

    e = await essai_de("casa-italia")
    return e, await porte.executer(SimpleNamespace(nom=nom), arguments, e.ctx, 5.0)


async def test_ouverture_en_ce_moment_par_la_porte(essai_de, monkeypatch):
    """V3 : « vous êtes ouverts ? » : l'outil de l'accueil passe par ``porte.executer`` et rend les modes avec leur état, lus dans la base (Casa Italia, jeudi midi, ouverte)."""
    e, r = await _accueil(essai_de, monkeypatch, "ouverture_en_ce_moment", {})
    assert r["statut"] == "LU" and r["faits"]["ouverts"] and all("ouvert" in m for m in r["faits"]["modes"]), r
    assert r["resultats"][0]["operation"] == "ouverture_en_ce_moment"
    assert not e.p["lignes"]  # lecture seule


async def test_heure_annoncee_par_la_porte(essai_de, monkeypatch):
    """V3 : « c'est prêt pour quand ? » : l'heure annoncée est calculée par le code (jamais le modèle), le panier ne change pas."""
    e, r = await _accueil(essai_de, monkeypatch, "heure_annoncee", {"mode_de_retrait": "emporter"})
    assert r["statut"] == "LU" and r["faits"].get("heure_annoncee") and r["faits"].get("texte"), r
    assert not e.p["lignes"]


async def test_remises_disponibles_par_la_porte(essai_de, monkeypatch):
    """V3 : « vous avez des offres ? » : répondu toujours (``demande``), par les remises valables maintenant ; aucune remise : ``a_dire`` faux."""
    _, r = await _accueil(essai_de, monkeypatch, "remises_disponibles", {})
    assert r["statut"] == "LU" and "a_dire" in r["faits"] and isinstance(r["faits"].get("remises"), list), r


async def test_envoyer_un_sms_par_la_porte(essai_de, monkeypatch):
    """V3 : « envoyez-moi la carte » : l'envoi passe par ``source.envoyer`` avec le numéro QUI S'AFFICHE (jamais dicté) et le message demandé ; rien n'est écrit dans le panier."""
    from api.services.commande.resultat import Resultat
    from api.services.restauration.source_commande import SourceClasseur

    appels: list = []

    async def envoyer(self, quoi, telephone, cle, organisation):
        appels.append((quoi, telephone))
        return Resultat("OK", {"envoye": quoi}, "")

    monkeypatch.setattr(SourceClasseur, "envoyer", envoyer)
    e, r = await _accueil(essai_de, monkeypatch, "envoyer_un_sms", {"quoi": "carte"})
    assert r["statut"] == "LU" and appels == [("carte", "+33600000000")], (r, appels)
    assert not e.p["lignes"]


async def test_plafond_titres_dit_et_partage_possible(essai_de):
    """C2 : 32 € en titres-restaurant, plafond atteint : la base refuse ``PLAFOND_TITRE_RESTAURANT`` ; le refus est un FAIT BLOQUANT DIT PAR LE CODE (liste d'EXCLUSION des statuts du module : avant,
    statut « FAIT » sans phrase, le refus restait muet) ; et le partage du règlement (une part en titres, le reste en espèces) est PORTÉ jusqu'au moteur par la fin dite (``part``, ``moyen_reste``).
    L'ouverture des deux CASES au modèle change les textes versés du gabarit (prouvés au banc) : listée pour Evan, non faite ici."""
    from api.services.actions_communes.repli import statut_qui_refuse
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    assert all(statut_qui_refuse(s) for s in ("PLAFOND_TITRE_RESTAURANT", "MOYEN_NON_ACCEPTE", "FERME", "PAUSE_TYPE", "REFUSEE", "INDISPONIBLE", "ARGUMENT_INVALIDE", "INTERDIT", "HORS_ZONE"))
    assert not any(statut_qui_refuse(s) for s in ("OK", "RETENU", "INCOMPLETE", "AMBIGU", "CHOIX_OBLIGATOIRE", "ENREGISTREE", "MINIMUM_NON_ATTEINT"))
    e = await essai_de("briques/INF6")
    await e.monde.c.execute("INSERT INTO mark.resto_reglage (site_id, plafond_titre_restaurant) VALUES ($1, 100) ON CONFLICT (site_id) DO UPDATE SET plafond_titre_restaurant = 100", e.monde.a)
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, en titres-restaurant", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="titre_restaurant")
    await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    r = await e.tour("Léa", prenom="Léa")
    r = await oui_au_numero_dicte(e) or r  # DC10 : le plafond bute à l'enregistrement, après le « oui » au numéro dicté
    assert not e.p.get("enregistree"), r
    assert r["statut"] == "PARTIEL" and r["faits"]["fait_bloquant"]["statut_du_module"] == "PLAFOND_TITRE_RESTAURANT", r
    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("prefixe") and "plafond" in json.dumps(r["faits"]["refus_de_la_fiche"], ensure_ascii=False).casefold(), (textes, r["faits"])  # donné au modèle (lot 7b, Q1), pas dit par le code
    # le partage : 1 € en titres, le reste en espèces, porté par la fin dite
    e.p["reglement_voulu"].update({"part": 1, "moyen_reste": "especes"})
    await e.tour("un euro en titres, le reste en espèces", prenom="Léa")
    assert e.p.get("enregistree"), e.retours[-1]


async def test_panne_a_l_enregistrement_phrase_du_code(essai_de, monkeypatch):
    """V10 : panne en pleine commande : le retour est ``REJETEE / indisponible`` ET le code DIT sa phrase (la commande part à l'équipe, qui rappelle) ; avant, aucune phrase : le modèle improvisait au
    second passage. Sans commande à joindre, une phrase qui ne promet aucun rappel."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.commande import porte
    from api.services.workflow import parole_de_la_fiche as PF

    e = await brique(essai_de, "INF1")
    await e.tour("une reine", ajouter=[{"article": "pizza reine", "quantite": 1}])

    async def panne(*a, **k):
        raise RuntimeError("catalogue injoignable")

    monkeypatch.setattr(porte, "executer_la_fiche", panne)
    r = await e.tour("et une salade", ajouter=[{"article": "salade verte", "quantite": 1}])
    assert r["faits"] == {"indisponible": True, "transmise_a_l_equipe": True}, r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == porte.PHRASE_PANNE_COMMANDE_JOINTE, d
    assert "équipe" in d.a_dire and "rappelle" in d.a_dire
    vide = await brique(essai_de, "INF1")
    r = await vide.tour("la carte ?", ajouter=[{"article": "salade verte", "quantite": 1}])
    d = PF.decider_apres_la_fiche(vide.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == porte.PHRASE_PANNE_SANS_COMMANDE and "rappel" not in d.a_dire, d


async def test_oui_ecrit_en_texte_ne_cherche_pas_un_article(essai_de):
    """T2 : « oui » écrit dans ``valeurs`` au lieu de ``sens: accepte`` : jamais cherché comme un article (avant : article « oui » introuvable, la question retirée, l'article en doute perdu) ;
    la question reste posée (contrat fermé accepte / refuse / autre) ; ``sens: accepte`` l'ajoute ensuite."""
    e = await brique(essai_de, "OPT3")
    await e.tour("deux bubble tea avec des perles", ajouter=[{"article": "bubble tea avec des perles", "quantite": 2}])
    q = CONV.question_de(e.p)
    assert q["type"] == "ambiguite", q
    r = await e.tour("oui", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["oui"]})
    assert "INTROUVABLE" not in fait(r) and not e.p["lignes"], fait(r)
    assert (CONV.question_de(e.p) or {}).get("type") == "ambiguite", CONV.question_de(e.p)  # la question reste posée
    q = CONV.question_de(e.p)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Bubble tea", 2)]


async def test_question_de_taille_du_premier_article_posee(essai_de):
    """T3 : « une Regina et un Coca » : la Regina demande sa taille ; le Coca pris ensuite ne masque plus la question (avant : seuls l'hésitation ou le refus comptaient ; statut FAIT, taille jamais demandée)."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une regina et un coca", ajouter=[{"article": "regina", "quantite": 1}, {"article": "coca", "quantite": 1}])
    assert (CONV.question_de(e.p) or {}).get("type") == "variante" and r["statut"] == "A_PRECISER", (CONV.question_de(e.p), fait(r))


async def test_deux_hesitations_deux_questions(essai_de):
    """T3 : deux articles en doute dans la même fiche : la question du premier est posée ; celle du second reste en attente et est posée après la réponse (avant : le second n'était ni ajouté ni posé)."""
    e = await brique(essai_de, "OPT3", carte=_carte_de_perles())
    r = await e.tour("un bubble tea avec des perles et un autre avec des perles",
                     ajouter=[{"article": "bubble tea", "quantite": 1, "composition": ["perles"]}, {"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    q1 = CONV.question_de(e.p)
    assert q1["type"] == "ambiguite", (q1, fait(r))
    await e.tour("tapioca", reponse={"question_id": q1["id"], "sens": "autre", "valeurs": ["Perles de tapioca"]})
    q2 = CONV.question_de(e.p) or {}
    assert q2.get("type") == "ambiguite" and q2["id"] != q1["id"] and len(e.p["lignes"]) == 1, (q2, e.p["lignes"])  # la seconde question est posée
    await e.tour("coco", reponse={"question_id": q2["id"], "sens": "autre", "valeurs": ["Perles de coco"]})
    assert len(e.p["lignes"]) == 2 and not CONV.question_de(e.p) or (CONV.question_de(e.p) or {}).get("type") != "ambiguite", e.p["lignes"]


def test_etat_final_rouge_si_article_en_trop():
    """T5 : l'état final attendu compare l'ENSEMBLE des articles (avant : chaque article attendu cherché par sous-chaîne, le reste du panier jamais regardé : un article en double ou inventé passait)."""
    from types import SimpleNamespace

    from api.services.builder.tests_agent.verdict import _ecarts_de_l_etat_final

    fiche = {"commande_panier": {"lignes": [{"nom": "Regina Normale", "quantite": 1}, {"nom": "Coca-Cola", "quantite": 1}], "enregistree": {"numero": "x"}, "mode": "emporter"}}
    critere = {"connecteur": "commande", "attendu": {"enregistree": True, "articles": {"Regina": 1}}}
    ecarts = _ecarts_de_l_etat_final(critere, SimpleNamespace(fiche=fiche))
    assert any("coca" in e.casefold() for e in ecarts), ecarts  # un article en trop
    juste = {"commande_panier": {**fiche["commande_panier"], "lignes": [{"nom": "Regina Normale", "quantite": 1}]}}
    assert _ecarts_de_l_etat_final(critere, SimpleNamespace(fiche=juste)) == []
    double = {"commande_panier": {**fiche["commande_panier"], "lignes": [{"nom": "Regina Normale", "quantite": 1}, {"nom": "Regina Mega", "quantite": 1}]}}
    assert _ecarts_de_l_etat_final(critere, SimpleNamespace(fiche=double)), "deux Regina pour une attendue"


def test_reglage_conduite_par_l_agent_supprime():
    """V10 : le réglage ``commande_conduite_par_l_agent`` n'était lu nulle part depuis le lot 4 : supprimé du schéma, des réglages du module, du gabarit et des réglages du moteur (Evan, 20/11)."""
    import dataclasses
    import json

    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
    from api.services.commande.moteur import Reglages
    from api.services.gabarits import gabarit as G

    assert "commande_conduite_par_l_agent" not in WorkflowConfigurationDefaults.model_fields
    assert "conduite_par_l_agent" not in {f.name for f in dataclasses.fields(Reglages)}
    assert "commande_conduite_par_l_agent" not in json.dumps(G.charger().reglages["modele"])


async def test_kit_envois_vise_le_sms_du_service(db_session):
    """V5 : le kit « Envois » vise ``service.envoyer_un_sms`` (avant : ``commande.envoyer_un_message``, retiré au lot 2 : kit vide sur une base neuve) ; un outil déjà posé dont l'action n'existe plus est
    purgé du kit (avant : ``poser_un_kit_livre`` n'enlevait rien, les kits gardaient leurs anciennes actions)."""
    from sqlalchemy import text

    from api.services.outils_mark import kits_livres

    async def outils_du_kit(nom: str) -> set[str]:
        # lu en SQL : la session de test garde ses objets en mémoire, ``lister_les_kits`` y relirait un kit périmé
        async with db_session.async_session() as session:
            lignes = await session.execute(text("SELECT i.name FROM tool_kit_items i JOIN tool_kits k ON k.id = i.kit_id WHERE k.name = :n"), {"n": nom})
            return {r[0] for r in lignes}

    mort = {"name": "envoyer_un_message", "category": "integration",
            "definition": {"schema_version": 1, "type": "integration", "config": {"connecteur": "commande", "action": "envoyer_un_message"}}}
    await db_session.poser_un_kit_livre("Commande", "ancien", [mort])  # une base d'avant : le kit porte un outil mort
    assert await outils_du_kit("Commande") == {"envoyer_un_message"}
    bilan = await kits_livres.poser_les_kits_livres()
    assert bilan["Commande"]["outils_retires"] == 1, bilan
    assert await outils_du_kit("Envois") == {"envoyer_un_sms"}
    assert await outils_du_kit("Commande") == {"fiche", "lire"}
    second = await kits_livres.poser_les_kits_livres()
    assert all(v["outils_ajoutes"] == 0 and v["outils_retires"] == 0 for v in second.values())  # rejouable


def test_outil_d_action_inconnue_signale():
    """V5 : un outil dont l'action n'existe pas est signalé (journal en erreur, aucun schéma rendu au modèle) ; ``outil_mort`` le dit pour les kits."""
    from types import SimpleNamespace

    from loguru import logger

    from api.services.integrations.connectors import outil
    from api.services.outils_mark import kits_livres

    definition = {"config": {"connecteur": "commande", "action": "envoyer_un_message"}}
    messages: list[str] = []
    identifiant = logger.add(lambda m: messages.append(str(m)), level="ERROR")
    try:
        assert outil.schema(SimpleNamespace(name="envoyer_un_message", description="d", definition=definition), "envoyer_un_message") is None
    finally:
        logger.remove(identifiant)
    assert any("unknown action" in m and "envoyer_un_message" in m for m in messages), messages
    assert kits_livres.outil_mort(definition) is True
    assert kits_livres.outil_mort({"config": {"connecteur": "commande", "action": "fiche"}}) is False


def test_relecture_des_habitudes_retiree():
    """V9 : la relecture des habitudes d'un client connu est RETIRÉE (Evan, 20/11 : rien ne change à l'écoute) : ``reconnaitre_le_client`` n'existe plus, ni son test."""
    from api.services.commande import moteur

    assert not hasattr(moteur, "reconnaitre_le_client")
