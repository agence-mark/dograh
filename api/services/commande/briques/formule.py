"""[.mark] La formule lue en entier (chantier Partie 1, lot 11 : briques FOR1 à FOR15 ; banc B10 à B12, ``formule_b12.py``).

Ce module tient ce qui est COMMUN aux briques des formules ; chaque brique garde sa règle dans ``for<N>.py``.

- **Une formule est un article à étapes** : chaque ligne de la formule devient un groupe ``role: "etape"`` (``min`` 1 si la ligne est obligatoire, ``max`` sa
  quantité) dont les options sont les déclinaisons des produits que la ligne accepte (FOR3 : ``inclus``, ``exclus``, ``prix_max``) ; une option d'étape porte le
  supplément de la ligne pour ce produit (FOR4) et **l'article du produit choisi** : ses groupes (ses ``enfants`` : la sauce du burger reste demandée), ses retraits,
  son alcool, sa TVA. Une étape à un seul choix possible est posée d'office (FOR8, FOR14).
- **Les tailles de la formule** (FOR6) et **le nombre de personnes** (FOR10) sont ses déclinaisons : un code par taille (``code_de_taille``), le prix de base plus
  l'écart, ou le prix pour N personnes.
- **Placer les choix** (``etapes_du_mot``) : chaque mot de ``composition`` est rangé sur l'étape dont il est un choix, par sa valeur ; un mot choix de deux étapes
  est refusé (jamais deviné), un mot hors de la ligne est refusé avec la raison et les choix de l'étape.
- **Les gardes de la fiche** (B10, B11) : un article de la fiche qui est aussi le choix d'une étape d'une formule de la même fiche n'est pas ajouté.

Aucun mot de restaurant : les noms viennent de la carte.
"""

from __future__ import annotations

from typing import Any, Callable

from api.db.bases_clients import recherche_liste
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche

SEPARATEUR_DE_TAILLE = "@"
ROLE_ETAPE = "etape"


# --------------------------------------------------------------------------- les lignes d'une formule


def ligne_normale(ligne: dict[str, Any]) -> dict[str, Any]:
    """Une ligne de formule avec ses valeurs par défaut : obligatoire, quantité 1, aucun filtre, aucun supplément."""
    return {
        "nom": ligne.get("nom") or "", "codes": list(ligne.get("codes") or []), "categories": list(ligne.get("categories") or []),
        "declinaison": ligne.get("declinaison"), "quantite": int(ligne.get("quantite") or 1), "obligatoire": ligne.get("obligatoire", True) is not False,
        "inclus": list(ligne.get("inclus") or []), "exclus": list(ligne.get("exclus") or []), "prix_max": ligne.get("prix_max"),
        "supplements": dict(ligne.get("supplements") or {}), "alternatives": list(ligne.get("alternatives") or []), "a_volonte": bool(ligne.get("a_volonte")),
    }


def code_de_taille(code: str, taille: str) -> str:
    """Le code de la ligne d'une formule à une taille (FOR6) ou pour un nombre de personnes (FOR10) : le code de la formule et le nom de sa déclinaison."""
    return f"{code}{SEPARATEUR_DE_TAILLE}{taille}"


def code_de_la_formule(code: str) -> tuple[str, str | None]:
    """``(code de la formule, nom de sa déclinaison ou None)``."""
    base, _, taille = code.partition(SEPARATEUR_DE_TAILLE)
    return base, (taille or None)


def declinaisons_de_la_formule(formule: dict[str, Any]) -> list[dict[str, Any]]:
    """Les déclinaisons d'une formule : ses tailles (FOR6), ses nombres de personnes (FOR10), sinon elle seule. ``prix`` : ce que la formule coûte à cette déclinaison."""
    from api.services.commande.briques import for6, for10

    tailles = for6.tailles_de(formule)
    if tailles:
        return [{"code": code_de_taille(formule["code_caisse"], t["nom"]), "nom": t["nom"], "prix": formule["prix"] + int(t.get("ecart") or 0), "type": "taille",
                 "taille": t} for t in tailles]
    personnes = for10.personnes_de(formule)
    if personnes:
        return [{"code": code_de_taille(formule["code_caisse"], str(n)), "nom": str(n), "prix": prix, "type": "personnes", "personnes": n} for n, prix in personnes]
    return [{"code": formule["code_caisse"], "nom": formule["nom"], "prix": formule["prix"], "type": None}]


