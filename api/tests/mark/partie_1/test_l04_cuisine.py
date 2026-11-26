"""[.mark] Chantier Partie 1, lot 4 : la cuisine du module commande (``services/commande/moteur.py``), ses règles en fonctions nommées.

Les essais passent par la vraie porte et la vraie source (montage ``porte_essai.py``), sur les cartes figées du banc A, sans modèle.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import conversation as CONV
from api.services.commande import moteur
from api.services.commande import phrases_du_manque as PM
from api.services.commande import panier as P
from api.services.commande.etat_pour_le_modele import ce_qui_manque_ensuite
from api.services.restauration.carte_et_allergenes import voir_un_article as VOIR

API = Path(__file__).resolve().parents[3]
PARIS = ZoneInfo("Europe/Paris")
NUIT_DU_18 = datetime(2026, 11, 18, 2, 40, tzinfo=PARIS)


def _statuts(r: dict) -> list[str]:
    return [x.get("statut_du_module") for x in r.get("resultats") or []]


def _faits(r: dict) -> str:
    return json.dumps(r, ensure_ascii=False, default=str)


from .aides_de_la_commande import (
    a_emporter as _a_emporter,
    jusqu_a_l_enregistrement as _jusqu_a_l_enregistrement,
    jusqu_au_recapitulatif as _jusqu_au_recapitulatif,
    oui_au_numero_dicte as _oui_au_numero_dicte,
    premier_article as _premier_article,
    question_posee as _q,
    refuser_la_proposition as _refuser_la_proposition,
)


# --------------------------------------------------------------------------- la proposition (L04-01, L04-02)


async def test_proposition_une_fois_question_numerotee(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await _premier_article(e)
    q = _q(e)
    assert q.get("type") == "proposition" and re.fullmatch(r"Q-\d+", q["id"]), r
    # C6 n° 11 (décision d'Evan 25/11 9 h 30) : le prix est un fait que le modèle dit dans sa question, plus une phrase que le code dit après elle
    assert "prix_dit_par_le_code_apres_ta_phrase" not in r and "en disant son prix" in (r.get("a_faire") or ""), r
    propose = q["article_propose"]
    assert propose and "euro" not in _faits(r).lower() and not re.search(r"\d+[,.]\d\d", json.dumps(r.get("question"))), r
    assert r["faits"]["proposition_a_poser"] == {"article": propose, "prix": q["prix"]} and isinstance(q["prix"], int), (r["faits"], q)  # un fait brut, jamais une phrase
    await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    r = await _premier_article(e, "regina")
    assert _q(e).get("type") != "proposition" and "prix_dit_par_le_code_apres_ta_phrase" not in r, r  # une fois par commande, jamais après un refus
    r = await e.tour("non c'est tout", c_est_tout=True)
    assert _q(e).get("type") == "relecture", r


async def test_oui_mais_plutot_x(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    q = _q(e)
    assert q.get("type") == "proposition" and q["article_propose"] != "Orangina", q
    await e.tour("oui, mais plutôt un Orangina", reponse={"question_id": q["id"], "sens": "accepte", "valeurs": ["Orangina"]})
    noms = [l["nom"] for l in e.p["lignes"]]
    assert any(n.startswith("Orangina") for n in noms) and not any(n.startswith(q["article_propose"]) for n in noms), noms


# --------------------------------------------------------------------------- l'adresse (L04-03, L04-13, L04-14)


async def test_seule_commune_livree_retenue(essai_de):
    e = await essai_de()
    source = e.source
    await source.charger_les_modes()
    p = P.nouveau()
    deux = moteur.Resultat("AMBIGU", {"candidats": [{"nom": "Senlis", "code_postal": "60300", "dans_une_zone": True},
                                                    {"nom": "Senlis", "code_postal": "62310", "dans_une_zone": False}]}, "")
    r = await moteur.retenir_la_seule_commune_livree(source, deux)
    assert r.statut == "RETENU" and r.faits["commune"]["code_postal"] == "60300", r
    aucune = moteur.Resultat("AMBIGU", {"candidats": [{"nom": "A", "dans_une_zone": True}, {"nom": "B", "dans_une_zone": True}]}, "")
    assert (await moteur.retenir_la_seule_commune_livree(source, aucune)) is aucune  # deux communes livrées : la question reste
    assert p["lignes"] == []
    assert "dans_une_zone" not in (API / "services" / "commande" / "porte.py").read_text(encoding="utf-8")  # une seule copie, dans la cuisine


async def test_livraison_exige_une_voie(essai_de):
    e = await essai_de()
    r = await e.tour("à livrer à Chantilly", mode_de_retrait="livraison", commune="Chantilly")
    manques = [x.get("manque") for x in r.get("resultats") or []]
    assert "voie" in manques and not e.p.get("zone"), r
    await e.tour("au 9 avenue du Bouteiller", adresse="9 avenue du Bouteiller")
    assert e.p.get("zone") and e.p["adresse"]["voie"] == "9 avenue du Bouteiller" and e.p["adresse"]["commune"] == "Chantilly", e.p.get("adresse")


async def test_hors_zone_propose_emporter(essai_de):
    e = await essai_de()
    r = await e.tour("en livraison au 8 rue Solférino à Compiègne", mode_de_retrait="livraison", adresse="8 rue Solférino", commune="Compiègne")
    hors = [x for x in r.get("resultats") or [] if x.get("statut_du_module") == "HORS_ZONE"]
    assert hors and {"mode": "emporter", "libelle": "à emporter"} in hors[0]["faits"].get("autres_modes", []), r


async def test_rue_de_beauvais_a_chantilly(essai_de):
    """C6 (conversation 5 de B12) : la commune dite à part situe l'adresse ; la rue « de Beauvais » n'est jamais la commune Beauvais."""
    e = await essai_de()
    await e.tour("en livraison au 4 rue de Beauvais à Chantilly", mode_de_retrait="livraison", adresse="4 rue de Beauvais", commune="Chantilly")
    assert e.p.get("zone") and e.p["adresse"]["commune"] == "Chantilly" and e.p["adresse"]["voie"] == "4 rue de Beauvais", e.p.get("adresse")


# --------------------------------------------------------------------------- la commande enregistrée (L04-04, L04-05)


async def test_commande_de_l_appel_apres_enregistrement(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e)
    avant = moteur.commande_de_l_appel(e.p)
    assert avant is not None
    ligne = e.p["lignes"][0]["n"]
    r = await e.tour("finalement deux margheritas", changer_quantite=[{"ligne": ligne, "quantite": 2}])
    apres = moteur.commande_de_l_appel(e.p)
    assert r["statut"] == "ENREGISTREE" and apres is not None and apres["numero"] != avant["numero"], r
    assert e.p["lignes"][0]["quantite"] == 2 and "remplace" in _faits(r), r
    statuts = await e.monde.c.fetch("SELECT numero::text, statut FROM mark.resto_commande ORDER BY cree_le")
    assert {s["numero"]: s["statut"] for s in statuts}[avant["numero"]] == "annulee", statuts  # une seule commande active pour l'appel (E30)


async def test_annuler_commande_enregistree(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    await _jusqu_a_l_enregistrement(e)
    numero = moteur.commande_de_l_appel(e.p)["numero"]
    await e.tour("finalement annulez-la", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)  # DC4 (Evan, 22/11) : en deux temps, la confirmation d'abord
    assert q["type"] == "annulation_enregistree" and not e.p.get("annulee"), e.p
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("annulee") and moteur.commande_de_l_appel(e.p) is None, e.retours[-1]
    assert await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", numero) == "annulee"
    # une caisse qui ne sait pas annuler : refusé avec la raison, rien ne change
    e2 = await essai_de("l00-carte-numerotee")
    e2.source.capacites = moteur_sans_annulation(e2.source.capacites)
    await _a_emporter(e2)
    await _premier_article(e2)
    await _refuser_la_proposition(e2)
    await _jusqu_a_l_enregistrement(e2)
    r = await e2.tour("annulez-la", annuler_une_commande_enregistree=True)
    assert "annulation_impossible" in _faits(r) and moteur.commande_de_l_appel(e2.p) is not None, r


def moteur_sans_annulation(capacites):
    from dataclasses import replace

    return replace(capacites, annulation=False)


# --------------------------------------------------------------------------- choix et retraits (L04-06, L04-07)


async def test_choix_sans_objet_ignore(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("un coca bien frais", ajouter=[{"article": "Coca-Cola", "quantite": 1, "supplements": ["bien frais"]}])
    assert "HORS_CARTE" not in _statuts(r) and any(l["nom"].startswith("Coca-Cola") for l in e.p["lignes"]), r
    assert "bien frais" in _faits(r), r  # signalé dans les faits (et noté sur la ligne : les notes libres sont permises)


async def test_retrait_en_note_sans_ingredients(essai_de):
    e = await essai_de("etoile-d-or")
    await _a_emporter(e)
    r = await e.tour("des nems au porc sans coriandre", ajouter=[{"article": "Nems au porc", "quantite": 1, "sans": ["coriandre"]}])
    ligne = next(l for l in e.p["lignes"] if l["nom"].startswith("Nems au porc"))
    assert "HORS_CARTE" not in _statuts(r) and "sans coriandre" in (ligne.get("note") or ""), r


# --------------------------------------------------------------------------- ouverture, fermeture, heure (L04-08 à L04-12)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_fermeture_dite_une_fois(essai_de):
    """Appel 2649 : deux opérations sur un lieu fermé (le mode, puis la fin) : la fermeture est dite une fois, le drapeau de l'appel est lu partout."""
    e = await essai_de()
    await e.monde.c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = false WHERE site_id = $1", e.monde.a)
    await e.monde.c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND fermeture <= '06:00'::time", e.monde.a)
    await e.source.charger_les_modes()
    p, regles = P.nouveau(), moteur.Reglages()
    r1 = await moteur.choisir_mode(e.source, p, regles, "emporter")
    r2 = await moteur.choisir_mode(e.source, p, regles, "livraison")
    r3 = await moteur.question_du_mode(e.source, p, "INCOMPLETE")
    # Lot 7b-C7a : le code n'écrit plus la phrase ; la fermeture est marquée dite au premier retour et la question du mode ne redonne plus ses faits
    assert r1.statut != "OK" and J.deja_dit(p, J.FERMETURE) and "raison" not in r3.faits and not any(r.suggestion for r in (r1, r2)), [r1, r2, r3]


