"""[.mark] Clôture de la Partie 1, lot B1 (audit du code M1, M4, M7) : la vie des questions et la phase de la commande, à UN seul endroit.

Forme (audit du code § 2, M1) :
* chaque question a un OBJET (la ligne qui attend, l'article dit en doute, l'article proposé, la relecture, le numéro qui s'affiche, l'heure proposée)
  et un numéro attaché à cet objet : reposée, elle garde son numéro (RC9) ;
* chaque type a une CONDITION lue dans l'état : la question n'existe que tant qu'elle est vraie (elle tombe avec son objet) ;
* à la fin de chaque fiche, ``choisir`` pose UNE question : la première, dans un ordre fixe, dont la condition est vraie (RC1) ; les autres ne sont
  pas perdues, l'état les redonne au tour suivant ;
* une fiche sans ``reponse`` quand une question est posée vaut « autre » pour elle, pour TOUS les types (``reponse_implicite``).

``phase`` (M7) : où en est la commande, à valeurs fermées, calculée ici seulement.
"""

from __future__ import annotations

from typing import Any

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import phrases_d_information as INFO
from api.services.actions_communes import registre_des_questions as RC
from api.services.commande import etape as ETAPE
from api.services.commande.briques import formule_a_etapes
from api.services.commande import panier as P
from api.services.commande import phrases_dites_par_le_code as PHRASES_DITES

# --------------------------------------------------------------------------- la phase (M7)

EN_COURS, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE = ETAPE.EN_COURS, ETAPE.A_RELIRE, ETAPE.ACCORDEE, ETAPE.ENREGISTREE, ETAPE.ANNULEE


def finie(p: dict[str, Any]) -> bool:
    return ETAPE.finie(p)


# --------------------------------------------------------------------------- le registre (M1)

TYPE_DU_NUMERO = "numero_affiche"
TYPE_DU_NUMERO_DICTE = "numero_dicte"  # DC10 : le numéro dicté relu avant l'enregistrement
TYPE_NOUVELLE_COMMANDE = "nouvelle_commande"  # DC5 : la commande annulée n'existe plus ; le code propose d'en passer une nouvelle
TEXTE_NOUVELLE_COMMANDE = INFO.NOUVELLE_COMMANDE_PROPOSEE  # proposée au modèle, jamais dite mot pour mot par le code (DC5 : un refus suivi d'une question)
TYPE_DE_L_ETAPE = "etape_formule"
CLE_ARTICLE_DIT = "article_dit"  # D24 : l'article de la fiche gardé avec une question d'hésitation
# DC4 (Evan, 22/11) : annuler une commande enregistrée se fait en deux temps ; la première question est celle-ci, dite par le code avec le montant
TYPE_ANNULATION = "annulation_enregistree"
TEXTE_ANNULATION_CONFIRMEE = PHRASES_DITES.TEXTE_ANNULATION_CONFIRMEE


def _montant_enregistre(p: dict[str, Any]) -> str | None:
    """Le total de la commande enregistrée (en centimes), en lettres ; ``None`` s'il n'est pas connu."""
    from api.services.mots_dits import montant_en_lettres

    total = (p.get("enregistree") or {}).get("total")
    try:
        return montant_en_lettres(int(total)) if total not in (None, "") else None
    except (TypeError, ValueError):
        return None


def texte_de_l_annulation(p: dict[str, Any]) -> str:
    """DC4, premier temps : la question d'annulation, avec le montant lu dans la commande enregistrée (le texte est dans ``phrases_dites_par_le_code``)."""
    montant = _montant_enregistre(p)
    return PHRASES_DITES.annulation_demandee(montant)


def texte_du_changement(p: dict[str, Any], question: str | None = None, montant: bool = True) -> str:
    """B2 (M3, TF2) : la commande enregistrée vient d'être changée en caisse : son nouveau total, dit par le code ; puis la question réglée après
    l'enregistrement (M108), comme la confirmation : la parole revient à la personne."""
    total = _montant_enregistre(p) if montant else None
    fait = PHRASES_DITES.changement(total)
    return " ".join(x for x in (fait, (question or "").strip()) if x)


