"""[.mark] Chantier Partie 1 : les corrections du point de contrôle du lot 7 (SA-C), une par défaut trouvé au clavier.

Chacune a été vue rouge sur ``dbd209f1`` (le code joué au point de contrôle) avant sa correction.
"""

from __future__ import annotations

import re
from pathlib import Path
from api.services.actions_communes import conversation as CONV

API = Path(__file__).resolve().parents[3]


def test_l_image_ecrit_la_pile_d_un_plantage_natif():
    """Défaut 1 (19/11, 16:05 et 16:09 UTC) : deux segfaults du serveur sans aucune pile Python. L'image allume ``faulthandler``
    pour chaque processus Python (uvicorn, arq, ari) : la prochaine fois, la pile de chaque fil est écrite dans les journaux."""
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    image_finale = dockerfile.split("AS runner", 1)[1]
    assert re.search(r"^ENV PYTHONFAULTHANDLER=1\s*$", image_finale, re.M)


def test_au_clavier_la_reservation_du_labo_est_jouee_pour_de_vrai(monkeypatch):
    """Défaut 2 (« [rejeu] fiche simulé : rien n'est parti ») : la réservation n'avait pas de ``sans_tiers``, sa fiche restait simulée en
    essai et l'agent ne pouvait rien réserver au clavier. Le classeur (la base du client dans le fork) ne parle à aucun client pour
    l'organisation Labo, comme la caisse de démo ; chez un client c'est son vrai cahier : simulé. Une source qui ne dit rien : simulée."""
    import asyncio
    from types import SimpleNamespace

    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.reservation import source as registre
    from api.services.restauration.caisse.caisse_demo import garde

    async def labo():
        return 7

    monkeypatch.setattr(garde, "id_du_labo", labo)
    reservation = connecteur("reservation")
    assert reservation.sans_tiers is not None and connecteur("commande").sans_tiers is not None

    def lu(organisation, reglages=None):
        return asyncio.run(reservation.sans_tiers(SimpleNamespace(organization_id=organisation, reglages=reglages or {})))

    assert lu(7) is True
    assert lu(8) is False and lu(None) is False
    assert lu(7, {"source": "classeur"}) is True
    monkeypatch.setitem(registre._SOURCES, "logiciel_du_client", registre._SOURCES["classeur"])
    assert lu(7, {"source": "logiciel_du_client"}) is False


def test_le_moteur_donne_les_reglages_de_l_outil_a_la_question(monkeypatch):
    """La source d'une réservation se lit dans le réglage de SON outil : la question posée au geste les porte."""
    import asyncio
    from types import SimpleNamespace

    from api.services.integrations.connectors import outil

    vus = []

    async def sans_tiers(ctx):
        vus.append(ctx.reglages)
        return True

    monkeypatch.setattr(outil, "connecteur_interne", lambda tool: SimpleNamespace(sans_tiers=sans_tiers))
    monkeypatch.setattr(outil, "configurations_de_l_etape", lambda manager: {})

    async def org():
        return 1

    manager = SimpleNamespace(_engine=SimpleNamespace(), get_organization_id=org)
    tool = SimpleNamespace(definition={"config": {"connecteur": "reservation", "action": "fiche", "reglages": {"source": "classeur"}}})
    assert asyncio.run(outil.sans_tiers_de(manager, tool)()) is True
    assert vus == [{"source": "classeur"}]


async def test_aucun_tour_muet_quand_le_modele_ne_rend_rien(essai_de):
    """Défaut 3 (``pc7-conv2-hors-zone``, tour 1, appel 28) : la fiche rend le hors zone et la proposition offerte ; le second passage du
    modèle ne rend rien (4 jetons, relance sans flux vide aussi) : le flux vérifié ne contrôlait qu'un texte, rien n'était dit. Sur une étape
    qui porte la fiche, le silence du modèle au bout des passes relance le modèle avec le fait (``consigne_de_relance``, lot 7b-C5)."""
    from types import SimpleNamespace

    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de("casa-italia")
    e.dit("Deux reines normales, livrées au 8 rue Solférino à Compiègne")
    e.montrer()
    r = await e.fiche(ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}], mode_de_retrait="livraison",
                      adresse="8 Rue Solférino", commune="Compiègne", _montrer=False)
    assert (r.get("faits") or {}).get("fait_bloquant", {}).get("statut_du_module") == "HORS_ZONE", r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est entendu. Livraison ou retrait ?"})
    assert d.mode == PAROLE.SECOND_PASSAGE, d

    from api.tests.mark.partie_1.aides_du_cerveau import flux_du_cerveau

    # Décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le code ne compose plus le refus ; le modèle muet est relancé avec le fait (le refus, les communes livrées, l'autre mode),
    # et si la relance échoue la phrase réglée de l'agent est dite : jamais un tour muet.
    v = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    hors_zone = next(x for x in r["resultats"] if x.get("statut_du_module") == "HORS_ZONE")
    retenue = v.controler_le_silence()
    assert retenue is not None and retenue.a_dire is None and "HORS_ZONE" in retenue.consigne, retenue
    assert all(c in retenue.consigne for c in hors_zone["faits"]["communes_livrees"]), retenue.consigne
    assert "Nous ne livrons pas" not in retenue.consigne, retenue.consigne
    dit = await flux_du_cerveau("", PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)))  # le vrai cerveau : un modèle qui ne rend rien, la relance aussi
    assert dit.strip() and "Compiègne" not in dit, dit


