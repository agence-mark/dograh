"""[.mark] Chantier Partie 1, lot 6 : la couche de parole à la version finale de B12 (repli A seul, D62 ; accueil sans la carte, B13 point 2).

Les essais de la parole se jouent sans modèle : les retours de la vraie porte (montage ``porte_essai.py``) et des phrases écrites d'après les
bancs B10 à B12 (cas cités par leur nom). Aucun test n'appelle un fournisseur (garde du lot 0).
"""

from __future__ import annotations

import re
from pathlib import Path

from api.services.actions_communes import barriere_des_chiffres as BC
from api.services.actions_communes import repli as R
from api.services.commande import porte as PORTE
from api.services.commande.note import composer_la_note_de_commande

API = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- la barrière des chiffres (L06-24, L06-25, L06-30, L06-40)


def test_chiffre_retenu_dans_une_phrase_libre():
    """L06-24 (B11 point 4) : une phrase libre avec un chiffre est retenue ; les mots du code de remise de la fiche ne sont pas un chiffre (B10)."""
    assert BC.chiffre_dans_la_phrase("Ça fera douze euros cinquante.", [], ["une reine"])
    assert BC.chiffre_dans_la_phrase("Votre commande sera prête dans 20 minutes.", [], ["à emporter"])
    assert not BC.chiffre_dans_la_phrase("C'est noté. Vous voulez autre chose ?", [], ["une reine"])
    assert not BC.chiffre_dans_la_phrase("J'ai bien noté le code VINGT.", [{"code_de_remise": "vingt"}], ["j'ai le code vingt"])
    assert "Les chiffres sont dits par le code" in BC.RAPPEL_DU_CHIFFRE


def test_valeur_dite_exemptee():
    """L06-25 (B12) : une valeur qu'elle a dite n'arrête pas la phrase ; l'argent seulement s'il a été dit en argent."""
    assert not BC.chiffre_dans_la_phrase("Vous payez en espèces avec un billet de cinquante euros.", [], ["en espèces avec un billet de cinquante"])
    assert not BC.chiffre_dans_la_phrase("Je note pour 20 heures.", [], ["vers vingt heures"])


def test_quantite_dite_ne_couvre_pas_un_prix():
    """L06-25 (B12) : « deux reines » ne couvre jamais « deux euros » ; « une table pour quatre » ne couvre pas « 6 personnes »."""
    assert BC.chiffre_dans_la_phrase("Un Coca-Cola à deux euros ?", [], ["deux reines normales"])
    assert BC.chiffre_dans_la_phrase("Pour 6 personnes, c'est noté.", [], ["une table pour quatre"])


def test_sans_balisage():
    """L06-30 (B10 point 4) : balises, astérisques et retours à la ligne retirés de toute phrase dite."""
    assert BC.sans_balisage("**C'est noté.**\nAutre <break time='1s'/> chose ?") == "C'est noté. Autre chose ?"


def test_une_seule_fonction_elle_l_a_dit():
    """L06-40 (D57) : la barrière des cases et la barrière des chiffres appellent ``forme.valeur_dite_par_elle`` ; aucune autre fonction de ce sens
    dans ``api/services/``, et le nom ``dans_ses_mots`` n'y existe pas."""
    services = API / "services"
    definitions = []
    for f in services.rglob("*.py"):
        texte = f.read_text(encoding="utf-8", errors="ignore")
        assert not re.search(r"(?<!\w)dans_ses_mots\s*\(", texte), f  # la fonction du banc ; la raison ``valeur_pas_dans_ses_mots`` (lot 2) reste
        definitions += [(f.name, m) for m in re.findall(r"def (\w*dite?_par_elle\w*|\w*dit_par_elle\w*)\(", texte)]
    assert definitions == [("forme.py", "valeur_dite_par_elle")], definitions
    for nom in ("barrieres.py", "barriere_des_chiffres.py"):
        assert "valeur_dite_par_elle" in (services / "actions_communes" / nom).read_text(encoding="utf-8"), nom


# --------------------------------------------------------------------------- le repli A (L06-26 à L06-28)


def test_refus_de_la_fiche_et_du_metier():
    """L06-26, L06-27 : une raison rangée « fiche » est un refus de la fiche ; une raison du métier (hors zone) ne l'est pas."""
    assert R.refus_de_la_fiche({"statut": "REJETEE", "raison": "valeur_pas_dans_ses_mots", "refus": [{"raison": "valeur_pas_dans_ses_mots"}]})
    assert not R.refus_de_la_fiche({"statut": "PARTIEL", "raison": "hors_zone", "refus": [{"raison": "hors_zone"}]})
    hors_zone = {"statut": "PARTIEL", "faits": {"fait_bloquant": {"statut_du_module": "HORS_ZONE", "manque": None}}}
    assert R.refuse(hors_zone) and not R.refus_de_la_fiche(hors_zone)
    # un manque (le numéro, le prénom) ou une proposition (``a_faire``) ne refusent rien : le modèle demande la suite (banc : ``i["refus"]``)
    assert not R.refuse({"statut": "PARTIEL", "faits": {"fait_bloquant": {"statut_du_module": "INCOMPLETE", "manque": "prenom"}}})
    assert not R.refuse({"statut": "FAIT", "a_faire": "propose-lui Coca-Cola en une question"})


def test_repli_question_en_attente():
    """L06-28 : au bout des passes, le code dit la question en attente par sa phrase (conv3 t2, mot pour mot)."""
    relecture = ("Je vous relis : une Margherita Mega et une Margherita Normale, à emporter. Cela fait vingt-sept euros quatre-vingts. "
                 "C'est bon ?")
    assert R.repli_dit_par_le_code({"question": {"id": "Q-2", "type": "relecture", "texte": relecture}, "lignes": []}) == relecture
    proposition = "Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ?"
    assert R.repli_dit_par_le_code({"question": {"id": "Q-1", "type": "proposition", "texte": "proposer Coca-Cola", "repli": proposition}}) == proposition


async def test_repli_phrase_du_manque(essai_de):
    """L06-28 (f307 t2) : sous le minimum, sans question en attente, le repli est la phrase du manque du module."""
    e = await essai_de("casa-italia", minimum=5000)
    await e.tour("en livraison au 9 avenue du Bouteiller à Chantilly", mode_de_retrait="livraison", commune="Chantilly", adresse="9 avenue du Bouteiller")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    assert e.p.get("question") is None, e.p.get("question")
    assert R.repli_dit_par_le_code(e.p) == "Je vous mets autre chose ?", R.repli_dit_par_le_code(e.p)


