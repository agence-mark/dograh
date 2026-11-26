"""[.mark] Le retour fermé d'un geste d'une action interne (commande, réservation, service) : le même que celui du classeur (``Resultat(statut, faits, suggestion, manque)``).

Seul point de contact du mécanisme commun avec la couche d'accès : le reste du paquet importe d'ici, jamais du classeur.
"""

from api.db.bases_clients.restauration_commun import STATUTS, Resultat
from api.services.mots_dits import numero_en_lettres

__all__ = [
    "STATUTS", "Resultat", "avec_le_fait_du_numero_affiche", "avec_numero_affiche", "avec_numeros_retenus", "phrase_du_numero_retenu", "question_apres_enregistrement", "question_du_numero_affiche", "phrase_du_code",
]

CLE_NUMERO_RETENU = "numero_retenu_dit"
CLE_SECOND_NUMERO_RETENU = "second_numero_retenu_dit"
# M98 : le numéro d'où la personne appelle, gardé : porté dans les FAITS (en lettres, par paires) pour que l'agent puisse le dire si on le lui
# demande, jamais ajouté à la phrase dite.
CLE_NUMERO_AFFICHE = "numero_affiche_dit"
# M110 (appel 2593) : un numéro s'affiche pour cet appel : le modèle le SAIT dès le premier geste (commande, réservation) et ne le demande pas.
# Un booléen, jamais le numéro (il n'est dit qu'à la demande, par ``numero_affiche_dit``).
CLE_NUMERO_S_AFFICHE = "numero_s_affiche"
# Ces statuts finaux portent déjà leur propre confirmation : on n'y ajoute pas le numéro qui s'affiche (M98).
_STATUTS_FINAUX = ("ENREGISTREE", "DEJA_FAIT", "TRANSMISE")
# C6 n° 10 : ce qui était déjà fait ou transmis ne porte pas de numéro retenu ; un enregistrement le porte (le code le dit après la confirmation du modèle).
_STATUTS_SANS_NUMERO = ("DEJA_FAIT", "TRANSMISE")


def avec_numeros_retenus(r: Resultat, numero: str | None = None, second: str | None = None) -> Resultat:
    """Mécanisme commun : un numéro DICTÉ et retenu dans cet appel du geste est porté dans les faits, tel que retenu (``numero_retenu_dit``, en lettres par paires) : jamais relu de
    mémoire par le modèle, qui peut avoir gardé l'ancien après une correction. C6 n° 10 (décision d'Evan 25/11 9 h 30) : aucune phrase n'est composée ici ; la porte dit le motif réglé
    ``numero_retenu`` (``phrase_du_numero_retenu``) après la phrase du modèle. ``numero``/``second`` : E.164 retenus, ``None`` s'il n'y a rien à dire (numéro qui s'affiche, déjà dit,
    refusé). Rien pour une commande déjà faite ou transmise ; un enregistrement le porte (la confirmation est dite par le modèle, le numéro par le code). Aucun mot de métier."""
    if r.statut in _STATUTS_SANS_NUMERO or not (numero or second):
        return r
    faits = dict(r.faits)
    if numero:
        faits[CLE_NUMERO_RETENU] = numero_en_lettres(numero)
    if second:
        faits[CLE_SECOND_NUMERO_RETENU] = numero_en_lettres(second)
    return Resultat(r.statut, faits, r.suggestion, r.manque)


def phrase_du_numero_retenu(ctx, faits: dict | None, rang: int = 0) -> str | None:
    """C6 n° 10 : la phrase réglée du numéro retenu (motif ``numero_retenu``, ``{numero}`` en lettres) quand ``faits`` porte un numéro dicté et retenu ; ``None`` sinon. Le second
    numéro se dit par la même phrase, à la suite. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import NUMERO_RETENU

    faits = faits if isinstance(faits, dict) else {}
    phrases = [phrase_du_code(ctx, NUMERO_RETENU, rang, numero=str(faits[cle])) for cle in (CLE_NUMERO_RETENU, CLE_SECOND_NUMERO_RETENU) if faits.get(cle)]
    return " ".join(x for x in phrases if x) or None


def avec_le_fait_du_numero_affiche(retour: dict, affiche: str | None) -> dict:
    """M110 : le retour d'un geste porte ``numero_s_affiche: true`` quand un numéro s'affiche pour l'appel ; rien sinon. Aucun mot de métier."""
    if affiche and isinstance(retour.get("faits"), dict):
        retour["faits"] = {**retour["faits"], CLE_NUMERO_S_AFFICHE: True}
    return retour