async def test_le_fait_bloquant_d_une_fiche_d_avant_n_est_jamais_redit(essai_de):
    """Les faits du fait bloquant valent pour le tour de leur fiche : au tour suivant, la relance du modèle revient à la question en attente (lot 7b-C5)."""
    from api.services.actions_communes import repli as R
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de("casa-italia")
    await e.tour("Deux reines normales, livrées au 8 rue Solférino à Compiègne", ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}],
                 mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne")
    assert R.faits_du_fait_bloquant(e.fiche_de_l_appel)
    e.dit("Ah bon")
    p = PF.dossier_de_la_parole(e.fiche_de_l_appel)
    assert R.faits_du_fait_bloquant(e.fiche_de_l_appel) == []
    from api.services.actions_communes import parole as PAROLE

    consigne = R.consigne_de_relance(p, e.fiche_de_l_appel, PAROLE.etat_du_tour(e.fiche_de_l_appel)) or ""
    assert '"a_dire"' not in consigne, consigne  # le refus du tour d'avant n'est jamais redonné
    r = await e.tour("à emporter alors", mode_de_retrait="emporter")
    assert R.faits_du_fait_bloquant(e.fiche_de_l_appel) == [], r


def test_l_image_donne_ses_autorites_de_certification():
    """Défaut 1, cause trouvée (pile de faulthandler, 19/11 16:46 UTC) : deux fils d'anyio dans ``truststore._openssl._configure_context`` en même
    temps, qui recharge les certificats dans le contexte TLS partagé à chaque poignée de main. L'image donne le fichier des autorités."""
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    image_finale = dockerfile.split("AS runner", 1)[1]
    assert re.search(r"^ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates\.crt\s*$", image_finale, re.M)


def test_avec_le_fichier_des_autorites_aucun_client_ne_prend_truststore(monkeypatch):
    """Avec ``SSL_CERT_FILE``, le client d'openai (httpx2, httpcore2) crée un contexte TLS standard, ses certificats chargés une fois ; sans elle, un
    ``truststore.SSLContext`` (celui qui a planté)."""
    import ssl

    import certifi
    import httpcore2
    import truststore
    from httpx2._config import create_ssl_context

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    assert isinstance(create_ssl_context(), truststore.SSLContext)  # la forme qui a planté, sans la variable
    monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
    for contexte in (create_ssl_context(), httpcore2.default_ssl_context()):
        assert isinstance(contexte, ssl.SSLContext) and not isinstance(contexte, truststore.SSLContext), type(contexte)
        assert contexte.cert_store_stats()["x509_ca"] > 0


