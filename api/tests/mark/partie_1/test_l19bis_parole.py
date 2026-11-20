"""[.mark] Chantier Partie 1, lot 19 bis, étape B : les petits correctifs de l'audit de Pierre (notes du 20/11), un test vu rouge chacun.

Allergie (A1, A3, A4), commande (C1 à C8), parole (P1 à P8), tours (T1 à T5), preuves (V1 à V10). Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait  # noqa: F401


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
    from api.services.restauration.signalements import codes_dits, code_dit

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
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            return q
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p.get("question") or {}
    assert q.get("type") == "relecture", e.retours[-1]
    return q


async def test_panier_change_apres_l_accord_relu_avant_enregistrement(essai_de):
    """C1 : relecture acceptée, puis un article ajouté : l'accord ne vaut plus (source : ``panier.toucher`` ne remettait pas ``relecture_acceptee`` à faux) ; la nouvelle
    relecture est posée et la commande n'est pas enregistrée avec l'article jamais annoncé."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    assert e.p.get("relecture_acceptee")
    await e.tour("rajoutez un autre gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 2}])
    assert not e.p.get("relecture_acceptee"), "l'accord de la relecture ne vaut plus : le panier a changé"
    await e.tour("non c'est tout", c_est_tout=True)
    q = e.p.get("question") or {}
    assert q.get("type") == "relecture" and not e.p.get("enregistree"), (q, e.retours[-1])


async def _jusqu_a_l_enregistrement(e) -> None:
    """Le numéro (dicté) puis le prénom, tant que la commande n'est pas enregistrée."""
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")


async def test_billet_puis_carte_enregistre(essai_de):
    """C3 : « un billet de cinquante » puis « finalement par carte » : le billet est effacé avec le moyen espèces (source : ``fin_dite.rendu_sur`` repartait à chaque fiche), la commande s'enregistre."""
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, en espèces, un billet de cinquante", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="especes", rendu_sur=50)
    r = await e.tour("finalement par carte", moyen_de_paiement="carte_bancaire")
    assert "Sur quel règlement le billet" not in fait(r), r
    assert not (e.p.get("fin_dite") or {}).get("rendu_sur") and not (e.p.get("paiement") or {}).get("rendu_sur")
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


async def _accueil(essai_de, monkeypatch, nom, arguments):
    from types import SimpleNamespace

    from api.services.commande import porte

    e = await essai_de("casa-italia")
    return e, await porte.executer(SimpleNamespace(nom=nom), arguments, e.ctx, 5.0)


