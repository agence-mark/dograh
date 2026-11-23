"""[.mark] Clôture de la Partie 1, lot B1 (audit du code M1, M4, M7) : la vie des questions et la phase de la commande, à UN seul endroit.

Avant : la vie d'une question (ouverture, garde, fermeture, numéro) était décidée à une douzaine d'endroits de la porte, avec trois exceptions devant
la même barrière, une file d'attente, une seconde liste d'hésitations et une remise en place à deux conditions différentes ; une question reposée
changeait de numéro (DF10) ; un changement dit pendant une proposition était refusé en entier (DF1).

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

from api.services.commande import panier as P

# --------------------------------------------------------------------------- la phase (M7)

VIDE, EN_COURS, A_RELIRE, ACCORDEE, ENREGISTREE, ANNULEE = "vide", "en_cours", "a_relire", "accordee", "enregistree", "annulee"


def phase(p: dict[str, Any]) -> str:
    """Où en est la commande : une seule réponse, lue partout (avant : redéduite de dix drapeaux à chaque endroit)."""
    if p.get("annulee"):
        return ANNULEE
    if p.get("enregistree"):
        return ENREGISTREE
    if p.get("relecture_acceptee"):
        return ACCORDEE
    if isinstance(p.get("relecture"), dict) and p["relecture"]:
        return A_RELIRE
    if p.get("lignes") or p.get("mode") or p.get("dits_en_attente"):
        return EN_COURS
    return VIDE


def finie(p: dict[str, Any]) -> bool:
    return phase(p) in (ENREGISTREE, ANNULEE)


# --------------------------------------------------------------------------- le registre (M1)

TYPE_DU_NUMERO = "numero_affiche"
TYPE_DU_NUMERO_DICTE = "numero_dicte"  # DC10 : le numéro dicté relu avant l'enregistrement
TYPE_NOUVELLE_COMMANDE = "nouvelle_commande"  # DC5 : la commande annulée n'existe plus ; le code propose d'en passer une nouvelle
TEXTE_NOUVELLE_COMMANDE = "Votre commande est annulée, je ne peux plus rien y ajouter. Voulez-vous en passer une nouvelle ?"
TYPE_DE_L_ETAPE = "etape_formule"
# DC4 (Evan, 22/11) : annuler une commande enregistrée se fait en deux temps ; la première question est celle-ci, dite par le code avec le montant
TYPE_ANNULATION = "annulation_enregistree"
TEXTE_ANNULATION_CONFIRMEE = "Je vous confirme l'annulation de votre commande."


def _montant_enregistre(p: dict[str, Any]) -> str | None:
    """Le total de la commande enregistrée (en centimes), en lettres ; ``None`` s'il n'est pas connu."""
    from api.services.mots_dits import montant_en_lettres

    total = (p.get("enregistree") or {}).get("total")
    try:
        return montant_en_lettres(int(total)) if total not in (None, "") else None
    except (TypeError, ValueError):
        return None


def texte_de_l_annulation(p: dict[str, Any]) -> str:
    """« Vous êtes sûr de vouloir annuler votre commande de vingt et un euros quatre-vingts ? » (DC4) : le montant lu dans la commande enregistrée."""
    montant = _montant_enregistre(p)
    return f"Vous êtes sûr de vouloir annuler votre commande{f' de {montant}' if montant else ''} ?"


def texte_du_changement(p: dict[str, Any], question: str | None = None, montant: bool = True) -> str:
    """B2 (M3, TF2) : la commande enregistrée vient d'être changée en caisse : son nouveau total, dit par le code ; puis la question réglée après
    l'enregistrement (M108), comme la confirmation : la parole revient à la personne."""
    total = _montant_enregistre(p) if montant else None
    fait = f"C'est changé : votre commande fait maintenant {total}." if total else "C'est changé dans votre commande."
    return " ".join(x for x in (fait, (question or "").strip()) if x)