def texte_dit_de_la_question(q: dict[str, Any], p: dict[str, Any]) -> str | None:
    """Ce que le code dit pour poser cette question : son texte ; la proposition, son repli (son texte n'est qu'une consigne). L'annulation n'a plus de forme à part (DC4, Q2 = A) :
    son texte, mis à jour avec le total d'AUJOURD'HUI de la commande, est celui que le repli dit quand le modèle se tait."""
    if q.get("type") == "proposition":
        return q.get("repli") or None
    return str(q.get("texte") or "").strip() or None


def demander_l_annulation(p: dict[str, Any]) -> None:
    """DC4 : « annulez ma commande » sur une commande enregistrée ouvre la question de confirmation ; rien n'est annulé avant le « oui »."""
    ouvrir(p, {"type": TYPE_ANNULATION, "texte": texte_de_l_annulation(p)})
# L'ordre fixe : on finit ce qui est commencé (le doute sur un article, sa taille, l'étape de sa formule) avant de proposer, de relire, puis d'identifier.
# L'heure proposée vient en tête : fermé, la commande pour plus tard est la première question (décision d'Evan, 21/11 : « dès le début de l'appel,
# le magasin est fermé, voulez-vous planifier pour l'ouverture à 18 h »).
ORDRE = (TYPE_ANNULATION, TYPE_NOUVELLE_COMMANDE, "heure_proposee", "ambiguite", "variante", TYPE_DE_L_ETAPE, "proposition", "relecture", TYPE_DU_NUMERO,
         TYPE_DU_NUMERO_DICTE)
CLE_DES_NUMEROS = RC.CLE_DES_NUMEROS
CLE_DES_QUESTIONS = RC.CLE_DES_QUESTIONS  # objet → question (texte, choix…) ; une seule est posée (``conversation.question_de``)


def _norme(x: Any) -> str:
    return " ".join(str(x or "").casefold().split())


def objet(q: dict[str, Any], p: dict[str, Any]) -> str:
    """L'objet d'une question (mécanisme commun : ``registre_des_questions.objet``)."""
    return RC.objet(TABLE, q, p)


def nommer(q: dict[str, Any], p: dict[str, Any]) -> str:
    """La naissance d'une question (mécanisme commun : ``registre_des_questions.nommer``) ; un doute prend son numéro d'hésitation ici, une seule fois."""
    return RC.nommer(TABLE, q, p)


def _objet_de_naissance(q: dict[str, Any], p: dict[str, Any], naitre: bool) -> str:
    t = q.get("type")
    if t in ("variante", TYPE_DE_L_ETAPE):
        attente = P.a_completer(p)
        # RC9 (tirées du contrôle long) : l'objet est la ligne DONT PARLE la question (l'article en question), pas toujours la première qui attend : « une regina » dite
        # pendant la taille de la margherita pose la question de la regina sous l'objet de la regina, jamais sous celui de la margherita
        voulue = next((l for l in attente if q.get("article_en_question") and _norme(l.get("nom")) == _norme(q["article_en_question"])), None) or (attente[0] if attente else None)
        return f"{t}:{(voulue.get('ref') or voulue.get('n')) if voulue else _norme(q.get('texte'))}"  # par article : deux lignes du même article attendent la MÊME question (une réponse les complète toutes)
    if t == "ambiguite":
        if naitre:
            CONV.de(p)["hesitations_nees"] = int(CONV.de(p).get("hesitations_nees") or 0) + 1
        return f"ambiguite:{int(CONV.de(p).get('hesitations_nees') or 0) + (0 if naitre else 1)}"
    if t == "proposition":
        return f"proposition:{_norme(q.get('article_propose'))}"
    return str(t)


def _dit_de_l_hesitation(q: dict[str, Any]) -> str | None:
    """La signature d'un doute : l'article tel que dit qui l'a ouvert (le mot, la quantité, ses précisions) ; ``None`` pour les autres types et sans lui."""
    if q.get("type") != "ambiguite":
        return None
    dit = q.get("article_dit")
    if not isinstance(dit, dict):
        return None
    return _norme(repr(sorted((k, v) for k, v in dit.items() if v not in (None, "", [], {}))))


def numero(p: dict[str, Any], cle: str) -> str:
    """Le numéro attaché à l'objet : donné une fois, gardé ensuite (RC9)."""
    return RC.numero(p, cle)


