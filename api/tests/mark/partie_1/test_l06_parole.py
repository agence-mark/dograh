"""[.mark] Chantier Partie 1, lot 6 : la couche de parole à la version finale de B12 (repli A seul, D62 ; accueil sans la carte, B13 point 2).

Les essais de la parole se jouent sans modèle : les retours de la vraie porte (montage ``porte_essai.py``) et des phrases écrites d'après les
bancs B10 à B12 (cas cités par leur nom). Aucun test n'appelle un fournisseur (garde du lot 0).
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.gabarits.restauration.textes import banc as B

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
    assert "Ne dis que les chiffres des faits" in BC.RAPPEL_DU_CHIFFRE  # C6 n° 12 (décision d'Evan 25/11 9 h 30) : le modèle dit les prix des faits, plus « dits par le code »


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


def _puis(p, fiche=None):
    """Ce que la relance du modèle lui donne à dire ensuite (``puis``), lu dans la consigne que le code construit : du JSON, jamais une phrase."""
    import json

    consigne = R.consigne_de_relance(p, fiche if fiche is not None else {}, PAROLE.EtatDuTour(tour=3))
    return json.loads(consigne[consigne.index("{"):])["puis"], consigne


def test_relance_question_en_attente():
    """L06-28, décision d'Evan 25/11 8 h 45 (lot 7b-C5) : au bout des passes, le code relance le modèle avec la question en attente en faits (conv3 t2) ; C6 (décision d'Evan 25/11 9 h 30) :
    la relecture est dite par le modèle, elle est relancée par son type, sans texte ; une proposition n'est jamais redite par sa phrase."""
    relecture = "Je vous relis : une Margherita Mega et une Margherita Normale, à emporter. C'est bon ?"  # un texte d'avant C6 resté au registre : jamais rendu
    puis, _ = _puis({CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-2", "type": "relecture", "texte": relecture}}, "lignes": []})
    assert puis == {"question": {"id": "Q-2", "type": "relecture"}}
    proposition = "Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ?"
    puis, consigne = _puis({CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "proposition", "texte": "proposer Coca-Cola", "repli": proposition, "article_propose": "Coca-Cola"}}})
    assert puis == {"question": {"id": "Q-1", "type": "proposition", "article_propose": "Coca-Cola"}} and proposition not in consigne


async def test_repli_valeur_du_manque(essai_de):
    """L06-28 (f307 t2) : sous le minimum, sans question en attente, la relance porte ce qui manque en valeur fermée (lot 7b-C5), jamais la phrase du module."""
    e = await essai_de("casa-italia", minimum=5000)
    await e.tour("en livraison au 9 avenue du Bouteiller à Chantilly", mode_de_retrait="livraison", commune="Chantilly", adresse="9 avenue du Bouteiller")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p) or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    assert CONV.question_de(e.p) is None, CONV.question_de(e.p)
    puis, consigne = _puis(e.p, e.fiche_de_l_appel)
    assert puis == {"manque": "d'autres articles, ou qu'elle dise qu'elle a tout dit"} and "Je vous mets autre chose" not in consigne, consigne


# --------------------------------------------------------------------------- la note composée (L06-07)


def test_allergie_jamais_perdue_regle():
    """L06-07 (E22, n8), la règle : l'allergie du greffier et la note du modèle sont toutes deux dans la note, rien n'est écrasé."""
    note = composer_la_note_de_commande([{"texte": "bien cuite"}], {"allergie": "arachides", "consigne_livreur": "aucune"})
    assert note == "Allergie : arachides ; bien cuite"  # D23 : l allergie ouvre la note
    assert composer_la_note_de_commande([{"texte": "allergie aux arachides"}], {"allergie": "arachides"}) == "Allergie : arachides ; allergie aux arachides"  # D23 : toujours avec son en-tête


async def test_allergie_jamais_perdue(essai_de):
    """L06-07 (E22, n8) : allergie notée par le greffier plus note du modèle : les deux dans la note envoyée avec la commande."""
    e = await essai_de("casa-italia")
    e.fiche_de_l_appel["allergie"] = "arachides"
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale bien cuite", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}],
                 note_generale="bien cuite")
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = CONV.question_de(e.p)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    if not e.p.get("enregistree"):
        await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    if not e.p.get("enregistree"):
        await e.tour("Léa", prenom="Léa")
    if (CONV.question_de(e.p) or {}).get("type") == "numero_dicte":  # DC10 : le numéro dicté relu, son « oui »
        await e.tour("oui", reponse={"question_id": CONV.question_de(e.p)["id"], "sens": "accepte"})
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
    q = CONV.question_de(e.p) or {}
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


