"""[.mark] Plan final Partie 1, lot 7b-C1 : les textes de secours de la commande, un par refus du moteur.

Quand le modèle se tait deux fois sur un refus, le repli du code dit le refus (R = A, Evan, 25/11). Ce texte n'est JAMAIS donné au modèle : le modèle reçoit les faits du refus et
le dit avec ses mots. Chaque fonction ne lit que les faits publics du refus (ceux que la porte montre au modèle) : si le texte a besoin d'une valeur, c'est qu'un fait manque au refus,
jamais qu'il faut la lire ailleurs. Le module qui refuse écrit ses faits, puis ``_r(statut, faits, TS.nom(faits), manque)``.

Aucune règle du métier ici : un texte de secours ne fait que mettre des faits en mots.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from api.services.mots_dits import chiffres_en_lettres, liste_dite, liste_dite_et, montant_en_lettres, nombre_en_lettres, phrase_nette

Faits = Mapping[str, Any]

_UNITE_DITE = re.compile(r"(?<![\w,.])(\d+(?:[,.]\d+)?)\s*(cl|ml|l|g|kg)(?![\w])", re.IGNORECASE)
_UNITES_EN_MOTS = {"cl": "centilitre", "ml": "millilitre", "l": "litre", "g": "gramme", "kg": "kilo"}


def _unites_dites(texte: str) -> str:
    """« 33 cl » -> « 33 centilitres », « 1,5 l » -> « 1,5 litre » : une unité abrégée n'est pas une parole (SA-52, appel 2604)."""
    def dite(m: re.Match) -> str:
        valeur = float(m.group(1).replace(",", "."))
        mot = _UNITES_EN_MOTS[m.group(2).casefold()]
        return f"{m.group(1)} {mot}{'s' if valeur >= 2 else ''}"

    return _UNITE_DITE.sub(dite, texte or "")


def _noms(valeurs: list[Any]) -> list[str]:
    """Les noms d'une liste de faits : une chaîne telle quelle, ou le ``nom`` d'un petit dictionnaire (« plus proches » : nom et prix)."""
    return [str(v["nom"] if isinstance(v, Mapping) else v) for v in valeurs]


# --------------------------------------------------------------------------- #
# articles.py : choisir, ajouter, retirer
# --------------------------------------------------------------------------- #


def question_d_un_choix(faits: Faits) -> str:
    """SA-52 (appel 2604) : la question d'un choix est une PHRASE à dire, jamais une étiquette (« taille pour X : 33 cl… ») : « Quelle taille pour votre X : 33 centilitres,
    1,5 litre ou 2 litres ? ». Sans accord deviné (« comme » ne dépend pas du genre du nom du groupe). Faits : ``question`` et ``article_de_la_carte``."""
    q, article_nom = faits["question"], faits["article_de_la_carte"]
    if not q["options"]:
        return f"Il faut préciser : {q['nom']}."
    options = liste_dite([_unites_dites(o) for o in q["options"]])
    if q["type"] == "declinaison":
        return f"{q.get('libelle') or 'Quel choix'} pour votre {article_nom} : {options} ?"
    nom = re.sub(r"\s*\([^)]*\)", "", q["nom"]).strip() or q["nom"]
    nom = _unites_dites(nom[:1].lower() + nom[1:])
    combien = ""
    if q.get("max", 1) > 1:
        combien = f", {nombre_en_lettres(q['max'])} au choix" if q.get("min") == q["max"] else f", jusqu'à {nombre_en_lettres(q['max'])}"
    return f"Pour votre {article_nom}, qu'est-ce que vous prenez comme {nom}{combien} : {options} ?"


def n_est_plus_disponible(faits: Faits) -> str:
    """Un choix, une taille : ce que dit son nom."""
    return f"{faits['nom']} n'est plus disponible."


def maximum_atteint(faits: Faits) -> str:
    """Faits : ``groupe``, ``option`` et ``maximum_atteint`` (le nombre dit : le maximum du groupe, ou celui de l'option)."""
    return f"{faits['groupe']} : pas plus de {nombre_en_lettres(faits['maximum_atteint'])} ; {faits['option']} n'est pas pris."


def ne_se_prend_pas_avec_des_choix(faits: Faits) -> str:
    return f"{faits['article']} ne se prend pas avec des choix."


def vous_voulez_dire(faits: Faits) -> str:
    return "Vous voulez dire : " + liste_dite(list(faits["candidats"])) + " ?"


def option_hors_carte(faits: Faits) -> str:
    """L'option dite n'existe pas pour l'article : la plus proche (``plus_proches``) ou, à défaut, ce qui se choisit (``choix_possibles``, au plus quatre noms)."""
    proches = _noms(faits.get("plus_proches") or [])
    debut = f"Je n'ai pas « {faits['dit']} » pour {faits['article']}."
    if proches:
        return f"{debut} Le plus proche : {liste_dite(proches)}."
    possibles = list(faits.get("choix_possibles") or [])
    return f"{debut} Ce qui se choisit : {liste_dite(possibles)}." if possibles else debut