def texte_dit_de_la_question(q: dict[str, Any], p: dict[str, Any]) -> str | None:
    """Ce que le code dit pour poser cette question : son texte (l'annulation, avec le total d'AUJOURD'HUI de la commande) ; la proposition, son repli (son texte n'est qu'une consigne)."""
    if q.get("type") == TYPE_ANNULATION:
        return texte_de_l_annulation(p)
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
CLE_DES_NUMEROS = "numeros_des_questions"
CLE_DES_QUESTIONS = "questions_ouvertes"  # objet → question (texte, choix…) ; une seule est posée, dans ``p["question"]``


def _norme(x: Any) -> str:
    return " ".join(str(x or "").casefold().split())


def objet(q: dict[str, Any], p: dict[str, Any]) -> str:
    """L'objet d'une question : ce sur quoi elle porte, fixé à sa naissance et gardé par elle (``objet``). Deux questions sur le même objet sont la
    même question (même numéro) ; deux hésitations sont deux objets, même sur deux articles dits de la même façon."""
    if q.get("objet"):
        return str(q["objet"])
    t = q.get("type")
    if t in ("variante", TYPE_DE_L_ETAPE):
        attente = P.a_completer(p)
        # RC9 (tirées du contrôle long) : l'objet est la ligne DONT PARLE la question (l'article en question), pas toujours la première qui attend : « une regina » dite
        # pendant la taille de la margherita pose la question de la regina sous l'objet de la regina, jamais sous celui de la margherita
        voulue = next((l for l in attente if q.get("article_en_question") and _norme(l.get("nom")) == _norme(q["article_en_question"])), None) or (attente[0] if attente else None)
        return f"{t}:{voulue.get('n') if voulue else _norme(q.get('texte'))}"
    if t == "ambiguite":
        # RC9 (contrôle long, lot 3) : le même doute reposé dans la fiche qui vient de fermer le sien (« une salmone » redit avec « non ») est la MÊME question : même objet, même numéro
        recent, dit = p.get("hesitation_fermee"), _dit_de_l_hesitation(q)
        if isinstance(recent, dict) and dit and recent.get("dit") == dit and recent.get("tour") == p.get("tour_de_l_appel"):
            return str(recent["objet"])
        p["hesitations_nees"] = int(p.get("hesitations_nees") or 0) + 1
        return f"ambiguite:{p['hesitations_nees']}"
    if t == "proposition":
        return f"proposition:{_norme(q.get('article_propose'))}"
    return str(t)


def _dit_de_l_hesitation(q: dict[str, Any]) -> str | None:
    """L'article tel que dit qui a ouvert le doute (le mot, la quantité, ses précisions) ; ``None`` sans lui."""
    dit = q.get("article_dit")
    if not isinstance(dit, dict):
        return None
    return _norme(repr(sorted((k, v) for k, v in dit.items() if v not in (None, "", [], {}))))


def numero(p: dict[str, Any], cle: str) -> str:
    """Le numéro attaché à l'objet : donné une fois, gardé ensuite (RC9)."""
    numeros = p.setdefault(CLE_DES_NUMEROS, {})
    if cle not in numeros:
        prochain = int(p.get("prochain_q") or 1)
        numeros[cle] = prochain
        p["prochain_q"] = prochain + 1
    return f"Q-{numeros[cle]}"