async def test_minimum_donne_au_modele_puis_issue(essai_de):
    """L06-02 (B7, 6/6) : un fait bloquant jette ``a_dire`` (le modèle repasse avec le retour). B3 (M5, H6) : lot 7b (Q1), le minimum n'est plus dit par le code : le retour porte ses faits
    (``minimum_de_la_commande``) la première fois qu'il bloque ; redit, le journal de ce qui est dit donne une issue."""
    from api.services.actions_communes import journal_du_dit as J

    e = await essai_de("casa-italia", minimum=5000)
    await e.tour("en livraison au 9 avenue du Bouteiller à Chantilly", mode_de_retrait="livraison", commune="Chantilly", adresse="9 avenue du Bouteiller")
    cases = {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("une margherita normale", **cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Parfait, une margherita.", **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, (d, r)
    assert r["faits"]["minimum_de_la_commande"] == {"commune": "Chantilly", "minimum": 5000, "manque": 3910,  # F3 (C7 B6) : les montants aussi en lettres
                                                     "minimum_dit": "cinquante euros", "manque_dit": "trente-neuf euros dix"}, r["faits"]
    assert not (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("prefixe") and r["a_faire"].startswith(PORTE.A_FAIRE_DU_MINIMUM), r
    q = CONV.question_de(e.p) or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r = await e.tour("c'est tout", c_est_tout=True)
    assert "minimum_de_la_commande" not in r["faits"] and J.A_FAIRE_ISSUE in r["a_faire"], r


async def test_recapitulatif_dit_par_le_code(essai_de):
    """L06-01 (b) (K4 du banc), réécrit par C6 (décision d'Evan 25/11 9 h 30) : le récapitulatif est dit par le modèle ; le code ne dit que la phrase réglée du total, après la sienne."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p) or {}
    if q.get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r = await e.tour("c'est tout", c_est_tout=True)
    total = (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("suffixe")
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture" and total, r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Parfait, je vous relis la commande."})
    assert d.mode == PAROLE.SECOND_PASSAGE, d  # la relecture née : le modèle repasse avec ses faits
    dit = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler("Alors une Margherita à emporter.")
    assert dit is not None and dit.a_dire == f"Alors une Margherita à emporter. {total}", dit


def test_prix_dit_apres_la_question_du_modele():
    """L06-29 (T3) : une question née dans ce tour : la phrase réglée que le code dit après elle suit la phrase du modèle, une fois. C6 n° 11 (décision d'Evan 25/11 9 h 30) :
    plus aucun prix (celui d'une proposition est un fait que le modèle dit) ; il reste le total de la relecture."""
    etat = PAROLE.EtatDuTour(tour=3)
    p = {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "relecture", "nee_au_tour": 3}}}
    d = PAROLE.parole_du_tour({"statut": "FAIT"}, "Alors une Regina.", etat, [], p, {}, {"suffixe": "Cela fait douze euros, c'est bon ?"})
    assert d.mode == PAROLE.SECOND_PASSAGE and etat.suffixe == "Cela fait douze euros, c'est bon ?"
    assert PAROLE.avec_le_suffixe("Alors une Regina, sans oignons.", etat) == "Alors une Regina, sans oignons. Cela fait douze euros, c'est bon ?"
    assert PAROLE.avec_le_suffixe("Autre chose ?", etat) is None  # dit une fois
    # passe vide après la naissance de la proposition : lot 7b-C5, le modèle est relancé avec la proposition en faits, le code ne dit plus la phrase de B8
    b8 = "Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ?"
    puis, consigne = _puis({CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "proposition", "texte": "x", "repli": b8}}})
    assert puis["question"]["type"] == "proposition" and b8 not in consigne


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
    """L06-26 (B12) : après un refus de LA FICHE, aucune phrase sans outil n'est dite : retenue, puis la relance fautive relance le modèle avec le fait (décision d'Evan 25/11 8 h 45)."""
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
    # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : la relance fautive n'est pas remplacée par une phrase du code : le modèle est relancé avec le fait
    assert relance is not None and relance.raison == PAROLE.REPLI_A and relance.a_dire is None and relance.consigne, relance


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
    assert relance is not None and relance.a_dire is None and relance.consigne, (relance, r)  # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : relancé avec le fait, pas de phrase du code


def test_porte_la_fiche():
    assert PF.porte_la_fiche({CLE_DES_CASES_MONTREES: {"fiche": ["ajouter"]}})
    assert not PF.porte_la_fiche({CLE_DES_CASES_MONTREES: {"lire": []}})


# --------------------------------------------------------------------------- le tour borné (L06-39, D51)


async def test_tour_borne_sur_429():
    """L06-39 (D51) : un 429 du fournisseur (réponse enregistrée, aucun appel réel) : une nouvelle tentative au plus, puis l'erreur, jamais d'attente
    sans fin. Le client est créé par ``CerveauBorneMixin`` ; que chaque service de la fabrique le porte est dit par ``test_p1f_lot4_cerveau.py``."""
    import httpx
    import openai

    from api.services.pipecat.borne_du_tour import DELAI_D_UNE_PASSE_S, CerveauBorneMixin

    vues = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        vues.append(requete.url.path)
        return httpx.Response(429, json={"error": {"message": "rate limited", "type": "rate_limit"}}, headers={"retry-after": "0"})

    client = openai.AsyncOpenAI(api_key="essai", base_url="http://fournisseur.essai/v1", http_client=httpx.AsyncClient(transport=httpx.MockTransport(repondre)))

    class _Base:
        def create_client(self, **_):
            return client

    class _Service(CerveauBorneMixin, _Base):
        pass

    service = SimpleNamespace(_client=_Service().create_client())
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
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = CONV.question_de(e.p)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    for dit, cases in (("zéro six douze trente-quatre cinquante-six soixante-dix-huit", {"telephone": "0612345678"}), ("Léa", {"prenom": "Léa"})):
        if not e.p.get("enregistree"):
            await e.tour(dit, **cases)
    if (CONV.question_de(e.p) or {}).get("type") == "numero_dicte":  # DC10 : le numéro dicté relu, son « oui »
        await e.tour("oui", reponse={"question_id": CONV.question_de(e.p)["id"], "sens": "accepte"})
    assert e.p.get("enregistree") and e.fiche_de_l_appel.get("call_disposition") == "commande_enregistree", e.fiche_de_l_appel.get("call_disposition")


async def test_issue_annulee_et_abandonnee(essai_de):
    """L06-15 : ``commande_annulee`` posée par l'annulation de la commande en cours (2677 : plus jamais « end_call »)."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p) or {}
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
                                      definition={"type": "transfer_agent", "config": {"workflow_id": 300, "description_demande": banc["parameters"]["properties"]["demande"]["description"]}},  # lot 5 (n° 123) : posé par l'installation
                                      tool_uuid=cible))
    return banc, outils


def test_passer_a_egal_a_la_version_finale():
    """L06-43 : l'outil unique rendu par le moteur est, mot pour mot, celui de la version finale (B8 point 2, B13 point 2)."""
    from api.services.workflow import passage_unique as PU

    banc, outils = _passages_de_la_version_finale()
    assert PU.schema(outils)["function"] == banc
    assert PU.outil_de_la_cible(outils, {"cible": "service", "demande": "x"}) is outils[2]
    assert PU.outil_de_la_cible(outils, {"cible": "livraison"}) is None
    assert not PU.actif({}) and PU.actif({"passage_unique": True})  # éteint par défaut


def test_cible_gardee_a_l_enregistrement():
    """L06-43 : la case ``cible`` d'un passage survit à l'enregistrement de l'outil (constaté sur chantier le 19/11 : le schéma la retirait)."""
    from api.schemas.tool import TransferAgentToolDefinition

    d = TransferAgentToolDefinition.model_validate({"type": "transfer_agent", "config": {"workflow_id": 300, "message": "", "cible": "commande"}})
    assert d.model_dump()["config"]["cible"] == "commande"
    assert TransferAgentToolDefinition.model_validate({"type": "transfer_agent", "config": {"workflow_id": 300}}).config.cible is None


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

    outils = {o["function"]["name"] for etats in B.rendus()["cartes"].values() for e in etats for o in e["outils"]}
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
    assert relance is not None and relance.raison == PAROLE.REPLI_A and relance.outil is None and relance.a_dire is None and relance.consigne  # décision d'Evan 25/11 8 h 45 (lot 7b-C5)


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
    from api.services.groupe.passations import CLE_PORTEURS, porteur_de_l_action_ouverte, refus_de_passation
    from api.services.workflow import etat_des_connecteurs as EC

    p = P.nouveau()
    p.update(mode="emporter", lignes=[{"n": 1, "quantite": 2, "nom": "Reine", "variante": "Normale"}])
    trace = [{"de": 299, "vers": 300, "raison": "passer_a_l_agent_commande", "issue": "completed"},
             {"de": 300, "vers": 299, "raison": "retour", "issue": "completed"}]
    ouverte = {P.CLE: p, "passations": trace, "conversation": {CLE_PORTEURS: {"commande": 300}}}  # lot 5 (n° 121) : la reprise est routée vers l'agent qui tient l'action, noté à sa fiche
    assert porteur_de_l_action_ouverte(ouverte, sauf=299) == 300
    assert refus_de_passation(ouverte, {}, de=299, vers=300, raison="passer_a_l_agent_commande") is None
    from api.services.commande import etape as ETAPE  # lot 2 : l'étape est la seule à écrire « enregistrée »

    enregistre = {**p}
    ETAPE.transition(enregistre, ETAPE.ENREGISTREE_EN_BASE, faits={"numero": "C1", "numero_court": "12"}, empreinte="e")
    finie = {P.CLE: enregistre, "passations": trace, "conversation": {CLE_PORTEURS: {"commande": 300}}}
    assert porteur_de_l_action_ouverte(finie, sauf=299) is None
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

from api.tests.mark.partie_1.egalite_b12 import CONVERSATIONS, ECARTS_DE_LA_PAROLE, REPONSES  # noqa: E402

# Les seules différences de texte admises entre le banc et le fork, liste fermée : chacune est une décision d'Evan ou du plan que le simulateur
# du banc ne porte pas (``banc-b2/guichet_candidat.py`` : « Ce qu'il simplifie »), et a sa ligne dans ``a-trancher.md``. Rien d'autre n'est toléré.
DIFFERENCES_NOMMEES: tuple[tuple[str, str, str], ...] = (
    # M26 : le fork accorde au genre de la carte (« un Coca-Cola offert ») ; le banc dit « une » et « offerte » pour tout article.
    ("accord au genre (M26)", r"\bun\b", "une"),
    ("accord au genre (M26)", r"\boffert\b", "offerte"),
    # M121 : l'heure annoncée d'une livraison est son arrivée (« elle sera livrée ») ; le banc dit « prête » en livraison aussi.
    ("arrivée d'une livraison (M121)", r"\belle sera livrée\b", "elle sera prête"),
    # C11 (lot 4) : le rendu de la monnaie, calculé par le code, dit dans la confirmation ; le banc ne le calcule pas.
    ("rendu de la monnaie (C11)", r" ?Sur votre billet de [^.]+, on vous rendra [^.]+\.", ""),
    # Point de contrôle du lot 7 (SA-C, règle du lot 6 rappelée par le coordinateur) : un fait bloquant qui refuse est dit par le code avant la phrase
    # du modèle (préfixe, la phrase du module) ; au banc, seul le modèle le disait.
    ("fait bloquant dit par le code (point de contrôle du lot 7)", r"^Nous ne livrons pas à [^.]+\.(?: Nous livrons [^.]+\.)? ?", ""),
)


def lu_comme_au_banc(texte: str) -> str:
    for _nom, motif, par in DIFFERENCES_NOMMEES:
        texte = re.sub(motif, par, texte)
    return " ".join(texte.split())


def eteindre_la_question_apres_enregistrement(e) -> None:
    """M108 et DC10 sont des réglages (motifs ``apres_enregistrement`` et ``numero_dicte_relu``, éteignables à l'écran) que l'agent du banc B12
    n'a pas : ils sont éteints pour l'égalité, comme sur l'agent du banc ; les agents du chantier gardent les leurs."""
    from api.services.phrases.catalogue import APRES_ENREGISTREMENT, NUMERO_DICTE_RELU
    from api.services.phrases.regles import CLE_REGLES

    e.ctx.configurations = {**(e.ctx.configurations or {}), CLE_REGLES: [{"motif": m, "portee": "agent", "active": False} for m in (APRES_ENREGISTREMENT, NUMERO_DICTE_RELU)]}


def _texte_du_modele(tour: dict) -> str:
    """La phrase du second passage du modèle au banc : le texte dit, sans ce que le code a dit avant ou après elle."""
    texte = tour.get("texte") or ""
    for bord in (tour.get("prefixe"), tour.get("suffixe")):
        if bord:
            texte = texte.replace(bord, "")
    return " ".join(texte.split())


async def poser_l_offre_de_casa(e) -> None:
    """La Casa Italia du banc B12 a son offre (``banc-b2/guichet_candidat.py`` ``OFFRE`` : « deux pizzas, une boisson offerte »), que la carte figée du
    banc A n'a pas : elle est posée dans la base de l'essai comme le portail la pose (mécanisme ``x_achetes_y_offert``), avant le premier geste."""
    import json

    await e.monde.c.execute(
        "INSERT INTO mark.resto_remise (site_id, ref, nom, mecanisme, declencheur, effet, perimetre, etat, cumul, phrase) "
        "VALUES ($1, 'DEUX-UNE', 'deux pizzas, une boisson offerte', 'x_achetes_y_offert', $2::jsonb, $3::jsonb, $4::jsonb, 'active', 'exclusive', $5)",
        e.monde.a, json.dumps({"achetes": 2}), json.dumps({"offerts": 1, "perimetre_offert": {"categories": ["boissons"]}}),
        json.dumps({"categories": ["pizzas-tomate", "pizzas-creme", "pizzas-eccellenza"]}), "Deux pizzas achetées, une boisson offerte.",
    )


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
                if seconde is not None and seconde.a_dire:
                    par, dit = "code", seconde.a_dire
                elif seconde is not None and seconde.consigne:
                    par, dit = "relance du fait", libre  # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le code ne dit rien, le modèle est relancé avec le fait
                else:
                    par, dit = "modele", libre
        attendu = PAROLE.sans_balisage(tour.get("texte") or "") if tour["dit_par"] in ("code", "a_dire", "modele+code") else None
        if par != tour["dit_par"] or (attendu is not None and lu_comme_au_banc(PAROLE.sans_balisage(dit or "")) != lu_comme_au_banc(attendu)):
            ecarts.append(f"{conversation['conversation']} tour {i} « {tour['dit'][:40]} » : banc {tour['dit_par']} « {(tour.get('texte') or '')} » / "
                          f"fork {par} « {(dit or '')} » [{retour.get('statut')} {retour.get('raison')}]")
    return ecarts


@pytest.mark.parametrize("nom", [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=ECARTS_DE_LA_PAROLE[n])) if n in ECARTS_DE_LA_PAROLE else n
                                 for n in CONVERSATIONS])