def pour_quelle_etape(faits: Faits) -> str:
    return f"Pour quelle étape : {liste_dite(list(faits['etapes']))} ?"


def pas_dans_la_formule(faits: Faits) -> str:
    return f"Je n'ai pas « {faits['valeur']} » dans {faits['article']}."


def sur_lequel(faits: Faits) -> str:
    return "Sur lequel : " + liste_dite(list(faits["candidats"])) + " ?"


def melange_refuse(faits: Faits) -> str:
    """Un menu à alternatives : l'appelant a mélangé deux contenus. Faits : ``article`` et ``choix`` (les alternatives, chacune dite en entier)."""
    return f"{faits['article']} : soit " + ", soit ".join(faits["choix"]) + "."


def valeur_parmi_les_choix(faits: Faits) -> str:
    """Une étape à taille liée : la valeur dite n'est pas admise ; ``choix`` dit ce qui l'est. Faits : ``valeur`` (sinon ``article``) et ``choix``."""
    return f"{faits.get('valeur') or faits['article']} : {liste_dite(list(faits.get('choix') or []))} ?"


# --------------------------------------------------------------------------- #
# articles.py : retraits, notes, code de remise
# --------------------------------------------------------------------------- #


def quoi_retirer(faits: Faits) -> str:
    return "Qu'est-ce qu'il faut retirer ?"


def sur_quelle_moitie(faits: Faits) -> str:
    """Faits : ``dit`` (l'ingrédient) et ``candidats`` (les moitiés, sans doublon dans le texte)."""
    return f"Sans {faits['dit']} sur quelle moitié : " + liste_dite(list(dict.fromkeys(faits["candidats"]))) + " ?"


def vous_voulez_retirer(faits: Faits) -> str:
    return "Vous voulez retirer : " + liste_dite(list(faits["candidats"])) + " ?"


def ne_se_retire_pas(faits: Faits) -> str:
    """Faits : ``dit``, ``article`` et ``retirables``."""
    return f"On ne peut pas retirer « {faits['dit']} » de {faits['article']}. On peut retirer : {liste_dite_et(list(faits['retirables']))}."


def notes_non_acceptees(faits: Faits) -> str:
    return "Je ne peux pas noter cette demande."


def code_inconnu(faits: Faits) -> str:
    return "Je ne connais pas ce code."


def code_de_remise_bon(faits: Faits) -> str:
    """Le code est bon mais la remise ne s'applique pas encore. Faits : ``code`` et ``remise`` (le nom de l'offre tel qu'écrit : le texte le dit)."""
    return f"Le code {faits['code']} est bon, {phrase_nette(chiffres_en_lettres(faits['remise']))} s'appliquera dès que votre commande y donne droit."


# --------------------------------------------------------------------------- #
# articles.py : trouver l'article, la ligne, la quantité
# --------------------------------------------------------------------------- #


def quel_rangement(faits: Faits) -> str:
    """Un mot de rangement dit seul : ``rangements`` (plusieurs) ou ``exemples`` (un seul, ses premiers éléments)."""
    noms = list(faits.get("rangements") or faits["exemples"])
    return f"Nous avons {liste_dite_et(noms)}" + (", entre autres" if not faits.get("rangements") else "") + " : qu'est-ce que je vous mets ?"


def article_introuvable(faits: Faits) -> str:
    """Faits : ``dit`` et ``plus_proches`` (sans doublon)."""
    proches = _noms(faits.get("plus_proches") or [])
    return f"Je ne trouve pas « {faits['dit']} »." + (f" Le plus proche : {liste_dite(proches)}." if proches else "")


def pas_servi_maintenant(faits: Faits) -> str:
    """L'article existe mais n'est pas servi en ce moment (fait ``pas_servi_maintenant``)."""
    return f"« {faits['dit']} » n'est pas disponible en ce moment."


def beaucoup_combien_exactement(faits: Faits) -> str:
    """Faits : ``quantite`` (celle qui a été dite) et ``quantite_max`` (le plafond d'une ligne)."""
    return f"{faits['quantite']}, c'est beaucoup : je vous mets combien exactement ?"


def combien_exactement(faits: Faits) -> str:
    return "Combien exactement ?"


def taille_en_rupture(faits: Faits) -> str:
    """Une taille en rupture à l'ajout : ce qui reste (``autres_tailles``) se dit avec."""
    reste = list(faits.get("autres_tailles") or [])
    return f"{faits['nom']} n'est plus disponible." + (f" Il reste : {liste_dite(reste)}." if reste else "")