def declinaison_de_la_formule(formule: dict[str, Any], code: str) -> dict[str, Any] | None:
    return next((d for d in declinaisons_de_la_formule(formule) if d["code"] == code), None)


def accepte(ligne: dict[str, Any], produit: dict[str, Any], declinaison: dict[str, Any], prix: int) -> tuple[bool, str | None]:
    """La ligne accepte-t-elle cette déclinaison de ce produit ? ``(oui, None)`` ; ``(non, None)`` : hors de la base de la ligne (pas sa catégorie ni ses codes) ;
    ``(non, "hors_sous_ensemble")`` : dans sa base, mais écartée par son filtre (FOR3)."""
    from api.services.commande.briques import for3

    code = declinaison["code_caisse"]
    dans_la_base = code in ligne["codes"] or (
        produit.get("categorie_id") in ligne["categories"] and (not ligne["declinaison"] or declinaison["nom"] == ligne["declinaison"])
    ) or any(code in (a.get("codes") or []) for a in ligne["alternatives"])
    if not dans_la_base and code not in ligne["inclus"]:
        return False, None
    if not for3.brique_for3_refuser_hors_liste(ligne, produit, declinaison, prix):
        return False, "hors_sous_ensemble"
    return True, None


# --------------------------------------------------------------------------- l'article d'une formule


def article_de_la_formule(
    carte: dict[str, Any], formule: dict[str, Any], ruptures: set[str], prix_de: Callable[[dict], int], vue_du_produit: Callable[[dict], dict],
) -> dict[str, Any]:
    """Ce que la cuisine lit d'une formule : ses déclinaisons (tailles, personnes), une étape par ligne, et pour chaque choix d'étape l'article du produit."""
    from api.services.commande.briques import for7, for8, for9, for12, for13, for14

    vues: dict[str, dict] = {}
    groupes = []
    for brute in formule["lignes"]:
        ligne = ligne_normale(brute)
        options, hors_ligne = [], []
        for p in carte["produits"]:
            for d in p["declinaisons"]:
                if not d["vendable"]:
                    continue
                oui, raison = accepte(ligne, p, d, prix_de(d))
                nom = p["nom"] + (f" {d['nom']}" if len(p["declinaisons"]) > 1 else "")
                if not oui:
                    if raison:
                        hors_ligne.append({"nom": nom, "code": d["code_caisse"], "produit": p["nom"]})
                    continue
                if p["id"] not in vues:
                    vues[p["id"]] = vue_du_produit(p)
                vue = vues[p["id"]]
                options.append({
                    "id": d["id"], "code": d["code_caisse"], "nom": nom, "prix": int(ligne["supplements"].get(d["code_caisse"], 0)), "retirable": False,
                    "par_defaut": False, "vendable": True, "rupture": d["code_caisse"] in ruptures, "synonymes": list(p.get("synonymes") or ()),
                    "article": p["id"], "produit": p["nom"], "declinaison": d["nom"], "enfants": vue["groupes"], "retirables": vue["retirables"],
                    "alcool": bool(p.get("alcool")), "tva_par_mode": p.get("tva_par_mode") or {},
                    "declinaisons_du_produit": [{"code": x["code_caisse"], "nom": x["nom"], "vendable": x["vendable"], "rupture": x["code_caisse"] in ruptures}
                                                for x in p["declinaisons"]],  # FOR6 : la même option à la déclinaison d'une taille
                    **for12.alternative_de(ligne, d["code_caisse"]),
                })
        groupes.append({
            "id": ligne["nom"], "nom": ligne["nom"], "min": ligne["quantite"] if ligne["obligatoire"] and not ligne["a_volonte"] else 0,
            "max": ligne["quantite"], "max_par_option": ligne["quantite"], "role": ROLE_ETAPE, "defaut": [], "options": options, "enfants": [],
            "hors_ligne": hors_ligne, "prix_max": ligne["prix_max"], "a_volonte": ligne["a_volonte"], "alternatives": ligne["alternatives"],
            "inclus": None, "prix_au_dela": None, "si_option": None,
        })
        if ligne["a_volonte"]:
            groupes[-1]["min"] = 1 if ligne["obligatoire"] else 0
        for o in for8.brique_for8_inclus_ou_vendu_seul(groupes[-1]):
            o["par_defaut"] = True  # FOR8, FOR14 : une étape à un seul choix possible est posée d'office, rien n'est demandé
    declinaisons = [
        {"code": d["code"], "nom": d["nom"], "prix": d["prix"], "vendable": formule["vendable"], "rupture": formule["code_caisse"] in ruptures,
         "type": d["type"], "libelle_question": None, "quotas": None, "taille": d.get("taille"), "personnes": d.get("personnes")}
        for d in declinaisons_de_la_formule(formule)
    ]
    categorie = next((c for c in carte["categories"] if c["id"] == formule.get("categorie_id")), None)
    return {
        "id": formule["id"], "nom": formule["nom"], "formule": True, "categorie": categorie["nom"] if categorie else None,
        "declinaisons": declinaisons, "groupes": groupes, "retirables": [], "ingredients": [], "allergenes": None, "genre": "m", "commun": False,
        "du_moment": False, "texte_du_jour": None, "description": "", "tailles": formule.get("tailles"),
        "indisponible": formule.get("indisponible"),  # lot 12 (PRX1)
        **for7.faits_de_la_formule(formule), **for9.faits_de_la_formule(formule), **for14.faits_de_la_formule(formule, groupes),
        **for13.faits_de_la_rubrique(carte, formule.get("categorie_id")),
    }