async def test_egalite_banc_et_fork(essai_de, nom):
    """L06-41 (D67) : les réponses de B12 servies à la vraie boucle donnent les mêmes phrases dites (qui les dit, et le texte quand le code ou
    ``a_dire`` le dit) que le banc, sans requête ; le panier et les refus sont égaux au lot 3 (``test_l03_porte.py``)."""
    conversation = next(c for c in REPONSES["conversations"] if c["conversation"] == nom)
    e = await essai_de()
    await poser_l_offre_de_casa(e)
    eteindre_la_question_apres_enregistrement(e)
    ecarts = await phrases_de_la_conversation(e, conversation)
    assert ecarts == [], chr(10).join(ecarts)


# --------------------------------------------------------------------------- essais au clavier sur une prise sans client, balises, chargement

import asyncio  # noqa: E402
from types import SimpleNamespace as _NS  # noqa: E402


def _morceau(texte=None, appel=False):
    appels = [_NS(index=0, id="x", function=_NS(name="fiche", arguments="{}"))] if appel else None
    return _NS(choices=[_NS(delta=_NS(content=texte, tool_calls=appels), finish_reason=None)], usage=None)


async def _flux(*morceaux):
    for m in morceaux:
        yield m


def _texte_rendu(morceaux):
    return "".join(m.choices[0].delta.content or "" for m in morceaux)