def condition(p: dict[str, Any], q: dict[str, Any]) -> bool:
    """La question existe tant que ceci est vrai DANS L'ÉTAT (audit du code M1, tableau des quatre propriétés)."""
    if q.get("type") == TYPE_ANNULATION:
        return phase(p) == ENREGISTREE
    if q.get("type") == TYPE_NOUVELLE_COMMANDE:
        return phase(p) == ANNULEE
    t = q.get("type")
    if phase(p) == ANNULEE or (phase(p) == ENREGISTREE and t not in ("variante", "ambiguite", TYPE_DE_L_ETAPE)):
        # enregistrée, la commande se change encore (E10) : la question d'une ligne changée se pose ; les autres sont closes
        return False
    if t in ("variante", TYPE_DE_L_ETAPE):
        # RC9 : la question tombe avec SA ligne (sa taille donnée par un changement), pas seulement quand plus aucune ligne n'attend
        n = str(q.get("objet") or "").split(":")[-1]
        return any(str(l.get("n")) == n for l in P.a_completer(p)) if n.isdigit() else bool(P.a_completer(p))
    if t == "proposition":
        article = _norme(q.get("article_propose"))
        dans_le_panier = any(_norme(l.get("nom")).startswith(article) for l in p.get("lignes") or []) if article else False
        return isinstance(p.get("proposition_en_plus"), dict) and not p.get("proposition_refusee") and not dans_le_panier
    if t == "heure_proposee":
        return not p.get("heure_voulue")
    if t == "relecture":
        return bool(P.lignes_pretes(p)) and not p.get("relecture_acceptee") and isinstance(p.get("relecture"), dict) and bool(p["relecture"])
    if t == TYPE_DU_NUMERO:
        fin = p.get("fin_dite") or {}
        return (bool(p.get("relecture_acceptee")) and p.get("attente_du_code") == TYPE_DU_NUMERO and not fin.get("telephone")
                and not p.get("numero_affiche_accepte") and not p.get("numero_affiche_refuse"))
    if t == TYPE_DU_NUMERO_DICTE:
        tel = (p.get("client") or {}).get("telephone")
        return bool(p.get("relecture_acceptee")) and p.get("attente_du_code") == TYPE_DU_NUMERO_DICTE and bool(tel) and p.get("numero_dicte_accepte") != tel
    return True  # l'ambiguïté : posée tant qu'elle n'est pas résolue par sa réponse ou par un de ses candidats nommé (``porte``, case ajouter : elle quitte alors le registre)


def ouvrir(p: dict[str, Any], q: dict[str, Any] | None) -> None:
    """Une question née d'un résultat du moteur entre au registre (ou y remplace la même question sur le même objet : son texte peut changer)."""
    if not isinstance(q, dict) or not q.get("type"):
        return
    cle = objet(q, p)
    ouvertes = p.setdefault(CLE_DES_QUESTIONS, {})
    neuve = {**{k: v for k, v in q.items() if k not in ("id",)}, "objet": cle}
    deja = ouvertes.get(cle)
    if isinstance(deja, dict) and deja.get("texte") == neuve.get("texte") and "nee_au_tour" in deja:
        neuve["nee_au_tour"] = deja["nee_au_tour"]  # la même question redonnée (même objet, même texte) n'est pas née une seconde fois (RC3)
    ouvertes[cle] = {**deja, **neuve} if isinstance(deja, dict) and deja.get("texte") == neuve.get("texte") else neuve


def fermer(p: dict[str, Any], q: dict[str, Any] | None) -> None:
    """La question a reçu sa réponse (ou est tombée) : elle quitte le registre. Son numéro reste attaché à l'objet."""
    if isinstance(q, dict):
        if q.get("type") == "ambiguite" and _dit_de_l_hesitation(q):
            p["hesitation_fermee"] = {"dit": _dit_de_l_hesitation(q), "objet": objet(q, p), "tour": p.get("tour_de_l_appel")}
        (p.get(CLE_DES_QUESTIONS) or {}).pop(objet(q, p), None)
        for cle, x in list((p.get(CLE_DES_QUESTIONS) or {}).items()):
            if x.get("type") == q.get("type") and x.get("id_pose") == q.get("id"):
                p[CLE_DES_QUESTIONS].pop(cle, None)