# --------------------------------------------------------------------------- la note composée (L06-07)


def test_allergie_jamais_perdue_regle():
    """L06-07 (E22, n8), la règle : l'allergie du greffier et la note du modèle sont toutes deux dans la note, rien n'est écrasé."""
    note = composer_la_note_de_commande([{"texte": "bien cuite"}], {"allergie": "arachides", "consigne_livreur": "aucune"})
    assert note == "bien cuite ; Allergie : arachides"
    assert composer_la_note_de_commande([{"texte": "allergie aux arachides"}], {"allergie": "arachides"}) == "allergie aux arachides"


async def test_allergie_jamais_perdue(essai_de):
    """L06-07 (E22, n8) : allergie notée par le greffier plus note du modèle : les deux dans la note envoyée avec la commande."""
    e = await essai_de("casa-italia")
    e.fiche_de_l_appel["allergie"] = "arachides"
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale bien cuite", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}],
                 note_generale="bien cuite")
    for _ in range(3):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p["question"]
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")
    assert e.p.get("enregistree"), e.retours[-1]
    note = await e.monde.c.fetchval("SELECT note FROM mark.resto_commande WHERE site_id = $1", e.monde.a)
    assert "bien cuite" in (note or "") and "Allergie : arachides" in (note or ""), note


# --------------------------------------------------------------------------- la boucle du tour (L06-01, L06-03, L06-21, L06-23, L06-26, L06-27, L06-33)

from types import SimpleNamespace  # noqa: E402

from api.services.actions_communes import parole as PAROLE  # noqa: E402
from api.services.workflow import parole_de_la_fiche as PF  # noqa: E402
from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES  # noqa: E402


def _verificateur(e) -> PF.VerificateurDeLaFiche:
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))


async def _jusqu_au_second_article(e):
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    e.dit("et une regina normale")
    e.montrer()
    return await e.fiche(ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}], _montrer=False)


async def test_a_dire_un_passage(essai_de):
    """L06-01 : retour ``FAIT`` sans refus ni fait bloquant, phrase sans chiffre : ``a_dire`` est dite en un passage."""
    e = await essai_de("casa-italia")
    r = await _jusqu_au_second_article(e)
    assert r["statut"] == "FAIT", r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté, une Regina. Autre chose ?"})
    assert (d.mode, d.a_dire) == (PAROLE.A_DIRE_SEUL, "C'est noté, une Regina. Autre chose ?"), d


async def test_introuvable_a_dire_jetee(essai_de):
    """L06-03 : « pizza au caviar » : le retour refuse ou ne trouve pas, ``a_dire`` est jetée, le modèle reformule avec le retour."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une pizza au caviar", ajouter=[{"article": "pizza au caviar", "quantite": 1}])
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté, une pizza au caviar."})
    assert d.mode == PAROLE.SECOND_PASSAGE, (d, r)


async def test_minimum_dit_par_le_code_puis_modele(essai_de):
    """L06-02 (B7, 6/6) : un fait bloquant jette ``a_dire`` (le modèle repasse avec le retour, sans chiffre)."""
    e = await essai_de("casa-italia", minimum=5000)
    await e.tour("en livraison au 9 avenue du Bouteiller à Chantilly", mode_de_retrait="livraison", commune="Chantilly", adresse="9 avenue du Bouteiller")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r = await e.tour("c'est tout", c_est_tout=True)
    textes = dict(e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Parfait, je vous relis."})
    assert d.mode == PAROLE.SECOND_PASSAGE, (d, r)
    # le code dit le minimum mot pour mot (bloquants_commande du banc), le retour ne porte que le drapeau
    assert d.prefixe == "En livraison à Chantilly, le minimum de commande est de cinquante euros : il manque trente-neuf euros dix.", d
    assert textes.get("prefixe") == d.prefixe and r.get("dit_avant_ta_phrase") is True and "minimum" not in str(r.get("texte_a_dire") or "")
    assert r["a_faire"].startswith(PORTE.A_FAIRE_DU_MINIMUM), r


async def test_recapitulatif_dit_par_le_code(essai_de):
    """L06-01 (b) (K4 du banc) : le récapitulatif est dit par le code, mot pour mot ; la phrase du modèle est jetée et le tour s'arrête."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r = await e.tour("c'est tout", c_est_tout=True)
    recap = (e.p.get("question") or {}).get("texte")
    assert (e.p.get("question") or {}).get("type") == "relecture" and recap, r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Parfait, je vous relis la commande."})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == PAROLE.sans_balisage(recap), d


def test_prix_dit_apres_la_question_du_modele():
    """L06-29 (D33, T3) : une proposition née dans ce tour : le modèle la pose sans chiffre, le code dit le prix juste après sa phrase, une fois."""
    etat = PAROLE.EtatDuTour(tour=3)
    p = {"question": {"id": "Q-1", "type": "proposition", "nee_au_tour": 3}}
    d = PAROLE.parole_du_tour({"statut": "FAIT", "prix_dit_par_le_code_apres_ta_phrase": True}, "Je vous ajoute un Coca ?", etat, [], p, {},
                              {"suffixe": "Il est à deux euros."})
    assert d.mode == PAROLE.SECOND_PASSAGE and etat.suffixe == "Il est à deux euros."
    assert PAROLE.avec_le_suffixe("Avec ça, un Coca-Cola bien frais ?", etat) == "Avec ça, un Coca-Cola bien frais ? Il est à deux euros."
    assert PAROLE.avec_le_suffixe("Autre chose ?", etat) is None  # dit une fois
    # passe vide après la naissance de la proposition : le code dit la proposition de B8 (repli E-b)
    b8 = "Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ?"
    assert R.repli_dit_par_le_code({"question": {"id": "Q-1", "type": "proposition", "texte": "x", "repli": b8}}) == b8