async def _lire(flux):
    return [m async for m in flux]


def test_aucune_balise_dite():
    """Appel 4 du chantier : « <thought > » sorti dans la phrase dite. La balise est retirée, coupée entre deux morceaux comprise ; le texte autour,
    un « < » qui n'ouvre pas une balise, et les appels d'outil passent intacts."""
    from api.services.pipecat.reponse_avalee import SansBalise

    rendu = asyncio.run(_lire(SansBalise(_flux(_morceau("C'est l'IA.\n\n<thou"), _morceau("ght\n>"), _morceau("\n\nC'est noté.")))))
    assert "<" not in _texte_rendu(rendu) and _texte_rendu(rendu).split() == ["C'est", "l'IA.", "C'est", "noté."], _texte_rendu(rendu)
    long = "a < " + "b" * 60 + " fin"
    assert _texte_rendu(asyncio.run(_lire(SansBalise(_flux(_morceau(long)))))) == long
    assert _texte_rendu(asyncio.run(_lire(SansBalise(_flux(_morceau("deux <3")))))) == "deux <3"
    avec_outil = asyncio.run(_lire(SansBalise(_flux(_morceau("<b>Je note</b>"), _morceau(appel=True)))))
    assert _texte_rendu(avec_outil) == "Je note" and avec_outil[-1].choices[0].delta.tool_calls


