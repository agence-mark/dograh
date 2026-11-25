"""[.mark] Moteur de la commande : la proposition d'un article en plus (vente en plus) et sa réponse.

Le moteur est découpé par sujet (``moteur/__init__.py`` garde tous les noms publics) ; les gestes sont ceux de l'ancien ``moteur.py``, inchangés.
"""

from __future__ import annotations

from typing import Any

from api.db.bases_clients import recherche_liste
from api.services.commande import panier as P
from api.services.mots_dits import montant_en_lettres, nom_dit
from api.services.commande.resultat import Resultat
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.commande.moteur.socle import Appelant, Reglages, _avec, _dit, _r, cle_de_la_remise
from api.services.commande.moteur.prealables import chiffrer_le_panier
from api.services.commande.moteur.articles import _bloque_l_ajout, chercher_l_article, etat_apres_ajout, _un_article


def _peut_parler_d_offre(p: dict[str, Any], regles: Reglages, ref: str | None = None) -> bool:
    """T-08 : une offre se dit au plus ``mentions_de_remise`` fois par appel, jamais après un refus ; une offre déjà dite peut être suivie (« laquelle voulez-vous ? »)."""
    if p.get("remise_refusee"):
        return False
    return (ref is not None and J.deja_dit(p, cle_de_la_remise(ref))) or p.get("mentions_de_remise", 0) < regles.mentions_de_remise


async def proposer_un_article_en_plus(source: Source, p: dict[str, Any], regles: Reglages, chiffre: Resultat | None = None) -> Resultat | None:
    """Lot 4 (A18, M47, D23, D33) : UN article précis proposé en plus (une offre atteinte, sinon ce qui manque au panier, la meilleure vente d'abord),
    UNE fois par commande, jamais après un refus. Le code décide quoi et quand ; le modèle pose la question avec ses mots (``texte`` : « proposer X ») ;
    C6 n° 11 (décision d'Evan 25/11 9 h 30) : son prix (``prix``, en centimes, gardé dans la question) est un fait que le modèle dit dans sa question, exigé
    par la barrière ; une proposition offerte n'a pas de prix. ``repli`` : la proposition de B8, dite par le code seulement quand le modèle n'a aucune phrase (lot 6, E-b).
    ``None`` : rien à proposer, la commande continue."""
    if not regles.vente_en_plus or p.get("vente_en_plus_faite") or p.get("proposition_refusee") or not P.lignes_pretes(p) or P.a_completer(p):
        return None
    chercher = getattr(source, "proposer_en_plus", None)
    if chercher is None:
        return None
    if chiffre is None:
        chiffre = await chiffrer_le_panier(source, p, regles)
    if _bloque_l_ajout(chiffre):
        return None  # sous le minimum de la zone, on propose quand même (le minimum se juge à la fin, lot 17)
    p["vente_en_plus_faite"] = True  # une seule fois par commande, même quand rien n'est trouvé
    lignes = chiffre.faits.get("lignes") or []
    proposition = await chercher(p["mode"], lignes, _peut_parler_d_offre(p, regles))
    if proposition is not None and proposition.get("raison") == "offre" and not _peut_parler_d_offre(p, regles, proposition["offre"]["ref"]):
        proposition = await chercher(p["mode"], lignes, False)
    if proposition is None:
        return None
    nom = nom_dit(proposition["nom"], 1, genre=proposition.get("genre"), commun=bool(proposition.get("commun")))
    offerte = proposition["raison"] == "offre"
    faits = {"proposition": {k: proposition.get(k) for k in ("ref", "nom", "declinaison", "raison", "etoile", "plusieurs_tailles")}}
    if offerte:
        offre = proposition["offre"]
        if J.une_fois(p, cle_de_la_remise(offre["ref"])):
            p["mentions_de_remise"] = p.get("mentions_de_remise", 0) + 1
        faits["proposition"]["offre"] = offre["nom"]
        offert = "offerte" if proposition.get("genre") == "f" else "offert"
        repli = f"{_dit(offre['nom'])} : vous avez droit à {nom} {offert}. Je vous l'ajoute ?"
        prix = None
    else:
        repli = f"Avec cela, je vous propose {nom} à {montant_en_lettres(proposition['prix'])}. Je vous l'ajoute ?"
        prix = proposition["prix"]
    p["proposition_en_plus"] = {
        "ref": proposition.get("ref"), "nom": proposition["nom"], "choix": [c for c in (proposition.get("choix") or []) if isinstance(c, str)],
        "offerte": offerte, "prix": prix, "repli": repli,
    }
    return _r("INCOMPLETE", faits, f"proposer {proposition['nom']}" + (" offert" if offerte else ""), "vente_en_plus")


async def repondre_a_la_proposition(source: Source, p: dict[str, Any], regles: Reglages, appelant: Appelant, sens: str | None,
                                    variante: str | None = None) -> Resultat:
    """Lot 4 (M44, appels 2560, 2568) : la réponse à la proposition en plus. ``accepte`` ajoute l'article proposé ; « oui, mais plutôt X »
    (``variante`` : X, un article du catalogue) ajoute X à sa place ; un mot qui n'est pas un article du catalogue (« oui ») n'est jamais lu comme
    un article. ``refuse`` : rien n'est ajouté et plus rien n'est proposé. La proposition faite juste après le premier article laisse la commande
    continuer ; celle de la fin mène à la suite de la fin."""
    from api.services.commande.moteur.enregistrement import finaliser  # cycle voulu : enregistrement appelle proposition aussi, l'import se fait à l'appel
    proposee = p.pop("proposition_en_plus", None) or {}
    tot = bool(proposee.get("tot"))  # n° 46 bis : le moment de la proposition est dans la proposition
    r = _r("OK", {"rien_ajoute": True})
    if sens == "accepte" and proposee:
        nom = proposee["nom"]
        if variante and recherche_liste.normaliser(variante) != recherche_liste.normaliser(nom):
            autre = await chercher_l_article(source, variante, regles)
            if autre.statut == "RETENU":
                nom = variante
        deja = {l.get("n") for l in p["lignes"]}
        r = await _un_article(source, p, regles, 1, nom)
        if r.statut == "OK":
            if proposee.get("offerte"):
                # L06-41 (``banc-b2/guichet_candidat.py`` ``libelle``) : la ligne née de l'offre acceptée se relit « offerte » (le chiffrage, lui,
                # reste celui de la remise) ; une ligne qui existait déjà et qui gagne un de plus n'est pas marquée.
                for l in p["lignes"]:
                    if l.get("n") not in deja:
                        l["offerte_dite"] = True
            r = await etat_apres_ajout(source, p, regles, dict(r.faits))
    elif sens == "refuse":
        p["proposition_refusee"] = True
    if tot or r.statut not in ("OK",) or r.manque:
        return _avec(r, p)
    return await finaliser(source, p, regles, appelant)