async def test_parole_sans_fiche_rejouee(essai_de):
    """L06-21 (B8, A) : un tour sans outil, objet en cours : la phrase est retenue avec son rappel, une fois par tour."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    e.dit("une margherita")
    e.montrer()
    v = _verificateur(e)
    retenue = v.controler("Très bien, je vous mets une margherita.")
    assert retenue is not None and retenue.raison == PAROLE.SANS_OUTIL and retenue.consigne == PAROLE.RAPPEL_SANS_OUTIL, retenue
    assert v.controler("Très bien, je vous mets une margherita.") is None  # une fois par tour


async def test_rattrapage_une_fois_par_tour(essai_de):
    """L06-23 (B11 point 5) : le rattrapage après un refus joue une fois, tenu par le drapeau ; une passe vide retenue ne le rouvre pas."""
    e = await essai_de("casa-italia")
    await e.tour("en livraison au 8 rue Solférino à Compiègne", mode_de_retrait="livraison", commune="Compiègne", adresse="8 rue Solférino")
    r = e.retours[-1]
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "D'accord."})
    v = _verificateur(e)
    premiere = v.controler("")
    assert premiere is not None and premiere.raison == PAROLE.APRES_REFUS, (premiere, r)
    assert PAROLE.etat_du_tour(e.fiche_de_l_appel).rattrapage_refus_joue
    assert v.controler("Nous ne livrons pas Compiègne, je peux vous proposer à emporter.") is None  # refus du métier : la phrase reste dite


async def test_pas_de_phrase_sans_outil_apres_refus_de_la_fiche(essai_de):
    """L06-26 (B12) : après un refus de LA FICHE, aucune phrase sans outil n'est dite : retenue, puis la relance fautive est remplacée par le repli."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    e.dit("une margherita mega")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "margherita", "quantite": 1, "variante": "Mega"}], prenom="Léa", _montrer=False)
    assert PAROLE.refus_de_la_fiche(r), r
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    v = _verificateur(e)
    assert v.controler("Je remplace tout de suite.").raison == PAROLE.APRES_REFUS
    relance = v.controler_la_relance("C'est fait, je remplace.")
    assert relance is not None and relance.raison == PAROLE.REPLI_A and relance.a_dire, relance


async def test_refus_du_metier_phrase_gardee(essai_de):
    """L06-27 (B12, preuve 1d') : après un refus du métier (hors zone), la phrase du modèle qui le dit est dite (après le rattrapage du tour)."""
    e = await essai_de("casa-italia")
    r = await e.tour("en livraison au 8 rue Solférino à Compiègne", mode_de_retrait="livraison", commune="Compiègne", adresse="8 rue Solférino")
    assert not PAROLE.refus_de_la_fiche(r), r
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "D'accord."})
    v = _verificateur(e)
    v.controler("")
    assert v.controler_la_relance("Nous ne livrons pas Compiègne. Voulez-vous la commander à emporter ?") is None


async def test_repli_sur_phrase_vide(essai_de):
    """L06-33 (n4 rép. 2) : une passe vide dite par le modèle après un refus de la fiche déclenche le repli du code ; aucun tour muet."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    e.dit("oui")
    e.montrer()
    r = await e.fiche(reponse={"question_id": "Q-99", "sens": "accepte"}, _montrer=False)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ""})
    v = _verificateur(e)
    v.controler("")
    relance = v.controler_la_relance("")
    assert relance is not None and relance.a_dire, (relance, r)


def test_porte_la_fiche():
    assert PF.porte_la_fiche({CLE_DES_CASES_MONTREES: {"fiche": ["ajouter"]}})
    assert not PF.porte_la_fiche({CLE_DES_CASES_MONTREES: {"lire": []}})


# --------------------------------------------------------------------------- le tour borné (L06-39, D51)


async def test_tour_borne_sur_429():
    """L06-39 (D51) : un 429 du fournisseur (réponse enregistrée, aucun appel réel) : une nouvelle tentative au plus, puis l'erreur, jamais d'attente
    sans fin ; le cerveau de la fabrique porte la borne."""
    import httpx
    import openai

    from api.services.pipecat.borne_du_tour import DELAI_D_UNE_PASSE_S, borner_le_cerveau

    vues = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        vues.append(requete.url.path)
        return httpx.Response(429, json={"error": {"message": "rate limited", "type": "rate_limit"}}, headers={"retry-after": "0"})

    client = openai.AsyncOpenAI(api_key="essai", base_url="http://fournisseur.essai/v1", http_client=httpx.AsyncClient(transport=httpx.MockTransport(repondre)))
    service = borner_le_cerveau(SimpleNamespace(_client=client))
    assert service._client.max_retries == 1 and service._client.timeout == DELAI_D_UNE_PASSE_S
    import pytest

    with pytest.raises(openai.RateLimitError):
        await service._client.chat.completions.create(model="gemma", messages=[{"role": "user", "content": "bonjour"}])
    assert len(vues) == 2, vues  # la requête, puis UNE nouvelle tentative


# --------------------------------------------------------------------------- l'issue posée par l'opération (L06-14, L06-15)


async def test_issue_posee_par_enregistrer(essai_de):
    """L06-14 (C10, 2678) : ``commande_enregistree`` est posée à l'enregistrement, par l'opération, jamais devinée."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    assert "call_disposition" not in e.fiche_de_l_appel
    for _ in range(3):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p["question"]
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    for dit, cases in (("zéro six douze trente-quatre cinquante-six soixante-dix-huit", {"telephone": "0612345678"}), ("Léa", {"prenom": "Léa"})):
        if not e.p.get("enregistree"):
            await e.tour(dit, **cases)
    assert e.p.get("enregistree") and e.fiche_de_l_appel.get("call_disposition") == "commande_enregistree", e.fiche_de_l_appel.get("call_disposition")