def condition(p: dict[str, Any], q: dict[str, Any]) -> bool:
    """La question existe tant que ceci est vrai DANS L'ÉTAT (audit du code M1, tableau des quatre propriétés)."""
    if q.get("type") == TYPE_ANNULATION:
        return ETAPE.courante(p) == ENREGISTREE
    if q.get("type") == TYPE_NOUVELLE_COMMANDE:
        return ETAPE.courante(p) == ANNULEE
    t = q.get("type")
    if ETAPE.courante(p) == ANNULEE or (ETAPE.courante(p) == ENREGISTREE and t not in ("variante", "ambiguite", TYPE_DE_L_ETAPE)):
        # enregistrée, la commande se change encore (E10) : la question d'une ligne changée se pose ; les autres sont closes
        return False
    if t in ("variante", TYPE_DE_L_ETAPE):
        # RC9 : la question tombe avec SA ligne (sa taille donnée par un changement), pas seulement quand plus aucune ligne n'attend
        cle = str(q.get("objet") or "").split(":", 1)[-1]
        return any(str(l.get("ref") or l.get("n")) == cle for l in P.a_completer(p)) if cle and cle != str(q.get("objet")) else bool(P.a_completer(p))
    if t == "proposition":
        article = _norme(q.get("article_propose"))
        dans_le_panier = any(_norme(l.get("nom")).startswith(article) for l in p.get("lignes") or []) if article else False
        return isinstance(p.get("proposition_en_plus"), dict) and not p.get("proposition_refusee") and not dans_le_panier
    if t == "heure_proposee":
        return not p.get("heure_voulue")
    if t == "relecture":
        return bool(P.lignes_pretes(p)) and not ETAPE.accord(p) and isinstance(p.get("relecture"), dict) and bool(p["relecture"])
    if t == TYPE_DU_NUMERO:
        # n° 44 : lue dans la commande et au journal du dit : le numéro n'est pas encore noté, et la dernière proposition n'a pas été refusée
        return (ETAPE.accord(p) and not (p.get("client") or {}).get("telephone")
                and J.fois(p, "numero_propose") > J.fois(p, "numero_refuse"))
    if t == TYPE_DU_NUMERO_DICTE:
        tel = (p.get("client") or {}).get("telephone")
        return ETAPE.accord(p) and bool(tel) and p.get("numero_dicte_accepte") != tel
    return True  # l'ambiguïté : posée tant qu'elle n'est pas résolue par sa réponse ou par un de ses candidats nommé (``porte``, case ajouter : elle quitte alors le registre)


def _texte_du_jour(p: dict[str, Any], q: dict[str, Any]) -> None:
    if q.get("type") == TYPE_ANNULATION:
        q["texte"] = texte_de_l_annulation(p)  # le total de la commande d'AUJOURD'HUI : elle a pu changer dans la même fiche


def _ferme(q: dict[str, Any], sens: str | None, r: Any, valeurs: list[str] | None) -> bool:
    """Lot 7a (n° 7) : cette réponse ferme-t-elle la question ? Lu sur le type, le sens et le statut du résultat, jamais sur un drapeau posé par la réponse.
    La relecture ne se ferme que sur un « oui » ; la question qui demande un « oui » ou un « non » (annulation, nouvelle commande, numéro) ne se ferme que sur l'un
    des deux ; l'heure proposée, le doute et l'étape restent posés quand la réponse n'a rien posé."""
    t = q.get("type")
    if t == "relecture":
        return sens == "accepte"
    if t in (TYPE_ANNULATION, TYPE_NOUVELLE_COMMANDE, TYPE_DU_NUMERO, TYPE_DU_NUMERO_DICTE):
        return sens in ("accepte", "refuse")
    if t == "heure_proposee":
        return not (sens == "autre" and not any(str(v).strip() for v in valeurs or []))  # le texte nettoyé, comme la réponse à l'heure (R5)
    if t == "ambiguite" and isinstance(q.get(CLE_ARTICLE_DIT), dict):
        rien_pose = r.statut == "OK" and bool((r.faits or {}).get("rien_ajoute"))
        return not (rien_pose and not (sens == "refuse" and not any(str(v).strip() for v in valeurs or [])))  # le texte nettoyé, comme pour l'heure
    if t == formule_a_etapes.TYPE_DE_LA_QUESTION:
        # la réponse à l'étape garde sa question quand elle ne choisit pas : son refus porte l'identifiant de la question (R3) ; le même mot rendu par le choix entre deux contenus la ferme
        return not (r.statut == "HORS_CARTE" and (r.faits or {}).get("raison") in ("choix_manquant", "plusieurs_choix") and (r.faits or {}).get("question") == q.get("id"))
    return True


