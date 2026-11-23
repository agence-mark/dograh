"""[.mark] Clôture de la Partie 1, note d'audit de Pierre du 23/11 (agent « commande ») : un test de règle par point, vu rouge avant le correctif.

* A2 : le remplacement d'une commande enregistrée se fait en tout ou rien ; un changement que l'enregistrement refuserait (plafond des titres,
  rupture relue en base, fermeture) est constaté AVANT d'annuler l'ancienne, qui reste la commande de l'appel.
"""

from __future__ import annotations

from datetime import timedelta

from api.db.bases_clients.restauration_commun import maintenant
from api.services.commande import moteur

from .test_l04_cuisine import _a_emporter, _faits, _jusqu_a_l_enregistrement, _premier_article, _refuser_la_proposition


async def _enregistree_en_titres(e):
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e, moyen="titre_restaurant")
    return moteur.commande_de_l_appel(e.p)


async def test_a2_changement_refuse_par_le_plafond_garde_la_commande_enregistree(essai_de):
    e = await essai_de()
    avant = await _enregistree_en_titres(e)
    assert avant is not None
    await e.monde.c.execute(
        "INSERT INTO mark.resto_reglage (site_id, plafond_titre_restaurant) VALUES ($1, $2) ON CONFLICT (site_id) DO UPDATE SET plafond_titre_restaurant = $2",
        e.monde.a, avant["total"],
    )
    ligne = e.p["lignes"][0]["n"]
    r = await e.tour("finalement deux margheritas", changer_quantite=[{"ligne": ligne, "quantite": 2}])
    reste = moteur.commande_de_l_appel(e.p)
    assert reste is not None and reste["numero"] == avant["numero"], (reste, avant, r)  # la commande de l'appel est toujours la première
    assert e.p["lignes"][0]["quantite"] == 1, e.p["lignes"]  # le panier redevient celui d'avant
    assert await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", avant["numero"]) != "annulee"
    assert "plafond" in _faits(r).casefold(), r  # et la raison est dite


async def test_a2_changement_refuse_par_une_rupture_garde_la_commande_enregistree(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e)
    avant = moteur.commande_de_l_appel(e.p)
    ligne = e.p["lignes"][0]
    code = await e.monde.c.fetchval("SELECT code_caisse FROM mark.resto_commande_ligne WHERE numero::text = $1 LIMIT 1", avant["numero"])
    # posée directement en base, sans passer par le cache de la carte : le chiffrage de l'appel ne la voit pas, l'enregistrement la relit (lot 5)
    await e.monde.c.execute(
        "INSERT INTO mark.resto_rupture (site_id, code_caisse, disponible, debut) VALUES ($1, $2, false, $3)", e.monde.a, code, (await maintenant(e.monde.c)) - timedelta(hours=1)
    )
    await e.tour("finalement deux margheritas", changer_quantite=[{"ligne": ligne["n"], "quantite": 2}])
    reste = moteur.commande_de_l_appel(e.p)
    assert reste is not None and reste["numero"] == avant["numero"], e.retours[-1]
    assert await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", avant["numero"]) != "annulee"


# --------------------------------------------------------------------------- A3 : l'allergie n'est jamais notée « donnée » sans avoir été dite


async def _gateau_et_allergie(essai_de):
    from api.tests.mark.partie_1.aides_briques import brique

    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "noix"  # le greffier la note
    return e


async def test_a3_fiche_vide_qui_porte_des_faits_d_allergie_fait_repasser_le_modele(essai_de):
    """Phrase libre retenue, puis fiche vide « C'est bien noté pour votre allergie » : les faits (le lait, les noix) n'ont pas été dits ; le modèle repasse."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await _gateau_et_allergie(essai_de)
    e.dit("au fait, je suis allergique aux noix")
    etat = PAROLE.etat_du_tour(e.fiche_de_l_appel)
    etat.rattrapage_a_joue = True  # la phrase écrite sans outil a déjà été retenue dans ce tour
    PAROLE.garder(e.fiche_de_l_appel, etat)
    r = await e.fiche()
    assert r.get(PAROLE.CLE_FAITS_A_DIRE) and r["faits"]["allergie"], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est bien noté pour votre allergie."})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.FAITS_A_DIRE, d


async def test_a3_des_faits_non_dits_ne_sont_pas_notes_donnes(essai_de):
    """Quand le code dit sa propre phrase à la place du modèle (le retour ne lui est pas rendu), les faits ne sont pas dits : l'allergie reste « à donner » et revient à la fiche suivante."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.commande import moteur
    from api.services.commande.porte import CLE_TEXTES_DU_CODE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await _gateau_et_allergie(essai_de)
    r = await e.tour("une salade et un gâteau", note_generale="allergique aux noix")
    assert r.get(PAROLE.CLE_FAITS_A_DIRE) and moteur.allergie_a_donner(e.p) is None, r  # donnés au retour : notés
    e.fiche_de_l_appel[CLE_TEXTES_DU_CODE] = {"avant": "Je vous relis : une salade. C'est bon ?"}  # le code dit sa phrase mot pour mot
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "x"})
    assert d.mode == PAROLE.A_DIRE_SEUL, d
    assert moteur.allergie_a_donner(e.p) == "noix", e.p.get("allergie_donnee")  # pas dits : rouverts