async def test_issue_annulee_et_abandonnee(essai_de):
    """L06-15 : ``commande_annulee`` posée par l'annulation de la commande en cours (2677 : plus jamais « end_call »)."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p.get("question") or {}
    reponse = {"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}  # « obligatoire tant qu'une question attend » (contrat, lot 2)
    await e.tour("non, laissez tomber, j'annule", annuler_la_commande=True, **reponse)
    assert e.fiche_de_l_appel.get("call_disposition") == "commande_annulee", (e.fiche_de_l_appel.get("call_disposition"), e.retours[-1])
    assert PORTE.issue_de_fin_d_appel(e.fiche_de_l_appel) is None  # une issue est posée : la fin de l'appel n'y touche pas
    # l'appel finit avec une commande commencée, ni enregistrée ni annulée : « abandonnée », posée à la fin (2678)
    from api.services.commande import panier as P

    ouverte = P.nouveau()
    ouverte.update(mode="emporter", lignes=[{"n": 1, "quantite": 1, "nom": "Margherita"}])
    fin = {P.CLE: ouverte}
    assert PORTE.issue_de_fin_d_appel(fin) == "commande_abandonnee"
    fin[PORTE.CLE_ISSUES_REGLEES] = {"commande_abandonnee": "Abandon"}
    assert PORTE.issue_de_fin_d_appel(fin) == "Abandon"
    assert PORTE.issue_de_fin_d_appel({P.CLE: {**ouverte, "enregistree": {"numero": "C1"}}}) is None


def test_messages_au_modele_en_francais():
    """L06-13 (Q02) : les messages rendus au modèle par le passage à un collègue sont en français (E27)."""
    texte = (API / "services" / "workflow" / "pipecat_engine_custom_tools.py").read_text(encoding="utf-8")
    debut = texte.index("Passer la main à un collègue")
    zone = texte[debut - 2500: debut + 6000]
    for anglais in ("Continue helping the caller", "Transferring to another agent", "A transfer is already under way", "Connecting the caller now"):
        assert anglais not in zone, anglais
    assert "La personne est passée à ton collègue." in zone


# --------------------------------------------------------------------------- les phrases d'attente (L06-17 à L06-19, D24)

from api.services.outils_mark import attente_par_case as AT  # noqa: E402
from api.services.outils_mark import variantes_d_attente as VA  # noqa: E402


def test_attente_par_case():
    """L06-17 : la lecture de la carte prend une phrase de sa famille ; l'adresse, la sienne ; une case sans famille garde la phrase de l'outil."""
    assert AT.config_avec_l_attente({}, "lire", {"sujet": "carte"})["phrases_attente"] == AT.familles()[AT.LECTURE]
    assert AT.config_avec_l_attente({}, "fiche", {"adresse": "8 rue Solférino", "commune": "Compiègne"})["phrases_attente"] == AT.familles()[AT.ZONE]
    assert AT.config_avec_l_attente({}, "fiche", {"c_est_tout": True})["phrases_attente"] == AT.familles()[AT.ENREGISTREMENT]
    assert AT.config_avec_l_attente({"phrase_attente": "Un instant."}, "fiche", {"ajouter": [{"article": "x"}]}) == {"phrase_attente": "Un instant."}


def test_attente_n_annonce_aucun_resultat():
    """L06-18 : aucune variante ne porte un chiffre ni un résultat (« c'est noté », « c'est fait », « il y a »)."""
    interdit = re.compile(r"\d|c'est not[ée]|c'est fait|il y a|enregistr", re.I)
    for famille, variantes in AT.familles().items():
        for v in variantes:
            assert not interdit.search(v) and not BC.a_un_chiffre(v), (famille, v)


def test_attente_une_par_tour_sans_repetition():
    """L06-19 : jamais deux fois la même variante dans l'appel (mécanisme existant ``variantes_d_attente.choisir``)."""
    moteur = SimpleNamespace()
    config = AT.config_avec_l_attente({}, "lire", {})
    dites = [VA.choisir(moteur, config) for _ in range(len(AT.familles()[AT.LECTURE]) + 1)]
    assert dites[-1] is None and len(set(dites[:-1])) == len(dites) - 1, dites


# --------------------------------------------------------------------------- l'état injecté sans ambiguïté (L06-10, L06-11)


def test_sans_consigne_des_suggestions():
    """L06-10 (G05) : la phrase « sont des suggestions » n'existe plus dans ce que lit le modèle."""
    for f in (API / "services").rglob("*.py"):
        texte = f.read_text(encoding="utf-8", errors="ignore")
        assert "écrites par le code sont des suggestions" not in texte, f
        assert "CONSIGNE_DES_SUGGESTIONS =" not in texte, f


def test_dit_avant_toi_une_fois():
    """L06-11 (G06) : « tout ce qui a été dit compte » n'est plus écrit ; la phrase réécrite est écrite une fois."""
    from api.services.groupe.notes import CONSIGNE_ALLER

    trouvees = [f.name for f in (API / "services").rglob("*.py") if "tout ce qui a été dit compte" in f.read_text(encoding="utf-8", errors="ignore")]
    assert trouvees == [], trouvees
    assert CONSIGNE_ALLER.count("Ce qui a été dit avant toi se prend une fois, par l'outil") == 1


# --------------------------------------------------------------------------- passer_a sur le vrai moteur (L06-43, étape 6.11)


def _passages_de_la_version_finale():
    """Les trois outils de passage de l'accueil, la description de chaque cible prise dans le rendu de la version finale."""
    from types import SimpleNamespace

    from api.services.gabarits.restauration import textes as T

    banc = next(o["function"] for o in T.outils_de_l_accueil() if o["function"]["name"] == "passer_a")
    corps = banc["description"].split(" cible ")[1:]
    outils = []
    for morceau in corps:
        cible, texte = morceau.split(" : ", 1)
        outils.append(SimpleNamespace(name=f"passer_a_l_agent_{cible}", description=texte, category="transfer_agent",
                                      definition={"type": "transfer_agent", "config": {"workflow_id": 300}}, tool_uuid=cible))
    return banc, outils


def test_passer_a_egal_a_la_version_finale():
    """L06-43 : l'outil unique rendu par le moteur est, mot pour mot, celui de la version finale (B8 point 2, B13 point 2)."""
    from api.services.workflow import passage_unique as PU

    banc, outils = _passages_de_la_version_finale()
    assert PU.schema(outils)["function"] == banc
    assert PU.outil_de_la_cible(outils, {"cible": "service", "demande": "x"}) is outils[2]
    assert PU.outil_de_la_cible(outils, {"cible": "livraison"}) is None
    assert not PU.actif({}) and PU.actif({"passage_unique": True})  # éteint par défaut