async def test_pause_de_la_caisse_au_decroche(essai_de):
    e = await essai_de()
    await e.monde.c.execute("UPDATE mark.resto_reglage_type SET planifiee_permise = false WHERE site_id = $1", e.monde.a)
    await e.monde.c.execute(
        "INSERT INTO mark.resto_etat_caisse (site_id, mode) VALUES ($1, 'pause') ON CONFLICT (site_id) DO UPDATE SET mode = 'pause'", e.monde.a)
    await e.source.charger_les_modes()
    ouverture = await moteur.lire_l_ouverture(e.source)
    assert ouverture["ouvert"] is False and ouverture["etat"] in ("PAUSE", "FERME"), ouverture
    from api.services.pipecat.etat_ouverture import CLE_ETAT, etat_de_la_caisse_au_decroche

    contexte = etat_de_la_caisse_au_decroche({CLE_ETAT: "OUVERT"}, ouverture)
    assert contexte[CLE_ETAT] in ("PAUSE", "FERME"), contexte
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert not e.p.get("mode") or any(s not in ("OK",) for s in _statuts(r)), r


async def test_pause_sans_fin_sans_reprise_inventee(essai_de):
    e = await essai_de()
    await e.monde.c.execute(
        "INSERT INTO mark.resto_etat_caisse (site_id, mode) VALUES ($1, 'pause') ON CONFLICT (site_id) DO UPDATE SET mode = 'pause'", e.monde.a)
    ouverture = await moteur.lire_l_ouverture(e.source)
    assert ouverture["ouvert"] is False and not ouverture.get("reprise"), ouverture
    assert "phrase" not in ouverture, ouverture  # lot 7b-C7 : aucune phrase de fermeture, le modèle la dit d'après les faits


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_creneau_verifie_des_l_heure(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await e.tour("pour mercredi 25 novembre à 4 h", heure="mercredi 25 novembre à 4 h")
    assert not e.p.get("heure_voulue") and any(s not in ("OK", None) for s in _statuts(r)), r  # refusée dès qu'elle est dite
    q = _q(e)
    r = await e.tour("alors jeudi midi", heure="jeudi midi", **({"reponse": {"question_id": q["id"], "sens": "autre"}} if q else {}))
    assert str(e.p.get("heure_voulue") or "").startswith("2026-11-19T12:00"), (e.p.get("heure_voulue"), r)
    q = _q(e)
    r = await e.tour("non, plutôt jeudi à 4 h", heure="jeudi à 4 h", **({"reponse": {"question_id": q["id"], "sens": "autre"}} if q else {}))
    assert not e.p.get("heure_voulue"), r  # une correction repasse par la même vérification (E28)


@pytest.mark.parametrize("faire_monde", [NUIT_DU_18], indirect=True)
async def test_midi_apres_reouverture_jeudi(essai_de):
    e = await essai_de()
    await e.monde.c.execute("DELETE FROM mark.horaire WHERE site_id = $1 AND jour = 3", e.monde.a)  # fermé ce mercredi
    await _a_emporter(e)
    await e.tour("alors midi", heure="midi")
    assert str(e.p.get("heure_voulue") or "").startswith("2026-11-19T12:00"), e.p.get("heure_voulue")


# --------------------------------------------------------------------------- l'ordre, la taille, les lignes (L04-15 à L04-17)


async def test_article_garde_avant_le_mode(essai_de):
    e = await essai_de()
    await e.tour("une regina normale", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert not e.p["lignes"] and e.p.get("dits_en_attente"), e.retours[-1]
    await _a_emporter(e)
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Regina Normale", 1)], e.p["lignes"]


async def test_changer_la_taille(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e, "regina")
    await _refuser_la_proposition(e)
    n = e.p["lignes"][0]["n"]
    await e.tour("finalement en mega", changer_quantite=[{"ligne": n, "variante": "Mega"}])
    assert [l["nom"] for l in e.p["lignes"]] == ["Regina Mega"], e.retours[-1]
    r = await e.tour("en mega oui", changer_quantite=[{"ligne": n, "variante": "Mega"}])
    assert "RIEN_A_CHANGER" in _statuts(r), r


async def test_ligne_id_stable(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    await e.tour("une regina, une napoli et un calzone", ajouter=[
        {"article": "regina", "quantite": 1, "variante": "Normale"}, {"article": "napoli", "quantite": 1, "variante": "Normale"},
        {"article": "calzone", "quantite": 1, "variante": "Normale"}])
    numeros = {l["nom"]: l["n"] for l in e.p["lignes"]}
    await _refuser_la_proposition(e)
    await e.tour("enlevez la regina", retirer_article=[numeros["Regina Normale"]])
    assert {l["nom"]: l["n"] for l in e.p["lignes"]} == {k: v for k, v in numeros.items() if k != "Regina Normale"}
    await e.tour("et une margherita", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    assert next(l["n"] for l in e.p["lignes"] if l["nom"] == "Margherita Normale") not in numeros.values()  # jamais réutilisé


# --------------------------------------------------------------------------- la fin (L04-18 à L04-23, L04-26)


async def test_une_seule_relecture(essai_de):
    """B6 (audit des tests, groupe 14) : la règle (R3, R10 : la relecture est dite une fois, quand elle part), plus le texte du code source compté."""
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    q = await _jusqu_au_recapitulatif(e)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    await e.tour("0612345678", telephone="0612345678")
    await e.tour("Léa", prenom="Léa")
    await _oui_au_numero_dicte(e)
    assert e.p.get("enregistree") and sum("Je vous relis" in json.dumps(r, ensure_ascii=False) for r in e.retours) <= 1, e.retours[-1]


async def test_consigne_demandee_une_fois_en_livraison(essai_de):
    e = await essai_de()
    await e.tour("en livraison au 12 rue de la République à Senlis", mode_de_retrait="livraison", adresse="12 rue de la République", commune="Senlis")
    await _premier_article(e)
    q = await _jusqu_au_recapitulatif(e)
    demandes = [r for r in e.retours if '"consigne_livreur": "a_demander"' in json.dumps(r, ensure_ascii=False)]
    assert len(demandes) == 1 and _q(e).get("type") == "relecture", e.retours[-1]  # demandée avec le récapitulatif
    r = await e.tour("aucune consigne, oui c'est bon, par carte, 0612345678, Léa", reponse={"question_id": q["id"], "sens": "accepte"},
                     consigne_livreur="aucune", moyen_de_paiement="carte_bancaire", telephone="0612345678", prenom="Léa")
    await _oui_au_numero_dicte(e)
    r = e.retours[-1]
    assert e.p.get("enregistree") and e.p.get("consigne_livreur") == "aucune", r  # « aucune » est une réponse
    assert sum('"consigne_livreur": "a_demander"' in json.dumps(r, ensure_ascii=False) for r in e.retours) == 1  # une fois
    note = await e.monde.c.fetchval("SELECT note FROM mark.resto_commande ORDER BY cree_le DESC LIMIT 1")
    assert "aucune" not in (note or ""), note
    assert await e.monde.c.fetchval("SELECT consigne_livreur FROM mark.resto_commande ORDER BY cree_le DESC LIMIT 1") is None  # « aucune » n'est pas une consigne


async def test_consigne_n_est_pas_une_habitude(essai_de):
    e = await essai_de()
    await e.tour("en livraison au 12 rue de la République à Senlis, sonnez au deuxième", mode_de_retrait="livraison", adresse="12 rue de la République",
                 commune="Senlis", consigne_livreur="sonnez au deuxième")
    await _premier_article(e)
    await _jusqu_a_l_enregistrement(e, telephone="0612345678", prenom="Léa")
    client = await e.source.client("+33612345678")
    assert not (client or {}).get("consignes"), client  # la consigne de cette commande ne s'écrit pas sur la fiche du client
    note = await e.monde.c.fetchval("SELECT note FROM mark.resto_commande ORDER BY cree_le DESC LIMIT 1")
    assert "sonnez au deuxième" in (note or ""), note  # elle part avec la commande
    consigne = await e.monde.c.fetchval("SELECT consigne_livreur FROM mark.resto_commande ORDER BY cree_le DESC LIMIT 1")
    assert consigne == "sonnez au deuxième", consigne  # et à part, pour la caisse (lot 16), remplaçant le test qui lisait la fonction privée


async def test_rendu_dit_a_la_confirmation(essai_de):
    """C6 n° 5 (décision d'Evan 25/11 9 h 30) : le rendu n'est plus collé à la confirmation par le moteur ; la porte le dit après la phrase du modèle (motif ``rendu_de_monnaie``)."""
    from api.services.commande import porte
    from api.services.mots_dits import montant_en_lettres

    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    r = await _jusqu_a_l_enregistrement(e, moyen="especes", rendu_sur=50, telephone="0612345678", prenom="Léa")
    monnaie = e.p["enregistree"]["monnaie"]
    assert r["statut"] == "ENREGISTREE" and monnaie > 0 and "on vous rend" not in _faits(r), r
    suite = (e.fiche_de_l_appel.get(porte.CLE_TEXTES_DU_CODE) or {}).get("suffixe") or ""
    assert f"Sur votre billet de {montant_en_lettres(5000)}" in suite and montant_en_lettres(monnaie) in suite, suite


async def test_en_carte_un_seul_moyen(essai_de):
    e = await essai_de()
    await e.monde.c.execute("UPDATE mark.resto_reglage SET moyens_paiement = ARRAY['carte_livraison', 'especes'] WHERE site_id = $1", e.monde.a)
    await e.tour("en livraison au 12 rue de la République à Senlis", mode_de_retrait="livraison", adresse="12 rue de la République", commune="Senlis")
    await _premier_article(e)
    await _jusqu_a_l_enregistrement(e, moyen="carte_bancaire", telephone="0612345678", prenom="Léa", consigne_livreur="aucune")
    manques = [x.get("manque") for r in e.retours for x in r.get("resultats") or []]
    assert "paiement" not in manques and e.p["enregistree"], manques  # « en carte » n'est pas redemandé


def test_une_valeur_fermee_par_manque():
    from api.services.commande import etat_pour_le_modele as E

    # C7 B9 : plus de phrase par manque (le modèle la pose, Evan 25/11 8 h 45) ; chaque valeur que l'état peut rendre est un membre de la liste fermée, montré au modèle
    connu = {"modes": {"emporter": "à emporter", "livraison": "en livraison"}, "modes_a_adresse": ["livraison"]}
    p = P.nouveau()
    vus = set()
    etats = [
        {}, {"mode": "livraison"}, {"mode": "livraison", "commune_dite": "Senlis"}, {"mode": "livraison", "adresse": {"voie": "12 rue"}},
        {"mode": "emporter"}, {"mode": "emporter", "lignes": [{"n": 1, "attente": {"nom": "taille"}, "quantite": 1}]},
        {"mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}]},
        {"mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "relecture": {"x": 1}, "etape": "a_relire"},
        {"mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "relecture": {"x": 1}, "etape": "accordee"},
        {"mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "relecture": {"x": 1}, "etape": "accordee", "paiement": {"m": 1}},
        {"mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "relecture": {"x": 1}, "etape": "accordee", "paiement": {"m": 1},
         "client": {"telephone": "+33600000000"}},
    ]
    for plus in etats:
        manque, modes = E.ce_qui_manque({**p, **plus}, connu)  # M8 : la décision est un membre de la liste fermée, la phrase se fait après
        assert isinstance(manque, PM.Manque), manque
        assert E.ce_qui_manque_ensuite({**p, **plus}, connu).startswith(str(manque))  # le texte montré au modèle est celui d'avant
        vus.add(manque)
    assert E.ce_qui_manque_ensuite(p, connu) == "le mode de retrait (à emporter ou en livraison)"  # les modes ouverts : un fait, plus une phrase
    assert vus >= {PM.Manque.ARTICLES, PM.Manque.MODE, PM.Manque.PAIEMENT, PM.Manque.TELEPHONE, PM.Manque.PRENOM}
    assert ce_qui_manque_ensuite is E.ce_qui_manque_ensuite


# --------------------------------------------------------------------------- recherche, plantage, lignes supprimées (L04-21, L04-24, L04-27)


async def test_sans_oignons_par_ingredient(essai_de):
    e = await essai_de()
    await _a_emporter(e)
    r = await VOIR.chercher_par_ingredient(e.source, e.p, moteur.Reglages(), "oignon", contient=False)
    assert r.statut == "OK" and r.faits["articles"] and "Regina" in r.faits["articles"], r
    r = await VOIR.chercher_par_ingredient(e.source, e.p, moteur.Reglages(), "thon", contient=True)
    assert "Neptune" in r.faits["articles"], r
    retour = await e.lecture(sujet="article", article="quelles pizzas sans oignons")
    assert "Regina" in _faits(retour), retour
    r = await VOIR.chercher_par_ingredient(e.source, e.p, moteur.Reglages(), "chorizo", contient=True)
    assert r.faits["articles"] and r.faits["inconnus"] > 0, r  # donnée absente = inconnu (E21)
    r = await VOIR.chercher_par_ingredient(e.source, e.p, moteur.Reglages(), "sardines", contient=True)
    assert not r.faits["articles"] and r.faits["inconnus"] > 0 and r.suggestion == "", r  # le catalogue ne dit pas tout : « il n'y en a pas » ne se dit pas


async def test_choisir_mode_2641_t2(essai_de):
    e = await essai_de()
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    r = await e.tour("une pizza aux sardines, en livraison", ajouter=[{"article": "pizza aux sardines", "quantite": 1}], mode_de_retrait="livraison")
    assert not (r.get("faits") or {}).get("indisponible"), r
    await e.tour("au 12 rue de la République à Senlis", adresse="12 rue de la République", commune="Senlis")
    assert e.p.get("mode") == "livraison" and any(l["nom"] == "Margherita Normale" for l in e.p["lignes"]), (e.p, e.retours)
    assert not any(l["nom"].lower().startswith(("regina", "pizza")) for l in e.p["lignes"]), e.p["lignes"]  # rien de choisi à sa place (E12)


def test_moteur_sans_les_lignes_supprimees():
    source = "\n".join(f.read_text(encoding="utf-8") for f in sorted((API / "services" / "commande" / "moteur").glob("*.py")))  # le moteur est un paquet par sujet
    lecture = (API / "services" / "commande" / "lecture.py").read_text(encoding="utf-8")
    for nom in ("_rattacher_les_choix", "_remplacer_l_attente", "def _deja_dit(", "_poser_le_suspens", "choix_en_suspens", "_sans_la_taille",
                "_moities_separees", "_deja_au_panier", "async def ajouter(", "_vente_en_plus(", "en_plus is True"):
        assert nom not in source, nom
    for nom in ("deux_moities", "moities_apres_le_marqueur", "lire_les_articles"):
        assert f"def {nom}" not in lecture, nom
    assert "Qu'est-ce que je vous mets ?" not in source and "Prenons les articles un par un" not in source