async def test_le_refus_hors_zone_est_donne_au_modele_et_une_phrase_jetee_n_est_jamais_dite(essai_de):
    """pc7g-conv2, tour 1 : la phrase du modèle (« Je ne peux pas livrer à Compiègne… ») est retenue au rattrapage, puis sa relance recopie la
    phrase jetée (« C'est bien noté pour vos deux pizzas reines à Compiègne. Livraison ou retrait ? ») et passe : le refus n'est jamais dit.
    Lot 7b (Q1) : le code ne dit plus le refus avant le second passage ; le retour le donne au modèle (faits) et une phrase jetée n'est jamais dite : le modèle est relancé avec le fait (C5)."""
    from types import SimpleNamespace

    from api.services.actions_communes import parole as PAROLE
    from api.services.commande import porte as PORTE
    from api.services.workflow import parole_de_la_fiche as PF

    jetee = "C'est bien noté pour vos deux pizzas reines à Compiègne. Est-ce que vous préférez une livraison ou un retrait à emporter ?"
    e = await essai_de("casa-italia")
    e.dit("Deux reines normales, livrées au 8 rue Solférino à Compiègne")
    e.montrer()
    r = await e.fiche(a_dire=jetee, ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}], mode_de_retrait="livraison",
                      adresse="8 Rue Solférino", commune="Compiègne", _montrer=False)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": jetee})
    assert d.mode == PAROLE.SECOND_PASSAGE and not hasattr(d, "prefixe"), d
    assert "refus_de_la_fiche" in r["faits"] and not (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("prefixe"), r
    v = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    assert v.controler("Je ne peux pas livrer à Compiègne, mais vous pouvez venir les chercher à emporter.") is not None  # le rattrapage du tour
    relance = v.controler_la_relance(jetee)
    # Décision d'Evan 25/11 8 h 45 (lot 7b-C5) : la phrase jetée, recopiée, n'est jamais dite et le code ne dit pas le refus à sa place : il relance le modèle avec le fait
    assert relance is not None and relance.a_dire is None, relance
    assert "HORS_ZONE" in relance.consigne and "Nous ne livrons pas" not in relance.consigne, relance.consigne


async def test_la_vente_en_plus_compte_les_choix_d_une_formule(essai_de):
    """pc7g-f307 : la boisson est prise comme choix du menu (« Un Coca »), puis la vente en plus repropose le Coca-Cola : la ligne de la formule
    porte la catégorie des menus, ses choix n'étaient pas comptés. Un choix de formule compte comme sa famille (ici « boisson ») : rien à proposer."""
    e = await essai_de("briques/FOR6")
    r = await e.tour("un menu whopper normal avec des frites et un coca, à emporter", mode_de_retrait="emporter",
                     ajouter=[{"article": "menu whopper", "quantite": 1, "variante": "Normal", "composition": ["frites", "coca"]}])
    assert e.p["lignes"] and any("Coca" in c["nom"] for c in e.p["lignes"][0]["choix"]), (r, e.p["lignes"])
    propose = [x for x in r.get("resultats") or [] if x.get("operation") == "proposition"]
    assert not propose and (CONV.question_de(e.p) or {}).get("type") != "proposition", r


async def test_le_changement_d_un_choix_de_formule_est_guide_puis_pris(essai_de):
    """pc7g-f307 : « Ah non, plutôt un Fanta » ; le modèle répond à la question close de l'étape (Q-1) et le refus lui disait « recopie
    l'identifiant de la question en attente » sans le donner : trois fois Q-1. Le refus dit maintenant la question en attente, ou qu'aucune
    n'attend ; et le changement par sa case (``changer_quantite`` avec la composition) remplace le seul choix de cette étape."""
    from api.services.actions_communes import registre_des_questions as B

    e = await essai_de("briques/FOR6")
    await e.tour("un menu whopper normal avec des frites et un coca, à emporter", mode_de_retrait="emporter",
                 ajouter=[{"article": "menu whopper", "quantite": 1, "variante": "Normal", "composition": ["frites", "coca"]}])
    assert CONV.question_de(e.p) is None, CONV.question_de(e.p)
    assert "aucune question n'attend" in B.question_inconnue({"reponse": {"question_id": "Q-1"}}, None)["a_faire"]
    attend = B.question_inconnue({"reponse": {"question_id": "Q-1"}}, {"id": "Q-2", "type": "proposition", "texte": "proposer X"})
    assert "Q-2" in attend["a_faire"] and attend["question"]["id"] == "Q-2", attend
    r = await e.tour("ah non, plutôt un jus d'orange", changer_quantite=[{"ligne": 1, "composition": ["jus d'orange"]}])
    noms = [c["nom"] for c in e.p["lignes"][0]["choix"]]
    assert any("orange" in n for n in noms) and not any("Coca" in n for n in noms) and any("Frites" in n for n in noms), (r, noms)


async def test_l_etat_dit_les_choix_d_une_ligne_de_formule(essai_de):
    """pc7j-f307 : l'état disait « ligne 1 : 1 × Menu kebab Maxi », sans la boisson choisie ; pour changer de boisson, le modèle retirait tout le
    menu. Une ligne de formule dit chaque étape et son choix, comme l'état du banc (« boisson : Coca »)."""
    from api.services.commande.etat_pour_le_modele import texte

    e = await essai_de("briques/FOR6")
    await e.tour("un menu whopper normal avec des frites et un coca, à emporter", mode_de_retrait="emporter",
                 ajouter=[{"article": "menu whopper", "quantite": 1, "variante": "Normal", "composition": ["frites", "coca"]}])
    etat = texte(e.fiche_de_l_appel, {}) or ""
    ligne = next(x for x in etat.splitlines() if x.startswith("- Lignes"))
    assert "boisson : Coca" in ligne and "frites : Frites" in ligne, ligne


async def test_une_ligne_retiree_n_est_jamais_annoncee_par_a_dire(essai_de):
    """pc7j-f307 : « je change la boisson » dite en un passage alors que la fiche retirait le menu entier. La phrase est écrite avant que le code
    exécute : après un retrait de ligne, le modèle repasse avec le retour, qui dit ce qui est retiré."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de("briques/FOR6")
    await e.tour("un menu whopper normal avec des frites et un coca, à emporter", mode_de_retrait="emporter",
                 ajouter=[{"article": "menu whopper", "quantite": 1, "variante": "Normal", "composition": ["frites", "coca"]}])
    e.dit("ah non, plutôt un jus d'orange")
    e.montrer()
    a_dire = "Pas de souci, je change la boisson. Voulez-vous autre chose ?"
    r = await e.fiche(a_dire=a_dire, retirer_article=[1], _montrer=False)
    assert r["statut"] == "FAIT" and "retirer_article" in r["cases_executees"], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": a_dire, "retirer_article": [1]})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.a_dire is None, d


def test_une_unite_dite_en_lettres_trouve_sa_forme_courte_de_la_carte():
    """pc7k-f307b : l'agent dit « Coca-Cola 33 centilitres » (les unités sont dites en lettres), le modèle le recopie, et la recherche ne trouvait pas
    « Coca-Cola 33 cl » : « Je n'ai pas « Coca-Cola 33 centilitres » pour Menu kebab Maxi ». Après un nombre, l'unité en lettres vaut sa forme courte,
    dans la recherche des choix comme des articles (une seule normalisation des noms)."""
    from api.db.bases_clients import recherche_liste
    from api.db.bases_clients.recherche_liste import Element
    from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche

    elements = [Element("C33", "Coca-Cola 33 cl", (), "Boissons"), Element("C15", "Coca-Cola 1,5 l", (), "Boissons"),
                Element("F33", "Fanta 33 cl", (), "Boissons"), Element("V500", "Viande 500 g", (), "Boucherie"), Element("V1", "Viande 1 kg", (), "Boucherie")]
    for dit, attendu in (("Coca-Cola 33 centilitres", "C33"), ("Fanta trente-trois centilitres", "F33"), ("viande 500 grammes", "V500"),
                         ("viande 1 kilo", "V1")):
        r = recherche_liste.chercher(elements, dit)
        assert r["statut"] == "RETENU" and r["retenu"] == attendu, (dit, r)
    assert norme_de_recherche("Coca-Cola 1,5 litre") == norme_de_recherche("Coca-Cola 1,5 l")
    assert norme_de_recherche("33 centilitres") == norme_de_recherche("33 cl")
    assert norme_de_recherche("un litre de lait") == norme_de_recherche("un litre de lait")  # sans nombre devant : rien ne change
    assert "litre" in norme_de_recherche("le litre")


async def test_replique_retenue_jamais_dite_si_la_relance_echoue():
    """Lot 19, D26 (note de Pierre du 20/11, point 4) : une réplique retenue (un chiffre sans source) dont la relance échoue (429, délai) n'est jamais
    rendue telle quelle : la phrase du code la remplace (le repli du point de contact, sinon une phrase neutre). Même chose quand la relance est retenue
    à son tour sans texte de l'outil à dire."""
    from types import SimpleNamespace

    from api.services.pipecat.reponse_avalee import RepliqueVerifiee

    def morceau(texte):
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)

    async def flux():
        yield morceau("Ça vous fera 15 euros.")

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    retenue = SimpleNamespace(a_dire=None, raison="chiffre", outil=None, appel_par_le_code=False)
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in RepliqueVerifiee(flux(), lambda t: retenue, relance_429)])
    assert dit.strip() and "15" not in dit, dit

    async def relance_fautive(_retenue):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="C'est 15 euros.", tool_calls=None), finish_reason="stop")], usage=None)

    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in RepliqueVerifiee(
        flux(), lambda t: retenue, relance_fautive, None, lambda t: SimpleNamespace(a_dire=None, raison="chiffre"))])
    assert dit.strip() and "15" not in dit, dit