async def test_passer_a_en_tete_sur_le_moteur(monkeypatch):
    """L06-43 : réglage allumé, le moteur montre ``passer_a`` en tête à la place des passages, et l'appel va au passage de la cible ;
    éteint, l'étape garde ses outils à l'octet."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api.services.workflow import pipecat_engine_custom_tools as CT

    _, passages = _passages_de_la_version_finale()
    lecture = SimpleNamespace(name="infos_pratiques", description="Lit une information pratique.", category="http_api", tool_uuid="i",
                              definition={"type": "http_api", "config": {"url": "https://exemple.invalid", "method": "GET"}})
    outils = [passages[0], lecture, passages[1], passages[2]]
    inscrits = {}
    llm = SimpleNamespace(register_function=lambda nom, f, **k: inscrits.__setitem__(nom, f))
    agent = SimpleNamespace(llm=llm, reglages={"passage_unique": True}, workflow=None, bind_tool=lambda e, h, **k: h)
    engine = SimpleNamespace(_get_organization_id=AsyncMock(return_value=1), active_agent=agent)
    m = CT.CustomToolManager(engine, agent)
    monkeypatch.setattr(m, "_lire_outils", AsyncMock(return_value=outils))
    appels = []

    def gestionnaire(tool, nom):
        async def h(params):
            appels.append(tool.name)
        return h

    monkeypatch.setattr(m, "_create_transfer_agent_handler", gestionnaire)
    noms = [s.name for s in await m.get_tool_schemas(["x"])]
    assert noms[0] == "passer_a" and not any(n.startswith("passer_a_l_agent_") for n in noms), noms
    await m.register_handlers(["x"])
    assert "passer_a" in inscrits and not any(n.startswith("passer_a_l_agent_") for n in inscrits), list(inscrits)
    rendu = []
    await inscrits["passer_a"](SimpleNamespace(arguments={"cible": "reservation", "demande": "une table"}, result_callback=AsyncMock()))
    assert appels == ["passer_a_l_agent_reservation"]
    params = SimpleNamespace(arguments={"cible": "livraison"}, result_callback=AsyncMock(side_effect=lambda r, **k: rendu.append(r)))
    await inscrits["passer_a"](params)
    assert rendu and rendu[0]["reason"] == "cible_inconnue" and appels == ["passer_a_l_agent_reservation"]
    agent.reglages = {}
    noms = [s.name for s in await m.get_tool_schemas(["x"])]
    assert "passer_a" not in noms and sum(n.startswith("passer_a_l_agent_") for n in noms) == 3, noms


# --------------------------------------------------------------------------- la fiche du service (sens des anciens tests du connecteur ``service``)


async def test_service_message_une_fois_issue_et_mesure():
    """L06-14 (C10), sens repris de ``test_restauration_service_client`` (urgence, une demande par appel), ``test_message_et_redites_m102_m113``
    (l'issue posée et réservée) : le message laissé par la fiche du service, normal par défaut, une fois par appel, avec l'issue et sa mesure.
    ``test_message_titre_pas_un_prenom_m122`` n'a plus d'objet : la fiche du service ne prend pas de prénom (version finale, B12)."""
    from types import SimpleNamespace

    from api.services.apres_appel import rappels
    from api.services.integrations.connectors import mesures
    from api.services.workflow.issue_reservee import codes_reserves

    ctx = SimpleNamespace(fiche={}, appel={"caller_number": "+33612345678"}, reglages={"issues": {"message_a_transmettre": "Message_Transmis"}},
                          run_id=None, organization_id=1, configurations={})
    r = await PORTE.executer_la_fiche_du_service({"laisser_un_message": {"objet": "Rappeler pour la privatisation"}, "a_dire": "C'est noté."}, ctx)
    assert r["statut"] == "FAIT" and r["resultats"][0]["faits"] == {"urgent": False}, r
    entree = ctx.fiche[rappels.CLE_RAPPEL][0]
    assert (entree["urgence"], entree["numero"], entree["objet"]) == ("normale", "+33612345678", "Rappeler pour la privatisation")
    assert ctx.fiche["call_disposition"] == "Message_Transmis" and mesures.compte(ctx.fiche).get("service.message_laisse") == 1
    deux = await PORTE.executer_la_fiche_du_service({"laisser_un_message": {"objet": "Un client attend", "urgent": True}}, ctx)
    assert deux["statut"] == "REJETEE" and deux["raison"] == "message_deja_laisse_dans_cet_appel" and len(ctx.fiche[rappels.CLE_RAPPEL]) == 1
    outil = SimpleNamespace(category="integration", definition={"config": {"connecteur": "service", "action": "fiche",
                                                                           "reglages": {"issues": {"message_a_transmettre": "Message_Transmis"}}}})
    assert codes_reserves([outil]) == {"message_transmis"}


async def test_textes_d_une_version_sans_parcours_genere(monkeypatch):
    """L06-44 (6.17) : une étape qui porte la fiche (ou des passages à cible) garde ses prompts mot pour mot : aucun bloc généré à l'enregistrement,
    et les blocs déjà écrits sont retirés ; un agent d'avant garde son parcours."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api.db import db_client
    from api.services.workflow import schema_du_parcours as SP

    definition = {"nodes": [
        {"id": "g", "type": "globalNode", "data": {"name": "Prompt général", "prompt": "Qui tu es.\n\n<parcours_genere>\nvieux\n</parcours_genere>"}},
        {"id": "c", "type": "startCall", "data": {"name": "commande", "prompt": "# Ta mission ici\nPrendre la commande.", "tool_uuids": ["f"]}},
    ], "edges": []}
    reglages = {"agent_principal_id": 299}  # un spécialiste : le parcours était toujours généré
    fiche = SimpleNamespace(tool_uuid="f", category="integration", definition={"config": {"connecteur": "commande", "action": "fiche"}})
    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=[fiche]))
    sortie = await SP.a_l_enregistrement(300, 1, definition, reglages)
    prompts = {n["id"]: n["data"]["prompt"] for n in sortie["nodes"]}
    assert prompts == {"g": "Qui tu es.", "c": "# Ta mission ici\nPrendre la commande."}, prompts
    ancien = SimpleNamespace(tool_uuid="f", category="integration", definition={"config": {"connecteur": "commande", "action": "ajouter"}})
    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=[ancien]))
    sortie = await SP.a_l_enregistrement(300, 1, definition, reglages)
    assert "<parcours_genere>" in sortie["nodes"][0]["data"]["prompt"] and "<position_generee>" in sortie["nodes"][1]["data"]["prompt"]


# --------------------------------------------------------------------------- le greffier qui propose (L06-05, L06-06)


def test_greffier_propose_jamais_obtenu():
    """L06-05 (E15, G07) : une note du greffier est montrée comme une proposition dans l'état, jamais posée dans la commande ; ce qu'il a noté
    n'est pas redemandé à la fin (appel 2631), sous les noms de la version finale."""
    from api.services.commande import etat_pour_le_modele as EM
    from api.services.commande import panier as P

    p = P.nouveau()
    fiche = {P.CLE: p, "extracted_variables": {"mode_de_retrait": "en livraison", "allergie": "arachides", "telephone": "0612345678", "motif": "commande"}}
    texte = EM.texte(fiche)
    assert "- Noté par le greffier (une proposition ; seule la fiche écrit dans la commande) : mode de retrait « en livraison » ; allergie « arachides » ; " \
           "numéro de téléphone « 0612345678 »." in texte, texte  # dans l'ordre des notes, comme le banc
    assert "- Mode de retrait : pas encore dit." in texte and p["mode"] is None and not p["client"]  # rien n'est posé
    assert "numéro de téléphone" not in EM._a_la_fin(p, fiche["extracted_variables"])
    assert EM.ligne_du_greffier({"extracted_variables": {"motif": "commande"}}) is None