def plus_au_catalogue(faits: Faits) -> str:
    return f"{faits['article']} n'est plus au catalogue."


def commande_vide(faits: Faits) -> str:
    return "Il n'y a encore rien dans la commande."


def pas_de_ligne(faits: Faits) -> str:
    return f"Il n'y a pas de ligne {faits['ligne']}."


def quelle_ligne(faits: Faits) -> str:
    return "Laquelle voulez-vous changer ?"


def laquelle(faits: Faits) -> str:
    return "Laquelle : " + liste_dite(list(faits["candidats"])) + " ?"


def pas_dans_la_commande(faits: Faits) -> str:
    return f"Je ne trouve pas « {faits['dit']} » dans la commande."


def que_change_t_on(faits: Faits) -> str:
    return "Qu'est-ce que je change ?"


# --------------------------------------------------------------------------- #
# prealables.py : l'ouverture, l'heure annoncée, l'adresse
# --------------------------------------------------------------------------- #


def pas_de_commande_en_ce_moment(faits: Faits) -> str:
    """Le secours d'une fermeture quand la source n'a pas écrit la sienne (``etat["phrase"]``, qui reste le texte de secours de ces refus : elle passe avant celui-ci)."""
    return "Nous ne prenons pas de commande en ce moment."


def minimum_de_l_adresse(faits: Faits) -> str:
    """Le minimum de commande de la zone : fait ``zone.minimum`` (en centimes)."""
    return f"Le minimum de commande pour cette adresse est de {montant_en_lettres(faits['zone']['minimum'])}."


def ce_sera_pret(faits: Faits) -> str:
    """L'heure annoncée : fait ``texte`` (« à dix-neuf heures trente »)."""
    return f"Ce sera prêt {faits['texte']}."


# --------------------------------------------------------------------------- #
# mode_et_adresse.py : un mode fermé qui se planifie
# --------------------------------------------------------------------------- #


def commande_pour(faits: Faits) -> str:
    """L'heure voulue est déjà gardée : fait ``heure_voulue_dite``."""
    return f"Commande pour {faits['heure_voulue_dite']}."


def preparer_pour_l_ouverture(faits: Faits) -> str:
    """La proposition du début d'appel : fait ``heure_proposee_dite`` (l'ouverture, dite)."""
    return f"Voulez-vous que je prépare votre commande pour {faits['heure_proposee_dite']} ?"


def quel_jour_et_quelle_heure(faits: Faits) -> str:
    return "Pour quel jour et à quelle heure ?"


# --------------------------------------------------------------------------- #
# enregistrement.py : le numéro, la fin
# --------------------------------------------------------------------------- #


def numero_pas_compris(faits: Faits) -> str:
    """Le numéro dicté ne se lit pas (fait ``numero_illisible``) : le même texte que les autres modules qui prennent un numéro, jamais une phrase du registre."""
    return "Je n'ai pas bien compris le numéro : vous pouvez le redire ?"


def je_vous_la_prepare_pour(faits: Faits) -> str:
    """La proposition de l'ouverture à la fin : fait ``heure_proposee_dite``."""
    return f"Je vous la prépare pour {faits['heure_proposee_dite']} ?"


# --------------------------------------------------------------------------- #
# reglement.py : le moyen de paiement, le montant, le billet
# --------------------------------------------------------------------------- #


def moyen_non_accepte(faits: Faits) -> str:
    """Faits : ``acceptes_dits`` (les libellés des moyens pris, dits)."""
    return "Ce moyen de paiement n'est pas accepté. On prend : " + liste_dite_et(list(faits["acceptes_dits"])) + "."


def quel_montant(faits: Faits) -> str:
    """Le montant dit n'est pas un montant (fait ``montant_illisible``) ou une part nulle ou négative."""
    return "Quel montant exactement ?"


def et_le_reste(faits: Faits) -> str:
    return "Et le reste, vous le réglez comment ?"


def sur_quel_reglement(faits: Faits) -> str:
    """Le billet ne vise aucun des règlements (fait ``moyen_du_billet``)."""
    return "Sur quel règlement le billet ?"


def billet_insuffisant(faits: Faits) -> str:
    """Faits : ``montant`` (à payer avec le billet) et ``billet``."""
    return "Le billet ne couvre pas ce règlement."


# --------------------------------------------------------------------------- #
# lecture.py : la commande lue, les offres, retrouver une commande
# --------------------------------------------------------------------------- #


def _dit(texte: str) -> str:
    """Une phrase écrite par une personne (une offre, un nom d'offre), prête à être dite : chiffres en lettres, un seul point final."""
    return phrase_nette(chiffres_en_lettres(texte))


def commande_vide_a_lire(faits: Faits) -> str:
    return "La commande est vide pour le moment."