def est_une_etape(groupe: dict[str, Any]) -> bool:
    return groupe.get("role") == ROLE_ETAPE


# --------------------------------------------------------------------------- placer les choix (B10, FOR1, FOR2)


def du_groupe(c: dict[str, Any], groupe: dict[str, Any]) -> bool:
    """Ce choix est-il pris dans ce groupe ? Un choix d'étape porte son étape (``etape``) : deux étapes qui acceptent les mêmes produits (« Pizza 1 », « Pizza 2 »)
    ne se confondent jamais ; un autre choix se reconnaît à son code."""
    if est_une_etape(groupe) and c.get("etape") is not None:
        return c["etape"] == groupe["id"]
    codes = {o["code"] for o in groupe["options"]} | {d["code"] for o in groupe["options"] for d in o.get("declinaisons_du_produit") or []}
    return c["option_code"] in codes and not (est_une_etape(groupe) and c.get("etape") is not None)


def choix_d_etape(groupe: dict[str, Any], option: dict[str, Any], quantite: int = 1) -> dict[str, Any]:
    """Le choix posé sur une étape : le produit, son étape, ses choix et ses retraits (vides au départ)."""
    return {"option_code": option["code"], "nom": option["nom"], "quantite": quantite, "choix": [], "retires": [], "etape": groupe["id"]}


def _pris_dans(groupe: dict[str, Any], choix: list[dict[str, Any]]) -> int:
    return sum(int(c.get("quantite", 1)) for c in choix if du_groupe(c, groupe))