def test_champs_du_greffier_sans_nom_d_outil():
    """L06-06 (Q16, D54) : aucun champ du greffier lu par le code ne porte le nom d'un outil de la version finale ; un champ qui porte le mot d'une
    case a le même sens et est déclaré au glossaire ; les noms de production (``type_de_commande``, ``mode_de_paiement``, ``numero_dicte``) ne sont
    plus lus."""
    from api.services.commande import etat_pour_le_modele as EM
    from api.services.gabarits.restauration import textes as T
    from api.services.restauration.source_commande import SourceClasseur
    from api.tests.mark.partie_1 import glossaire as GL

    outils = {o["function"]["name"] for etats in T.outils_verses()["cartes"].values() for e in etats for o in e["outils"]}
    lus = set(EM.CHAMPS_DU_GREFFIER) | set(SourceClasseur.champs_du_greffier["note"])
    assert not lus & outils, lus & outils
    cases = {n for n, (genres, _) in GL.GLOSSAIRE.items() if "case" in genres}
    assert all(c in GL.PARTAGES for c in lus & cases), lus & cases - GL.PARTAGES
    code = (API / "services" / "commande" / "etat_pour_le_modele.py").read_text(encoding="utf-8")
    for ancien in ("type_de_commande", '"mode_de_paiement"', "numero_dicte"):
        assert ancien not in code, ancien


# --------------------------------------------------------------------------- « c'est fait », repli A, accueil, première visite (L06-20, 32, 35, 31)


def test_c_est_fait_lie_au_tour():
    """L06-20 (Q06, E21) : la phrase d'une fiche refusée n'est jamais dite ; au tour suivant, une fiche réussie avant ne fonde pas une phrase
    libre qui dit « c'est fait » (objet en cours, aucune fiche dans ce tour : retenue). Lecture de l'état, jamais des mots (D1)."""
    etat = PAROLE.EtatDuTour(tour=1)
    refusee = PAROLE.parole_du_tour({"statut": "REJETEE", "raison": "format", "refus": [{"raison": "format"}]}, "C'est ajouté.", etat, [])
    assert refusee.mode == PAROLE.SECOND_PASSAGE and refusee.a_dire is None
    faite = PAROLE.parole_du_tour({"statut": "FAIT"}, "C'est noté.", PAROLE.EtatDuTour(tour=1), [])
    assert faite.mode == PAROLE.A_DIRE_SEUL
    suivant = PAROLE.EtatDuTour(tour=2)  # la personne a reparlé : l'état du tour repart de zéro
    assert PAROLE.phrase_libre_retenue("C'est fait, c'est ajouté.", suivant, objet_en_cours=True, question_en_attente=False, paroles=[]) == PAROLE.SANS_OUTIL


async def test_outil_exige_apres_refus_de_la_fiche(essai_de):
    """L06-32 (D62 : repli A seul, B13 point 1 réfuté) : après un refus de la fiche, la phrase sans outil est retenue avec son rappel, SANS outil
    forcé (aucun ``tool_choice``, aucun appel fait par le code) ; la relance encore sans outil est remplacée par la phrase du code."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    e.dit("une margherita mega")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "margherita", "quantite": 1, "variante": "Mega"}], prenom="Léa", _montrer=False)
    assert PAROLE.refus_de_la_fiche(r), r
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté."})
    v = _verificateur(e)
    retenue = v.controler("Je vous mets une margherita mega.")
    assert retenue.raison == PAROLE.APRES_REFUS and retenue.outil is None and retenue.appel_par_le_code is False and not retenue.a_dire
    assert retenue.consigne == R.RAPPEL_APRES_REFUS
    relance = v.controler_la_relance("Voilà, c'est ajouté.")
    assert relance is not None and relance.raison == PAROLE.REPLI_A and relance.outil is None and relance.a_dire


def test_accueil_voir_produit_refuse():
    """L06-35 (B12 décision 3) : l'accueil n'a pas ``voir_produit`` (rendu de la version finale, posé sur les copies par passer_aux_textes) ; un appel
    de ce nom n'est rattaché à aucun outil de l'accueil et le code le refuse en clair, rien n'est lu."""
    from api.services.gabarits.restauration import textes as T
    from api.services.workflow import nom_d_outil_abime as NA

    noms = [o["function"]["name"] for o in T.outils_de_l_accueil()]
    assert "voir_produit" not in noms
    assert NA.rattacher("voir_produit", noms) is None
    refus = NA._refus(noms)
    assert refus["status"] == "outil_inconnu" and "voir_produit" not in refus["outils"] and refus["a_dire_au_client"] == ""


def test_demande_de_passage_premiere_visite():
    """L06-31 (B9 point 2, B8 n7) : la demande de passage est remise à la première visite d'un collègue ; au retour chez un collègue déjà visité,
    elle n'est plus remontrée (sa demande est dans l'échange, ce qui est pris dans l'état)."""
    from api.services.groupe.notes import demande_a_la_premiere_visite

    une = {"passations": [{"de": 299, "vers": 300, "raison": "passer_a_l_agent_commande", "issue": "completed", "demande": "deux pizzas"}]}
    assert demande_a_la_premiere_visite("deux pizzas", {}, 300, en_cours=True) == "deux pizzas"  # première visite, passation qui arrive
    assert demande_a_la_premiere_visite("deux pizzas", une, 300, en_cours=False) == "deux pizzas"  # la même, déjà tracée (clavier)
    assert demande_a_la_premiere_visite("finir ma commande", une, 300, en_cours=True) is None  # seconde visite
    deux = {"passations": une["passations"] + [{"de": 299, "vers": 300, "raison": "passer_a_l_agent_commande", "issue": "completed"}]}
    assert demande_a_la_premiere_visite("finir ma commande", deux, 300, en_cours=False) is None
    retour = {"passations": [{"de": 300, "vers": 299, "raison": "retour", "issue": "completed"}]}
    assert demande_a_la_premiere_visite("une table", retour, 299, en_cours=True) == "une table"  # un retour n'est pas une visite