def numero_est_dit(r_faits: dict) -> bool:
    """Ce résultat porte un numéro retenu à dire : il part à la voix tel quel, comme la relecture (W17)."""
    return CLE_NUMERO_RETENU in r_faits or CLE_SECOND_NUMERO_RETENU in r_faits


def avec_numero_affiche(r: Resultat, affiche: str | None) -> Resultat:
    """M98 : le numéro qui s'affiche, gardé pour ce geste, est porté dans les faits (``numero_affiche_dit``, par paires), sans toucher à la
    phrase. Rien pour un statut final ni sans numéro. Aucun mot de métier."""
    if r.statut in _STATUTS_FINAUX or not affiche:
        return r
    return Resultat(r.statut, {**r.faits, CLE_NUMERO_AFFICHE: numero_en_lettres(affiche)}, r.suggestion, r.manque)


def _phrase_du_code_dans_un_resultat(ctx, motif_id: str, rang: int = 0) -> str | None:
    """Le texte d'une phrase du code qu'un outil met dans son résultat, réglable à l'écran (groupe, agent, étape) : la résolution du moteur à
    l'endroit de l'appel, sinon les règles de la configuration, sinon le défaut du catalogue. ``None`` : phrase éteinte. ⛔ Ne lève jamais."""
    from api.services.phrases.regles import texte_dans_un_resultat

    resolue = None
    resoudre = getattr(ctx, "phrase_du_code", None)
    if callable(resoudre):
        try:
            resolue = resoudre(motif_id)
        except Exception:  # noqa: BLE001 -- la résolution de l'appel manque : les règles de la configuration valent
            resolue = None
    return texte_dans_un_resultat(motif_id, resolue=resolue, configurations=getattr(ctx, "configurations", None), rang=rang)


def question_du_numero_dicte(ctx) -> str | None:
    """DC10 : la relecture du numéro dicté avant l'enregistrement, réglable à l'écran (motif ``numero_dicte_relu`` : groupe, agent, étape), allumée
    par défaut. ``None`` : éteinte, le numéro est enregistré dès qu'il est dit. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import NUMERO_DICTE_RELU

    return _phrase_du_code_dans_un_resultat(ctx, NUMERO_DICTE_RELU)


def question_du_numero_affiche(ctx) -> str | None:
    """M98 : la question qui finit la relecture quand le numéro qui s'affiche est gardé, réglable à l'écran (motif ``numero_affiche_garde`` des
    phrases du code : groupe, agent, étape). ``None`` : phrase éteinte, le modèle pose la question à la fin de sa relecture (C6 n° 8). ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import NUMERO_AFFICHE_GARDE

    return _phrase_du_code_dans_un_resultat(ctx, NUMERO_AFFICHE_GARDE)


def question_apres_enregistrement(ctx) -> str | None:
    """M108 : la question qui finit la confirmation d'un enregistrement dite par le code, réglable à l'écran (motif ``apres_enregistrement`` :
    groupe, agent, étape). ``None`` : phrase éteinte, la confirmation est dite seule. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import APRES_ENREGISTREMENT

    return _phrase_du_code_dans_un_resultat(ctx, APRES_ENREGISTREMENT)


def phrase_du_code(ctx, motif_id: str, rang: int = 0, **valeurs: str) -> str | None:
    """C6 : une phrase réglée du catalogue, ses variables remplacées (``{total}``…) et RIEN d'autre : le code ne compose pas la phrase, il remplit celle de l'écran. ``rang`` fait tourner les
    variantes (Q3 = A) : l'appelant le tient (une fois par phrase dite). Seules les variables déclarées par le motif sont remplacées. ``None`` : éteinte. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import MOTIFS

    texte = _phrase_du_code_dans_un_resultat(ctx, motif_id, rang)
    motif = MOTIFS.get(motif_id)
    if texte is None or motif is None:
        return texte
    for nom in motif.variables:
        if nom in valeurs:
            texte = texte.replace("{" + nom + "}", str(valeurs[nom]))
    return texte