def la_commande_se_lit(faits: Faits) -> str:
    """La commande lue, une lecture et non un refus : ``lignes_dites`` (ce qui est pris, déjà dit) est passé par le module qui lit, jamais posé dans les faits que reçoit le modèle ; puis ``total`` ou ``sous_total`` et ``minimum_non_atteint``, ``remises`` et ``total_remises``, ``livraison_offerte``."""
    phrase = f"Vous avez {faits['lignes_dites']}."
    minimum, total = faits.get("minimum_non_atteint"), faits.get("total")
    if minimum is not None:
        phrase += (
            f" Cela fait {montant_en_lettres(faits['sous_total'])}, il manque {montant_en_lettres(minimum['manque'])}"
            f" pour atteindre le minimum de {montant_en_lettres(minimum['minimum'])}."
        )
    elif total is not None:
        phrase += f" Cela fait {montant_en_lettres(total)}."
    remises = faits.get("remises") or []
    if remises and total is not None:
        phrase += f" Avec {liste_dite_et([_dit(r['nom']) for r in remises])}, vous économisez {montant_en_lettres(faits['total_remises'])}."
    if faits.get("livraison_offerte"):
        phrase += " La livraison est offerte."
    return phrase


def pas_d_offre(faits: Faits) -> str:
    return "Pas d'offre en ce moment."


def offres_en_ce_moment(faits: Faits) -> str:
    """Faits : ``remises`` = ``[{nom, phrase}]`` des offres en cours."""
    return phrase_nette("En ce moment : " + liste_dite_et([_dit(r["phrase"] or r["nom"]).rstrip(".") for r in faits["remises"]]) + ".")


def offre_atteinte(faits: Faits) -> str:
    """Faits : ``remise`` = ``{nom, phrase, choix, prix}``."""
    r = faits["remise"]
    debut = _dit(r["phrase"]) if r.get("phrase") else f"{_dit(r['nom'])} : vous y avez droit."
    return f"{debut} Qu'est-ce qui vous ferait plaisir : {liste_dite(list(r['choix']))} ?"


def offre_presque_atteinte(faits: Faits) -> str:
    return f"Il vous manque encore un article pour avoir {_dit(faits['remise']['nom'])}."


def seuil_presque_atteint(faits: Faits) -> str:
    r = faits["remise"]
    return f"Il vous manque {montant_en_lettres(r['manque'])} pour avoir {_dit(r['nom'])}."


def quel_numero_de_commande(faits: Faits) -> str:
    return "Quel est le numéro de la commande ?"


def commande_introuvable(faits: Faits) -> str:
    """Faits : ``cherche_par`` (``numero`` dit, ou ``telephone_affiche``)."""
    return "Je ne trouve pas de commande, ni aujourd'hui ni sous ce numéro."


def commandes_plusieurs(faits: Faits) -> str:
    """Faits : ``candidats`` = ``[{numero_court, quand_dit}]``."""
    dites = [f"la {c['numero_court']}" + (f" pour {c['quand_dit']}" if c.get("quand_dit") else "") for c in faits["candidats"]]
    return "Vous en avez plusieurs : " + liste_dite(dites) + ". Laquelle ?"


def commande_annulee(faits: Faits) -> str:
    return "Cette commande est annulée."


# --------------------------------------------------------------------------- #
# changement.py, porte.py : changer une commande enregistrée, l'heure proposée refusée
# --------------------------------------------------------------------------- #


def tout_retirer_c_est_annuler(faits: Faits) -> str:
    """Le changement viderait la commande (fait ``manque`` = ``articles``) : retirer toutes les lignes, c'est annuler."""
    return "Pour tout retirer, c'est une annulation."


def pour_quel_jour_alors(faits: Faits) -> str:
    """La proposition d'heure est refusée sans autre heure dite (fait ``heure_manquante``) : « alors » la redemande, de plus que la question du début."""
    return "Pour quel jour et à quelle heure, alors ?"


# --------------------------------------------------------------------------- #
# porte.py : la panne du moteur pendant la fiche
# --------------------------------------------------------------------------- #


def panne_avec_la_commande_transmise(faits: Faits) -> str:
    """La panne tombe en pleine commande et la commande est jointe au message de l'équipe (fait ``transmise_a_l_equipe``) : le rappel est promis."""
    return "Je n'arrive pas à enregistrer votre commande pour le moment. Je la transmets à l'équipe, qui vous rappelle."


def panne_sans_commande(faits: Faits) -> str:
    """La panne tombe sans commande à joindre : aucun rappel n'est promis."""
    return "Je n'arrive pas à faire cela pour le moment."


def panne_de_la_porte(faits: Faits) -> str:
    """Le texte de secours d'une panne : l'une des deux variantes, selon ``transmise_a_l_equipe``."""
    return panne_avec_la_commande_transmise(faits) if faits.get("transmise_a_l_equipe") else panne_sans_commande(faits)