def test_prise_sans_tiers_seulement_demo_ou_essai():
    """B42 protège le système d'un client : seule une prise qui ne parle à aucun client (caisse de démo du Labo, prise d'essai) le dit."""
    from api.services.restauration.caisse.prises.hubrise_client import ClientHubrise
    from api.services.restauration.caisse.prises.prise import PrisePortail
    from api.services.restauration.caisse.prises.prise_essai import PriseTest
    from api.services.restauration.caisse.prises.prise_hubrise import PriseHubrise

    assert PriseTest().sans_tiers is True
    assert PrisePortail().sans_tiers is False
    assert PriseHubrise().sans_tiers is False
    assert PriseHubrise(ClientHubrise("jeton", labo=False)).sans_tiers is False
    assert PriseHubrise(ClientHubrise("jeton", labo=True)).sans_tiers is True


def test_au_clavier_une_action_sans_tiers_est_jouee_pour_de_vrai():
    """Le rejeu simule une action qui écrit (B42) ; elle est jouée pour de vrai quand le connecteur dit que l'appel n'écrit chez aucun client,
    et reste simulée quand il dit non, ne sait pas, ou échoue."""
    from api.services.tests_rejouables import simulation as SIM

    def moteur():
        return _NS(_gathered_context={SIM.CLE_REJEU: True})

    def cas(sans_tiers):
        m, joues, rendus = moteur(), [], []

        async def vrai(params):
            joues.append(params.arguments)

        async def rendre(r):
            rendus.append(r)

        g = SIM.simuler_si_rejeu(m, "integration", "fiche", vrai, sans_tiers=sans_tiers)
        asyncio.run(g(_NS(arguments={"a_dire": "x"}, result_callback=rendre)))
        return joues, rendus, m._gathered_context.get(SIM.CLE_NOTES)

    async def oui():
        return True

    async def non():
        return False

    async def panne():
        raise RuntimeError("base")

    joues, rendus, notes = cas(oui)
    assert joues == [{"a_dire": "x"}] and rendus == [] and notes[0]["joue_pour_de_vrai"] is True
    for faux in (non, panne, None):
        joues, rendus, notes = cas(faux)
        assert joues == [] and rendus == [SIM.RESULTAT_NEUTRE] and "joue_pour_de_vrai" not in notes[0], faux