# --------------------------------------------------------------------------- A4 : une parenthèse qui porte un fait est dite


async def test_a4_une_parenthese_qui_porte_une_allergie_est_dite():
    from api.services.pipecat.appels_de_fonction_voix import PhraseQuiNEstQuUnAppel, retirer_appels_de_fonction

    for dit in ("(Attention : ce plat contient des arachides.) Autre chose ?", "Votre commande : (sans arachide) une salade thaï.",
                "(Allergie au lait) La margherita en contient.", "(Sans gluten) Une pizza ?"):
        assert await retirer_appels_de_fonction(dit) == dit, dit
    assert await PhraseQuiNEstQuUnAppel().filter("(Attention : ce plat contient des arachides.)") == "(Attention : ce plat contient des arachides.)"
    # la mise en scène reste tue : une liste fermée de formes
    assert await retirer_appels_de_fonction("(En attente) Très bien.") == "Très bien."
    assert await retirer_appels_de_fonction("Très bien. (Pause) Autre chose ?") == "Très bien. Autre chose ?"
    assert await retirer_appels_de_fonction("(Silence.) Bonjour.") == "Bonjour."
    assert await PhraseQuiNEstQuUnAppel().filter("(En attente de la réponse de l'appelant)") == ""


# --------------------------------------------------------------------------- 7 : une réponse écartée ne vaut jamais « autre » là où « autre » a un effet

from api.services.commande import registre as RQ  # noqa: E402