def proposer_une_nouvelle_commande(p: dict[str, Any]) -> None:
    """DC5 (Evan, 22/11) : un article dit après l'annulation n'entre pas ; le code le dit et propose une nouvelle commande (sa question au registre)."""
    ouvrir(p, {"type": TYPE_NOUVELLE_COMMANDE, "texte": TEXTE_NOUVELLE_COMMANDE})


def repartir(p: dict[str, Any]) -> None:
    """DC5 : « oui » à la nouvelle commande : un panier neuf, sur place (la même fiche de l'appel), le client, le mode et l'adresse gardés ; les numéros
    des questions continuent (jamais un numéro redonné à un autre objet)."""
    neuf = P.nouveau()
    for cle in ("client", "mode", "zone", "adresse", "connu", CLE_DES_NUMEROS, "prochain_q", "vente_en_plus_faite", "proposition_refusee"):
        if cle in p:
            neuf[cle] = p[cle]
    p.clear()
    p.update(neuf)


def tout_fermer(p: dict[str, Any]) -> None:
    """La commande repart de zéro (vidée) ou est annulée : toutes ses questions tombent, ses articles en doute et sa proposition avec elles."""
    p.pop(CLE_DES_QUESTIONS, None)
    p.pop("proposition_en_plus", None)
    p["question"] = None


def choisir(p: dict[str, Any], tour: int, de_l_etat: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """La question posée après la fiche : la première, dans l'ordre fixe, dont la condition est vraie ; numérotée par son objet. Celles dont la
    condition est tombée quittent le registre. ``de_l_etat`` : les questions que l'état redonne sans être gardées (la ligne qui attend sa taille)."""
    ouvertes = p.setdefault(CLE_DES_QUESTIONS, {})
    for q in de_l_etat or []:
        if isinstance(q, dict) and q.get("type"):
            cle = objet(q, p)
            ouvertes.setdefault(cle, {**{k: v for k, v in q.items() if k != "id"}, "objet": cle})
    for cle, q in list(ouvertes.items()):
        if not condition(p, q):
            ouvertes.pop(cle)
    if not ouvertes:
        p["question"] = None
        return None
    cle, q = min(ouvertes.items(), key=lambda kv: ORDRE.index(kv[1]["type"]) if kv[1]["type"] in ORDRE else len(ORDRE))
    id_ = numero(p, cle)
    if q.get("type") == TYPE_ANNULATION:
        q["texte"] = texte_de_l_annulation(p)  # le total de la commande d'AUJOURD'HUI : elle a pu changer dans la même fiche
    q.setdefault("nee_au_tour", tour)
    posee = {**q, "id": id_}
    q["id_pose"] = id_
    p["question"] = posee
    return posee


QUESTIONS_AVANT_LA_RELECTURE = ("ambiguite", "variante", TYPE_DE_L_ETAPE)  # ce qui se finit avant de relire : un article en doute, sa taille, l'étape de sa formule


def question_en_doute(p: dict[str, Any]) -> dict[str, Any] | None:
    """La première question ouverte au registre sur un article encore en doute (RC10) : tant qu'elle vit, la commande ne se relit pas."""
    for q in (p.get(CLE_DES_QUESTIONS) or {}).values():
        if isinstance(q, dict) and q.get("type") in QUESTIONS_AVANT_LA_RELECTURE and condition(p, q):
            return q
    return None


def reponse_implicite(fiche: dict[str, Any], question: dict[str, Any] | None, posee: bool) -> dict[str, Any]:
    """Une question posée et une fiche sans ``reponse`` : la fiche vaut « autre » pour cette question, pour tous les types (remplace les trois
    exceptions du lot 20 et le refus de la fiche entière, DF1). Jamais « accepte » ni « refuse » déduits."""
    if not question or not posee or isinstance(fiche.get("reponse"), dict):
        return fiche
    return {**fiche, "reponse": {"question_id": question.get("id"), "sens": "autre", "implicite": True}}  # ``implicite`` : la fiche n'a PAS répondu (Pierre 7, 8)