def test_la_commande_dit_sa_prise_au_clavier_et_le_moteur_la_lit():
    from api.services.integrations.connectors.catalogue import connecteur

    assert connecteur("commande").sans_tiers is not None


def test_le_clavier_charge_l_appel_comme_le_decroche(monkeypatch):
    """Appel 4 du chantier : au clavier, la fiche partait sans ses listes fermées (le chargement du lot 5 n'était branché qu'au décroché)."""
    from api.services.commande.contrat import CLE_DES_OBJETS
    from api.services.restauration.appel_et_memoire import memoire_de_l_appel as MEM

    vus = []

    def charger(org, run, configs, contexte, fiche):
        async def tache():
            vus.append(run)
            contexte["listes_de_la_fiche"] = ["emporter", "livraison"]
            fiche[CLE_DES_OBJETS] = {"choix": True}

        return asyncio.get_event_loop().create_task(tache())

    monkeypatch.setattr(MEM, "charger_au_decroche", charger)
    contexte, fiche = {}, {}

    async def deux_tours():
        await MEM.charger_au_clavier(1, 7, {}, contexte, fiche)
        await MEM.charger_au_clavier(1, 7, {}, contexte, fiche)

    asyncio.run(deux_tours())
    assert vus == [7] and contexte["listes_de_la_fiche"] and fiche[CLE_DES_OBJETS]