def etapes_du_mot(article: dict[str, Any], morceau: str, ouvertes: list[dict[str, Any]] | None = None, choix: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Où se range le mot dit : ``{"cible": id de l'étape}``, le refus (``raison``, ``choix``), ou ``None`` (aucune étape : un choix du plat, la cuisine le pose).
    Valeur seulement, jamais l'intention :
    - choix certain de deux étapes DIFFÉRENTES ou plus : ``choix_de_plusieurs_etapes`` (B10 : « demande-lui pour quelle étape ») ; deux étapes qui acceptent les
      mêmes choix (« Pizza 1 », « Pizza 2 ») ne sont pas un doute : le mot va à la première qui a encore de la place ;
    - aucune étape ne l'a, mais il est écarté par le filtre d'une ligne : ``hors_sous_ensemble`` (FOR3), avec les choix de cette étape ;
    ``ouvertes`` : seulement ces étapes (la réponse à une question d'étape) ; ``choix`` : ce que la ligne a déjà pris."""
    etapes = [g for g in (ouvertes if ouvertes is not None else article["groupes"]) if est_une_etape(g)]
    if not etapes:
        return None
    dans = []
    for g in etapes:
        elements = [Element(o["code"], o["nom"], tuple(o.get("synonymes") or ()), g["nom"]) for o in g["options"] if o["vendable"]]
        if elements and recherche_liste.chercher(elements, morceau)["statut"] == "RETENU":
            dans.append(g)
    if len({frozenset(o["code"] for o in g["options"]) for g in dans}) > 1:
        return {"raison": "choix_de_plusieurs_etapes", "valeur": morceau, "etapes": [g["nom"] for g in dans]}
    if dans:
        libre = next((g for g in dans if _pris_dans(g, choix or []) < g["max"]), dans[-1])
        return {"cible": libre["id"]}
    from api.services.commande.briques import for3

    return for3.hors_de_la_ligne(etapes, morceau)


def valeur_de(texte: str) -> str:
    return norme_de_recherche(texte or "")


# --------------------------------------------------------------------------- les gardes de la fiche (B10 § 2, B11 § 2 point 6)


def _le_mot_est_un_choix(groupe: dict[str, Any], mot: str) -> bool:
    elements = [Element(o["code"], o["nom"], tuple(o.get("synonymes") or ()), groupe["nom"]) for o in groupe["options"] if o["vendable"]]
    if not elements:
        return False
    trouve = recherche_liste.chercher(elements, mot)
    return trouve["statut"] == "RETENU"


def article_aussi_choix_d_une_etape(formule: dict[str, Any], mots_places: list[str], article: str) -> dict[str, Any] | None:
    """Dans la même fiche, ``article`` est le choix d'une étape de ``formule`` que ses mots de composition ne remplissent pas encore : rien n'est ajouté,
    refusé avec la raison et les deux choix (le code ne devine pas ; recopié de ``formule_b12.py``). ``None`` : pas de conflit."""
    for g in formule["groupes"]:
        if not est_une_etape(g) or g.get("a_volonte"):
            continue
        remplie = any(_le_mot_est_un_choix(g, m) for m in mots_places)
        if not remplie and _le_mot_est_un_choix(g, article):
            nom = formule["nom"].lower()
            return {"raison": "article_aussi_choix_d_une_etape", "article": article, "formule": formule["nom"], "etape": g["nom"], "rien_ajoute": True,
                    "choix": [f"dans le {nom} : la même fiche, avec {article} dans composition du {nom} et sans l'article à part",
                              f"en plus du {nom} : demande-lui d'abord son choix pour cette étape"],
                    "a_faire": "rien n'est ajouté : refais la fiche selon ce qu'elle a dit"}
    return None


def article_deja_choix_de_la_formule(formule: dict[str, Any], mots_places: list[str], article: str) -> dict[str, Any] | None:
    """Dans la même fiche, ``article`` est déjà un choix rangé (dit dans ``composition``) d'une étape de ``formule`` : rien n'est ajouté, refusé avec la raison et
    les deux choix (B11 point 6). ``None`` : pas de conflit."""
    voulu = valeur_de(article)
    for g in formule["groupes"]:
        if not est_une_etape(g):
            continue
        for m in mots_places:
            if valeur_de(m) == voulu and _le_mot_est_un_choix(g, m):
                f = formule["nom"].lower()
                return {"raison": "article_deja_choix_de_la_formule", "article": article, "formule": formule["nom"], "etape": g["nom"], "rien_ajoute": True,
                        "choix": [f"dans la {f} seulement : la même fiche, sans l'article à part", f"en plus de la {f} : demande-lui si elle le veut aussi à part"],
                        "a_faire": "rien n'est ajouté : refais la fiche selon ce qu'elle a dit"}
    return None