async def _annulee_avec_sa_question(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("non, et annulez tout", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"}, annuler_la_commande=True)
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert e.p["question"]["type"] == RQ.TYPE_NOUVELLE_COMMANDE, e.p.get("question")
    return e


async def test_dc5_article_redit_sans_reponse_garde_la_question(essai_de):
    """Pierre 7 : « euh attendez » (une fiche sans réponse) à « Voulez-vous en passer une nouvelle ? » ne ferme pas toute commande pour le reste de l'appel."""
    e = await _annulee_avec_sa_question(essai_de)
    q = e.p["question"]
    await e.tour("euh attendez, une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert (e.p.get("question") or {}).get("id") == q["id"], e.p.get("question")
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert RQ.phase(e.p) == RQ.EN_COURS, e.p


async def test_dc5_non_ne_pose_pas_de_drapeau_definitif(essai_de):
    """Pierre 7 : seul un « non » dit ferme la proposition d'une nouvelle commande ; un article dit plus tard la propose de nouveau."""
    e = await _annulee_avec_sa_question(essai_de)
    await e.tour("non merci", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"})
    assert not e.p.get("question"), e.p.get("question")
    await e.tour("finalement une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert (e.p.get("question") or {}).get("type") == RQ.TYPE_NOUVELLE_COMMANDE, e.p.get("question")


async def test_dc4_oui_avec_mauvais_numero_garde_la_question(essai_de):
    """Pierre 7 : le « oui » à « Vous êtes sûr de vouloir annuler… ? » avec un mauvais numéro n'abandonne pas l'annulation : la question reste posée."""
    e = await essai_de()
    await _enregistree_en_titres(e)
    numero = moteur.commande_de_l_appel(e.p)["numero"]
    await e.tour("finalement annulez-la", annuler_une_commande_enregistree=True)
    q = e.p["question"]
    assert q["type"] == RQ.TYPE_ANNULATION, q
    await e.tour("oui", reponse={"question_id": "Q-99", "sens": "accepte"})  # un mauvais numéro
    assert (e.p.get("question") or {}).get("id") == q["id"] and moteur.commande_de_l_appel(e.p) is not None, e.p.get("question")
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("annulee") and await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", numero) == "annulee"


async def test_hesitation_tombe_quand_un_de_ses_candidats_est_pris(essai_de):
    """Pierre 7 : « une salmone » (deux candidats) puis la personne nomme l'un d'eux sans répondre à la question : l'hésitation tombe, « c'est tout » n'attend plus."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = e.p["question"]
    assert q["type"] == "ambiguite" and len(q.get("choix") or []) >= 2, q
    candidat = q["choix"][0]
    await e.tour(f"{candidat}", ajouter=[{"article": candidat, "quantite": 1, "variante": "Normale"}])
    assert not any(x.get("type") == "ambiguite" for x in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values()), e.p.get(RQ.CLE_DES_QUESTIONS)


# --------------------------------------------------------------------------- 8 : un article redit n'est pas compté deux fois


async def test_article_remis_avec_sa_taille_complete_la_ligne(essai_de):
    """Pierre 8 : « une Regina », la taille est demandée ; le modèle range « normale » dans ``ajouter`` avec la variante, sans ``reponse`` : c'est la réponse, pas un ajout."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert e.p["question"]["type"] == "variante", e.p.get("question")
    await e.tour("normale", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Regina Normale", 1)], e.p["lignes"]
    assert not any(l.get("attente") for l in e.p["lignes"]), e.p["lignes"]


async def test_article_en_doute_redit_une_seule_question(essai_de):
    """Pierre 8 : « une salmone » (deux candidats) redit pendant l'hésitation : le même mot ouvre la même question, un seul article en attente."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = e.p["question"]
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    ouvertes = [x for x in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values() if x.get("type") == "ambiguite"]
    assert len(ouvertes) == 1 and e.p["question"]["id"] == q["id"], (ouvertes, e.p["question"])


# --------------------------------------------------------------------------- 9 : « lait et poisson » : tous les allergènes dits sont vérifiés


async def test_lire_deux_allergenes_sans_les_deux(essai_de):
    """Pierre 9 : ``lire {sujet: allergenes, a_eviter: "lait et poisson"}`` ne rend « sans » que ce qui l'est pour les DEUX ; « lait et kiwi » : le kiwi n'est jamais « sûr »."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    seul_lait = await e.lecture(sujet="allergenes", a_eviter="lait")
    deux = await e.lecture(sujet="allergenes", a_eviter="lait et poisson")
    sans_les_deux = (deux.get("faits") or {}).get("sans", [])
    assert set(sans_les_deux) <= set((seul_lait.get("faits") or {}).get("sans", [])), (seul_lait, deux)  # jamais plus d'articles « sans » avec un allergène de plus
    assert "Margherita" not in sans_les_deux and "Regina" not in sans_les_deux, sans_les_deux
    assert sorted((deux.get("faits") or {}).get("codes") or []) == ["lait", "poissons"], deux  # les deux sont lus, pas le dernier seul
    kiwi = await e.lecture(sujet="allergenes", a_eviter="lait et kiwi")
    assert (kiwi.get("faits") or {}).get("sans") == [] and (kiwi.get("faits") or {}).get("inconnus", 0) > 0, kiwi  # un mot inconnu : rien n'est « sûr »


async def test_lire_un_article_avec_deux_allergenes_les_verifie_tous(essai_de):
    """Pierre 9 : « lait et kiwi » sur le Coca : le lait est lu, le kiwi (hors des quatorze) est « à confirmer par l'équipe », jamais passé sous silence."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.lecture(sujet="allergenes", article="Coca-Cola", a_eviter="lait et kiwi")
    faits = r.get("faits") or {}
    assert faits.get("signalement") == "plusieurs" and faits.get("a_confirmer_par_l_equipe") is True, r
    from api.tests.mark.partie_1.aides_briques import brique

    e2 = await brique(essai_de, "INF6")
    deux = await e2.lecture(sujet="allergenes", article="Gâteau aux noix", a_eviter="noix et lait")
    par = {x["code"]: x["signalement"] for x in (deux.get("faits") or {}).get("par_signalement") or []}
    assert len(par) == 2 and "present" in par.values(), deux  # chacun est vérifié : celui que l'article contient est dit


# --------------------------------------------------------------------------- 10 : un moyen redit efface le partage


async def test_moyen_redit_efface_le_partage(essai_de):
    """Pierre 10 : « 5 euros en titres, le reste en carte », puis « finalement tout en espèces » : le partage, la part et le billet ne restent pas (enregistré 25 + 7 avant)."""
    from .test_l04_cuisine import _jusqu_au_recapitulatif

    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    q = await _jusqu_au_recapitulatif(e)
    await e.tour("oui, 5 euros en titres et le reste en carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="titre_restaurant", part=5, moyen_reste="carte_bancaire")
    assert e.p["fin_dite"].get("part") and e.p["fin_dite"].get("moyen_reste"), e.p["fin_dite"]
    await e.tour("finalement tout en espèces", moyen_de_paiement="especes")
    assert "part" not in e.p["fin_dite"] and "moyen_reste" not in e.p["fin_dite"], e.p["fin_dite"]
    assert not (e.p.get("paiement") or {}).get("part") and not (e.p.get("paiement") or {}).get("moyen_reste"), e.p.get("paiement")


# --------------------------------------------------------------------------- 11 : phrases abîmées par le retrait du nom


def test_11_le_nom_n_abime_pas_une_phrase():
    from api.services.workflow.parole_de_la_fiche import noms_de_la_personne, sans_le_nom

    assert sans_le_nom("C'est noté pour le dîner, je vérifie le créneau.", ["Le Goff"]) == "C'est noté pour le dîner, je vérifie le créneau."
    assert sans_le_nom("Une reine, c'est noté.", ["Reine"]) == "Une reine, c'est noté."
    assert sans_le_nom("C'est noté, Le Goff.", ["Le Goff"]) == "C'est noté."  # le nom entier, en position d'adresse, part toujours
    assert sans_le_nom("Reine, c'est noté.", ["Reine"]) == "C'est noté."
    # le prénom ne se lit que dans ses chemins : ni la zone de livraison, ni un article proposé
    assert noms_de_la_personne({"client": {"prenom": "Léa"}, "zone": {"nom": "Senlis"}, "adresse": {"nom": "Rue"}}) == ["Léa"]
    assert noms_de_la_personne({"prenom": "Léa", "nom": "Martin"}) == ["Léa", "Martin"]  # la réservation : à la racine


async def test_11_proposition_par_fiche_vide_dite_avec_son_prix(essai_de):
    """Pierre 11 : la proposition née dans ce tour a déjà été donnée au modèle ; il la pose par une fiche vide : sa phrase est dite avec le prix du code, jamais une fiche sans prix."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await essai_de()
    await _a_emporter(e)
    cases = {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("une margherita normale", **cases)
    assert (e.p.get("question") or {}).get("type") == "proposition", e.p.get("question")
    d1 = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Très bien.", **cases})
    assert d1.mode == PAROLE.SECOND_PASSAGE, d1
    prix = (e.fiche_de_l_appel.get(PAROLE.CLE_ETAT_DU_TOUR) or {}).get("suffixe")
    assert prix, e.fiche_de_l_appel.get(PAROLE.CLE_ETAT_DU_TOUR)  # le prix du code attend d'être dit après la phrase du modèle
    r2 = await e.fiche()
    d2 = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r2, {"a_dire": "Avec cela, je vous propose un Coca-Cola, je vous l'ajoute ?"})
    assert d2.mode == PAROLE.A_DIRE_SEUL and prix in (d2.a_dire or ""), d2


# --------------------------------------------------------------------------- 12 : les plus petits


async def test_12_poids_le_maximum_vaut_pour_le_poids_total(essai_de):
    """Pierre 12 : ``quantite: 20, poids: "5 kg"`` n'est plus accepté (100 kg, 1 800 €) ; le prix dit pour plusieurs portions est le total de la ligne."""
    from api.tests.mark.partie_1.aides_briques import brique
    from .test_l13_briques import _ajouter, _objets_charges, _suffixe

    e = await brique(essai_de, "QTE1")
    await _objets_charges(e)
    r = await _ajouter(e, "vingt portions de cinq kilos de houmous", article="houmous", quantite=20, poids="5 kg")
    assert "poids_au_dessus_du_maximum" in _faits(r) and not e.p["lignes"], _faits(r)
    await _ajouter(e, "deux fois trois cents grammes de houmous", article="houmous", quantite=2, poids="trois cents grammes")
    assert _suffixe(e) == "deux fois trois cents grammes de houmous : dix euros quatre-vingts.", _suffixe(e)  # 2 x 5,40 €


def test_12_un_montant_dit_sans_le_mot_euros_est_de_l_argent():
    """Pierre 12 (C2) : « 25 € » et « 25 en titres » couvrent la part ou le billet de 25 (avant : refusés, l'impasse du plafond revenait) ; « deux enfants » reste un nombre."""
    from api.services.actions_communes.forme import valeur_dite_par_elle, valeurs

    assert valeur_dite_par_elle(25, "part", ["25 € en titres, le reste en carte"]) and valeur_dite_par_elle(25, "part", ["25 en titres"])
    assert valeurs("j'ai deux enfants") == [("2", "nombre")] and not valeur_dite_par_elle(2, "part", ["j'ai deux enfants"])


def test_12_l_annonce_non_fondee_ne_confond_ni_la_commande_ni_l_allergie():
    from api.services.workflow.parole_de_la_fiche import annonce_non_fondee

    vide = {"lignes": [], "mode": None, "enregistree": None, "annulee": False}
    assert annonce_non_fondee("Votre commande est passée.", vide)
    assert annonce_non_fondee("Votre commande est bien passée, merci.", vide)
    assert not annonce_non_fondee("J'ai bien enregistré votre allergie au lait.", vide)
    assert annonce_non_fondee("J'ai bien enregistré votre commande.", vide)
    assert not annonce_non_fondee("Votre commande est passée.", {**vide, "enregistree": {"numero": "A1"}})


def test_12_une_duree_dite_en_mots_passe_la_garde_des_chiffres():
    """Pierre 12 (P1) : « dans un quart d'heure », « une demi-heure », « dans une heure » : des durées que le code dit, retenues comme « dans vingt minutes »."""
    from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase

    for phrase in ("Ce sera prêt dans un quart d'heure.", "Comptez une demi-heure.", "C'est prêt dans une heure.", "Dans trois quarts d'heure."):
        assert chiffre_dans_la_phrase(phrase), phrase
    assert not chiffre_dans_la_phrase("Je vous mets une pizza, c'est noté.")


async def test_12_la_marque_arguments_illisibles_arrive_a_la_porte(essai_de):
    """Pierre 12 (P5) : ``arguments_permis`` ne gardait que les paramètres déclarés : la marque posée par le filet du cerveau était supprimée et la fiche illisible s'exécutait vide (R1 : le test d'avant passait la marque directement)."""
    from api.services.integrations.connectors.actions.commande import COMMANDE
    from api.services.integrations.connectors.execution import arguments_permis

    arguments = arguments_permis(COMMANDE.action("fiche"), {"arguments_illisibles": True})
    assert arguments == {"arguments_illisibles": True}, arguments
    e = await essai_de()
    e.dit("une pizza")
    r = await e.fiche(**arguments)
    assert r["statut"] == "REJETEE" and r["raison"] == "arguments_illisibles", r


async def test_12_un_montage_qui_echoue_ferme_la_connexion_de_l_appel(monkeypatch):
    """Pierre 12 : si le montage de l'appel à la voix lève entre le chargement et le ``try/finally`` de fin, la connexion du chargement est fermée (jamais fermée depuis A5)."""
    import pytest

    from api.services.pipecat import run_pipeline as RP
    from api.services.restauration import memoire_de_l_appel as M

    class Connexion:
        fermee = False

        def is_closed(self):
            return self.fermee

        async def close(self):
            self.fermee = True

    connexion = Connexion()
    M._APPELS["777"] = M.AppelOuvert("base_essai", connexion=connexion)

    async def corps(*args, **kwargs):
        raise RuntimeError("montage en échec")

    monkeypatch.setattr(RP, "_run_pipeline_corps", corps)
    try:
        with pytest.raises(RuntimeError):
            await RP._run_pipeline_impl(None, 1, 777, 1)
        assert connexion.fermee and M.appel_ouvert(777) is None
    finally:
        M._APPELS.pop("777", None)


async def test_f_dc3_et_dc6_ensemble_un_non_merci_apres_un_hein_n_est_pas_la_fin(essai_de):
    """Pierre F : la proposition fermée par « hein ? » (DC3), puis « non merci » au tour suivant (la réponse à la proposition redite par le modèle) n'est pas lue comme la fin de la prise (DC6)."""
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    q = e.p["question"]
    assert q["type"] == "proposition", q
    await e.tour("hein ?")  # un tour sans « oui » : la proposition est fermée (DC3)
    assert not e.p.get("question") or e.p["question"].get("type") != "proposition", e.p.get("question")
    await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})  # le « non » répond à la proposition que le modèle vient de redire
    assert (e.p.get("question") or {}).get("type") != "relecture" and not e.p.get("relecture"), e.p.get("question")  # la relecture ne part pas : elle n'a pas fini
    # DC6 reste : un « non merci » seul, plus tard, à « autre chose ? » est la fin
    await e.tour("non merci", reponse={"question_id": "Q-99", "sens": "refuse"})
    assert (e.p.get("question") or {}).get("type") == "relecture", e.p.get("question")