def test_portee_du_reglage_a_l_etape():
    """L06-16 (S09) : un réglage de la commande est lu chez l'agent dont l'étape porte l'outil (le collègue de la commande), plus chez le premier
    agent de l'appel ; sans réglages sur l'agent (montage à la main), ceux de l'appel, comme avant."""
    from types import SimpleNamespace

    from api.services.integrations.connectors import outil as O

    moteur = SimpleNamespace(configurations_des_modules={"commande_vente_en_plus": False, "agents_specialises": [300]})
    collegue = SimpleNamespace(_engine=moteur, _agent=SimpleNamespace(reglages={"commande_vente_en_plus": True, "agent_principal_id": 299}))
    assert O.configurations_de_l_etape(collegue)["commande_vente_en_plus"] is True
    seul = SimpleNamespace(_engine=moteur, _agent=SimpleNamespace(reglages=None))
    assert O.configurations_de_l_etape(seul) == moteur.configurations_des_modules
    code = (API / "services" / "integrations" / "connectors" / "outil.py").read_text(encoding="utf-8")
    assert "configurations=configurations_de_l_etape(manager)" in code and "configurations=_configurations_des_modules(engine)" not in code


# --------------------------------------------------------------------------- l'état injecté sans ambiguïté (L06-08, L06-09)


def _cerveau_et_fiche(fiche_de_l_appel):
    """Un faux service de conversation habillé par ``montrer_la_fiche`` : la requête bâtie montre ce que le modèle recevrait."""
    from types import SimpleNamespace

    from api.services.workflow import fiche_au_fil_de_leau as FA

    llm = SimpleNamespace(_appended_system_instructions=[], _compose_system_instruction=lambda: None)
    llm.get_chat_completions = lambda contexte: None
    llm.build_chat_completion_params = lambda params: dict(params)
    reglages = FA.ReglagesFiche.depuis({"fiche_au_fil_de_leau": True, "fiche_champs": [{"nom": "prenom", "description": "Son prénom."}]})
    assert FA.montrer_la_fiche(llm, reglages, lambda: fiche_de_l_appel)
    return llm


def test_fiche_dans_le_systeme():
    """L06-09 (G04) : sur une étape qui porte la fiche, l'état de la fiche de l'appel n'est plus glissé comme une parole de la personne ; une étape
    d'avant (sans fiche) le garde, comme avant."""
    from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": "Je m'appelle Léa."}]
    avec = {CLE_DES_CASES_MONTREES: {"fiche": ["ajouter"]}, "prenom": "Léa"}
    sans = {"prenom": "Léa"}
    for fiche, montree in ((avec, False), (sans, True)):
        llm = _cerveau_et_fiche(fiche)
        etat = llm._mark_etat_de_la_fiche(messages)
        assert (etat is not None) is montree, (fiche, etat)


def test_un_seul_bloc_ce_qui_manque():
    """L06-08 (Q17) : une requête d'une étape qui porte la fiche a un seul bloc d'état, celui du connecteur, en fin d'instruction système ; le
    bloc de la fiche de l'appel n'y est pas rangé en second."""
    from types import SimpleNamespace

    from api.services.workflow import etat_des_connecteurs as EC
    from api.services.workflow import fiche_dans_le_systeme as FS
    from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

    fiche = {CLE_DES_CASES_MONTREES: {"fiche": ["ajouter"]}, "prenom": "Léa"}
    llm = _cerveau_et_fiche(fiche)
    moteur = SimpleNamespace(active_agent=SimpleNamespace(llm=llm, reglages={FS.CLE_FICHE_DANS_LE_SYSTEME: True}), reglages_appel={},
                             _gathered_context=fiche, _call_context_vars={}, **{EC.ATTRIBUT: {"fiche": "commande"}})
    FS.placer_la_fiche(moteur, llm, [{"role": "user", "content": "Je m'appelle Léa."}])
    EC.placer_l_etat(moteur, llm, [{"type": "function", "function": {"name": "fiche"}}])
    blocs = llm._appended_system_instructions
    assert len(blocs) == 1 and blocs[0].startswith("[État de la commande, tenu par le code]"), blocs


def test_rendre_a_l_action_ouverte():
    """L06-12 (E25, C4 : 2673, 2674) : une seconde demande pendant une commande ouverte ne perd pas la commande : le retour au collègue de la
    commande est permis (plus de refus « même agent »), et l'accueil reçoit l'état de l'appel qui dit la commande commencée (la reprise est
    proposée par le texte de l'accueil repris). Commande finie : le refus d'avant reste."""
    from types import SimpleNamespace

    from api.services.commande import panier as P
    from api.services.groupe.passations import refus_de_passation, rendre_a_l_action_ouverte
    from api.services.workflow import etat_des_connecteurs as EC

    p = P.nouveau()
    p.update(mode="emporter", lignes=[{"n": 1, "quantite": 2, "nom": "Reine", "variante": "Normale"}])
    trace = [{"de": 299, "vers": 300, "raison": "passer_a_l_agent_commande", "issue": "completed"},
             {"de": 300, "vers": 299, "raison": "retour", "issue": "completed"}]
    ouverte = {P.CLE: p, "passations": trace}
    assert rendre_a_l_action_ouverte(ouverte)
    assert refus_de_passation(ouverte, {}, de=299, vers=300, raison="passer_a_l_agent_commande") is None
    finie = {P.CLE: {**p, "enregistree": {"numero": "C1", "numero_court": "12"}}, "passations": trace}
    assert not rendre_a_l_action_ouverte(finie)
    assert refus_de_passation(finie, {}, de=299, vers=300, raison="passer_a_l_agent_commande") == "meme_agent"
    moteur = SimpleNamespace(_gathered_context=ouverte)
    etat = EC.texte_de_l_etat(moteur, [{"type": "function", "function": {"name": "passer_a"}}])
    assert etat.splitlines()[0] == "[État de l'appel, tenu par le code]" and "- Commande de cet appel : commencée, pas encore enregistrée (2 × " in etat
    assert "- Réservation de cet appel : aucune." in etat, etat


# --------------------------------------------------------------------------- les phrases d'attente sur un faux flux de parole (L06-37, L06-38)


class _FluxDeParole:
    """Un faux flux de parole : une seule file (comme le transport), ce qui est dit dans l'ordre, et ce que la personne peut couper."""

    def __init__(self):
        self.dits: list[tuple[str, bool]] = []

    async def queue_text_message(self, texte, *, append_to_context=False, mute_user=False):
        self.dits.append((texte, mute_user))
        return True