def test_le_controle_des_arguments_connait_les_cases_de_la_fiche():
    """Appel 5 du chantier : ``garde_arguments_controles`` allumé jugeait ``ajouter`` (une liste) comme un texte, et chaque fiche qui ajoutait
    un article revenait « à redemander ». Une liste, un objet, un entier sont jugés sur leur forme ; une forme fausse reste refusée."""
    from api.services.integrations.connectors import garde
    from api.services.integrations.connectors.catalogue import connecteur

    fiche = connecteur("commande").action("fiche")
    bons = {"a_dire": "C'est noté.", "ajouter": [{"article": "margherita", "quantite": 1}], "mode_de_retrait": "emporter", "c_est_tout": True}
    assert garde.arguments_invalides(fiche, bons) == []
    assert garde.arguments_invalides(fiche, {"ajouter": "une margherita"}) == ["ajouter"]
    entier = next(p for p in fiche.parametres if p.type == "integer") if any(p.type == "integer" for p in fiche.parametres) else None
    if entier is not None:
        assert garde.arguments_invalides(fiche, {entier.nom: 2}) == [] and garde.arguments_invalides(fiche, {entier.nom: "deux"}) == [entier.nom]


def test_une_requete_lancee_directement_au_cerveau_a_la_forme_d_une_requete_ordinaire():
    """Appel 6 du chantier : l'ouverture de l'agent de commande après une passation (``run_llm``, sans phrase d'accueil) partait sans ses cases
    selon l'état ; sa première fiche était refusée « cases_pas_ouvertes ». ``run_llm`` passe par la même forme que la requête ordinaire."""
    from api.services.workflow.agent_runtime import AgentRuntime
    from api.services.workflow.cases_selon_l_etat import CasesIllisibles

    poussees = []

    class Cerveau:
        async def queue_frame(self, trame):
            poussees.append(trame)

    def agent(preparer=None):
        a = AgentRuntime.__new__(AgentRuntime)
        a.llm = Cerveau()
        if preparer is not None:
            a.preparer_la_forme = preparer
        return a

    async def preparee(trame):
        return "trame préparée"

    async def illisible(trame):
        raise CasesIllisibles("aucune case")

    asyncio.run(agent(preparee).run_llm(object()))
    assert poussees == ["trame préparée"]
    poussees.clear()
    asyncio.run(agent(illisible).run_llm(object()))
    assert poussees == []
    asyncio.run(agent().run_llm(object()))
    assert len(poussees) == 1 and poussees[0] != "trame préparée"


def test_la_lecture_garde_ses_cases_quand_la_fiche_suit_l_etat():
    """Appel 23 du chantier (n11) : les cases selon l'état de la fiche étaient appliquées à tous les outils du connecteur ; ``lire`` partait sans
    ``sujet`` ni ``article`` et la question « la Napoli contient-elle des anchois ? » n'était jamais lue. Seule la fiche suit l'état."""
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    from api.services.integrations.connectors.actions.commande import COMMANDE
    from api.services.integrations.connectors.outil import _propriete
    from api.services.workflow import cases_selon_l_etat as CSE
    from api.services.workflow import etat_des_connecteurs as EDC

    moteur = _NS(_gathered_context={})
    for nom, action in (("fiche", "fiche"), ("lire", "lire")):
        EDC.inscrire_l_outil(moteur, nom, _NS(definition={"config": {"connecteur": "commande", "action": action}}))
    outils = []
    for action in ("fiche", "lire"):
        a = COMMANDE.action(action)
        outils.append(FunctionSchema(name=action, description=a.description, properties={p.nom: _propriete(p, {}) for p in a.parametres},
                                     required=[p.nom for p in a.parametres if p.obligatoire]))
    rendus, montrees = CSE.outils_selon_l_etat(moteur, ToolsSchema(standard_tools=outils))
    lire = next(o for o in rendus.standard_tools if o.name == "lire")
    assert {"sujet", "article"} <= set(lire.properties), lire.properties
    assert "fiche" in montrees and "lire" not in montrees