# Ce que la commande dit de ses questions : l'ordre, la condition, l'objet de naissance, la signature du doute, le texte du jour, ce qui ferme.
TABLE = RC.Table(ordre=ORDRE, condition=lambda p, q: condition(p, q), objet_de_naissance=_objet_de_naissance, signature=_dit_de_l_hesitation,
                 rafraichir=_texte_du_jour, ferme=_ferme)

CLE_DERNIERE_FERMEE = RC.CLE_DERNIERE_FERMEE


def ouvrir(p: dict[str, Any], q: dict[str, Any] | None) -> None:
    """Une question née d'un résultat du moteur entre au registre (mécanisme commun)."""
    RC.ouvrir(TABLE, p, q)


def est_deja_ouverte(p: dict[str, Any], q: dict[str, Any] | None) -> bool:
    return RC.est_deja_ouverte(TABLE, p, q)


def fermee_sans_reponse_au_tour_d_avant(p: dict[str, Any], type_de_la_question: str) -> bool:
    return RC.fermee_sans_reponse_au_tour_d_avant(p, type_de_la_question)


def fermer(p: dict[str, Any], q: dict[str, Any] | None, sens: str | None = None) -> None:
    RC.fermer(TABLE, p, q, sens)


def proposer_une_nouvelle_commande(p: dict[str, Any]) -> None:
    """DC5 (Evan, 22/11) : un article dit après l'annulation n'entre pas ; le code le dit et propose une nouvelle commande (sa question au registre)."""
    ouvrir(p, {"type": TYPE_NOUVELLE_COMMANDE, "texte": TEXTE_NOUVELLE_COMMANDE})


def repartir(p: dict[str, Any]) -> None:
    """DC5 : « oui » à la nouvelle commande : un panier neuf, sur place (la même fiche de l'appel), le client, le mode et l'adresse gardés ; les numéros
    des questions continuent (jamais un numéro redonné à un autre objet)."""
    neuf = P.nouveau()
    for cle in ("client", "mode", "zone", "adresse", "connu", "vente_en_plus_faite", "proposition_refusee"):
        if cle in p:
            neuf[cle] = p[cle]
    for cle in (CLE_DES_NUMEROS, RC.CLE_DU_PROCHAIN):  # la conversation continue : jamais un numéro redonné
        if cle in CONV.de(p):
            CONV.de(neuf)[cle] = CONV.de(p)[cle]
    P.remplacer_par(p, neuf)


def tout_fermer(p: dict[str, Any]) -> None:
    """La commande repart de zéro (vidée) ou est annulée : toutes ses questions tombent, ses articles en doute et sa proposition avec elles."""
    CONV.de(p).pop(CLE_DES_QUESTIONS, None)
    p.pop("proposition_en_plus", None)
    CONV.poser_question(p, None)


def choisir(p: dict[str, Any], tour: int, de_l_etat: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """La question posée après la fiche (mécanisme commun, table de la commande)."""
    return RC.choisir(TABLE, p, tour, de_l_etat)


QUESTIONS_AVANT_LA_RELECTURE = ("ambiguite", "variante", TYPE_DE_L_ETAPE)  # ce qui se finit avant de relire : un article en doute, sa taille, l'étape de sa formule


def question_en_doute(p: dict[str, Any]) -> dict[str, Any] | None:
    """La première question ouverte au registre sur un article encore en doute (RC10) : tant qu'elle vit, la commande ne se relit pas."""
    for q in (CONV.de(p).get(CLE_DES_QUESTIONS) or {}).values():
        if isinstance(q, dict) and q.get("type") in QUESTIONS_AVANT_LA_RELECTURE and condition(p, q):
            return q
    return None


def reponse_implicite(fiche: dict[str, Any], question: dict[str, Any] | None, posee: bool) -> dict[str, Any]:
    return RC.reponse_implicite(fiche, question, posee)
