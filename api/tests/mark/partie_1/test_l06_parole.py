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
    assert R.refuse({"statut": "PARTIEL", "raison": "hors_zone"})


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


def test_prix_dit_apres_la_phrase_du_modele():
    """L06-29 (D33, T3) : une proposition née dans ce tour : le modèle la pose sans chiffre, le code dit le prix juste après sa phrase, une fois."""
    etat = PAROLE.EtatDuTour(tour=3)
    p = {"question": {"id": "Q-1", "type": "proposition", "nee_au_tour": 3}}
    d = PAROLE.parole_du_tour({"statut": "FAIT", "prix_dit_par_le_code_apres_ta_phrase": True}, "Je vous ajoute un Coca ?", etat, [], p, {},
                              {"suffixe": "Il est à deux euros."})
    assert d.mode == PAROLE.SECOND_PASSAGE and etat.suffixe == "Il est à deux euros."
    assert PAROLE.avec_le_suffixe("Avec ça, un Coca-Cola bien frais ?", etat) == "Avec ça, un Coca-Cola bien frais ? Il est à deux euros."
    assert PAROLE.avec_le_suffixe("Autre chose ?", etat) is None  # dit une fois


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