async def test_attente_sans_chevauchement():
    """L06-37 (Pierre, point 2) : la réponse prête avant le seuil, aucune phrase d'attente ; prête après, la phrase d'attente est dite AVANT elle
    dans la même file et jamais après (arrêtée dès que l'outil rend)."""
    import asyncio

    from api.services.integrations.connectors.champs_requis import Patience

    config = {"phrases_attente": ["Je regarde."], "seuil_patience_ms": 20}
    rapide = _FluxDeParole()
    p = Patience(rapide, config)
    p.demarrer()
    await rapide.queue_text_message("C'est noté.")
    p.arreter()
    await asyncio.sleep(0.05)
    assert [t for t, _ in rapide.dits] == ["C'est noté."] and not p.dite
    lent = _FluxDeParole()
    p = Patience(lent, config)
    p.demarrer()
    await asyncio.sleep(0.05)  # l'outil dépasse le seuil
    p.arreter()
    await lent.queue_text_message("C'est noté.")
    await asyncio.sleep(0.05)
    assert [t for t, _ in lent.dits] == ["Je regarde.", "C'est noté."], lent.dits


async def test_attente_coupee_quand_elle_parle():
    """L06-38 (Pierre, point 2) : la phrase d'attente se coupe quand la personne parle (jamais dite muette pour elle) et n'est pas reprise (dite une
    fois)."""
    import asyncio

    from api.services.integrations.connectors.champs_requis import Patience

    flux = _FluxDeParole()
    p = Patience(flux, {"phrases_attente": ["Je regarde."], "seuil_patience_ms": 10})
    p.demarrer()
    await asyncio.sleep(0.04)
    p.arreter()
    await asyncio.sleep(0.02)
    assert flux.dits == [("Je regarde.", False)], flux.dits


# --------------------------------------------------------------------------- égalité banc et fork à la vraie boucle (L06-41, D67)

import pytest  # noqa: E402

from api.tests.mark.partie_1.egalite_b12 import CONVERSATIONS, REPONSES  # noqa: E402

# Les écarts de parole au banc dont la cause est hors de la couche de parole : chacun a sa ligne dans ``a-trancher.md``.
# Toutes viennent des TEXTES DU MODULE que le code dit mot pour mot (cuisine, lot 4 ; porte, lot 3), la couche de parole les disant au bon moment
# et par la bonne bouche (qui dit : égal au banc sur les 40 tours).
_CONFIRMATION = "confirmation de l'enregistrement : le module ajoute « Puis-je faire autre chose pour vous ? » (et « livrée », le rendu de la monnaie) au texte du banc"
_RECAP = "récapitulatif : « un Coca-Cola » au lieu de « une Coca-Cola » du banc"
_OFFRE = "vente en plus offerte : le module ne pose pas l'offre (prix dit, total sans l'offre)"
ECARTS_DE_PAROLE: dict[str, str] = {
    "conv1-livraison-refus": f"{_RECAP} ; {_CONFIRMATION}",
    "conv2-hors-zone": f"{_OFFRE} ; {_CONFIRMATION}",
    "conv3-taille": f"{_OFFRE} ; changement de ligne : « On retire Margherita Normale » au lieu de « C'est changé : Margherita Mega »",
    "conv4-allergie": _CONFIRMATION,
    "conv5-consigne": f"{_OFFRE} (total du récapitulatif) ; {_CONFIRMATION}",
    "conv6-recommencer-annuler": f"{_OFFRE} ; annulation : le module ne dit pas « Je ne l'enregistre pas. » et refuse la réponse en attente (question_inconnue)",
    "conv7-heure": f"{_OFFRE} ; {_CONFIRMATION}",
    "conv8-apres-enregistrement": _CONFIRMATION,
}


def _texte_du_modele(tour: dict) -> str:
    """La phrase du second passage du modèle au banc : le texte dit, sans ce que le code a dit avant ou après elle."""
    texte = tour.get("texte") or ""
    for bord in (tour.get("prefixe"), tour.get("suffixe")):
        if bord:
            texte = texte.replace(bord, "")
    return " ".join(texte.split())


async def phrases_de_la_conversation(e, conversation: dict) -> list[str]:
    """Joue les fiches enregistrées de B12 à la vraie porte et à la vraie boucle du tour ; rend les écarts de parole au banc (qui dit, quoi)."""
    v = _verificateur(e)
    ecarts = []
    for i, tour in enumerate(conversation["tours"]):
        e.dit(tour["dit"])
        decision, retour = None, {}
        for appel in tour["appels"]:
            if appel["nom"] != "fiche":
                continue
            retour = await e.fiche(**appel["args"])
            decision = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, appel["args"])
        if decision is not None and decision.mode == PAROLE.A_DIRE_SEUL:
            par, dit = ("code" if decision.motif == "texte_du_code" else "a_dire"), decision.a_dire
        elif tour["dit_par"] is None:
            par, dit = None, None
        else:
            libre = _texte_du_modele(tour)
            retenue = v.controler(libre)
            if retenue is None:
                par, dit = "modele", libre
            elif retenue.raison == PAROLE.SUFFIXE:
                par, dit = "modele+code", retenue.a_dire
            elif retenue.a_dire:
                par, dit = "code", retenue.a_dire
            else:
                # retenue une fois (rattrapage) : le modèle repasse ; sa relance est la phrase que le banc a dite
                seconde = v.controler_la_relance(libre)
                par, dit = ("code", seconde.a_dire) if seconde is not None and seconde.a_dire else ("modele", libre)
        if decision is not None and decision.prefixe and par in ("modele", "modele+code"):
            par, dit = "modele+code", f"{decision.prefixe} {dit or ''}".strip()  # la règle dite par le code avant la phrase du modèle
        attendu = PAROLE.sans_balisage(tour.get("texte") or "") if tour["dit_par"] in ("code", "a_dire", "modele+code") else None
        if par != tour["dit_par"] or (attendu is not None and PAROLE.sans_balisage(dit or "") != attendu):
            ecarts.append(f"{conversation['conversation']} tour {i} « {tour['dit'][:40]} » : banc {tour['dit_par']} « {(tour.get('texte') or '')} » / "
                          f"fork {par} « {(dit or '')} » [{retour.get('statut')} {retour.get('raison')}]")
    return ecarts


@pytest.mark.parametrize("nom", [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=ECARTS_DE_PAROLE[n])) if n in ECARTS_DE_PAROLE else n
                                 for n in CONVERSATIONS])
async def test_egalite_banc_et_fork(essai_de, nom):
    """L06-41 (D67) : les réponses de B12 servies à la vraie boucle donnent les mêmes phrases dites (qui les dit, et le texte quand le code ou
    ``a_dire`` le dit) que le banc, sans requête ; le panier et les refus sont égaux au lot 3 (``test_l03_porte.py``)."""
    conversation = next(c for c in REPONSES["conversations"] if c["conversation"] == nom)
    ecarts = await phrases_de_la_conversation(await essai_de(), conversation)
    assert ecarts == [], chr(10).join(ecarts)