def test_la_question_deja_donnee_est_posee_par_la_phrase_de_la_fiche():
    """Lot 19, D04 (styles du lot 17, SOBRE-A n° 2) : la vente en plus naît dans le tour, le second passage la donne au modèle ; il répond par une fiche qui
    ne change rien, dont la phrase pose la question (« Désirez-vous un Coca-Cola ? ») : elle est dite, suivie du prix dû par le code, jamais un passage de
    plus (le troisième rendait un texte vide : tour muet)."""
    etat = PAROLE.EtatDuTour(tour=1)
    p = {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "proposition", "nee_au_tour": 1}}}
    premiere = PAROLE.parole_du_tour({"statut": "FAIT"}, "C'est noté pour votre Reine.", etat, [], p, {"ajouter": [{"article": "reine"}]},
                                     {"suffixe": "Il est à deux euros."})
    assert premiere.mode == PAROLE.SECOND_PASSAGE and premiere.motif == "question_nouvelle"
    seconde = PAROLE.parole_du_tour({"statut": "FAIT"}, "Désirez-vous un Coca-Cola pour accompagner votre commande ?", etat, [], p, {"ajouter": []})
    assert seconde.mode == PAROLE.A_DIRE_SEUL, seconde
    assert seconde.a_dire == "Désirez-vous un Coca-Cola pour accompagner votre commande ? Il est à deux euros.", seconde


async def test_commande_sans_caisse_jouee_pour_de_vrai_au_labo_seulement(monkeypatch):
    """Lot 19 (restaurants installés par le gabarit, lot 18) : sans caisse, la prise est celle du portail (le classeur est maître, rien n'est envoyé) ;
    au Labo, l'essai au clavier y commande pour de vrai, comme la réservation ; chez un client, il reste simulé (B42) ; une vraie caisse reste simulée."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from api.services.integrations.connectors.actions import commande as C
    from api.services.restauration.appel_et_memoire import memoire_de_l_appel
    from api.services.restauration.caisse.caisse_demo import garde
    from api.services.restauration.caisse.prises import prise as PR
    from api.services.restauration.caisse.prises.hubrise_client import ClientHubrise
    from api.services.restauration.caisse.prises.prise_hubrise import PriseHubrise

    @asynccontextmanager
    async def geste(ctx):
        yield None, SimpleNamespace(etablissement_id=1, nom_base="b")

    monkeypatch.setattr(memoire_de_l_appel, "geste", geste)
    prise = {"valeur": PR.PrisePortail()}

    async def prise_de(_contexte):
        return prise["valeur"]

    monkeypatch.setattr(PR, "prise_de_l_etablissement", prise_de)

    async def labo(organization_id):
        return organization_id == 1

    monkeypatch.setattr(garde, "organisation_est_labo", labo)
    assert await C._sans_tiers(SimpleNamespace(organization_id=1)) is True
    assert await C._sans_tiers(SimpleNamespace(organization_id=2)) is False
    prise["valeur"] = PriseHubrise(ClientHubrise("jeton", labo=False))
    assert await C._sans_tiers(SimpleNamespace(organization_id=1)) is False


def test_allergie_en_tete_de_la_note_jamais_coupee():
    """Lot 19, D23 (note de Pierre du 20/11, point 1, E22) : l'allergie ouvre la note, toujours avec son en-tête, même si son mot est déjà dans une
    autre note (« sans noix » n'est pas une allergie) ; la coupe à la taille de la note porte sur le reste, jamais sur elle."""
    assert composer_la_note_de_commande([{"texte": "pizza sans noix"}], {"allergie": "noix"}) == "Allergie : noix ; pizza sans noix"
    longue = [{"texte": "x" * 200}, {"texte": "y" * 200}]
    note = composer_la_note_de_commande(longue, {"allergie": "arachides"})
    assert note.startswith("Allergie : arachides ; ") and len(note) <= 300, note
