"""[.mark] Le retour fermé d'un geste d'une action interne (commande, réservation, service) : le même que celui du classeur (``Resultat(statut, faits, suggestion, manque)``).

Seul point de contact du mécanisme commun avec la couche d'accès : le reste du paquet importe d'ici, jamais du classeur.
"""

from api.db.bases_clients.restauration_commun import STATUTS, Resultat
from api.services.mots_dits import numero_en_lettres

__all__ = [
    "STATUTS", "Resultat", "avec_le_fait_du_numero_affiche", "avec_numero_affiche", "avec_numeros_retenus", "question_apres_enregistrement", "question_du_numero_affiche",
]

CLE_NUMERO_RETENU = "numero_retenu_dit"
CLE_SECOND_NUMERO_RETENU = "second_numero_retenu_dit"
# M98 : le numéro d'où la personne appelle, gardé : porté dans les FAITS (en lettres, par paires) pour que l'agent puisse le dire si on le lui
# demande, jamais ajouté à la phrase dite.
CLE_NUMERO_AFFICHE = "numero_affiche_dit"
# M110 (appel 2593) : un numéro s'affiche pour cet appel : le modèle le SAIT dès le premier geste (commande, réservation) et ne le demande pas.
# Un booléen, jamais le numéro (il n'est dit qu'à la demande, par ``numero_affiche_dit``).
CLE_NUMERO_S_AFFICHE = "numero_s_affiche"
# Ces statuts finaux portent déjà leur propre confirmation, dite par le code : on n'y ajoute pas la lecture d'un numéro.
_STATUTS_FINAUX = ("ENREGISTREE", "DEJA_FAIT", "TRANSMISE")


def avec_numeros_retenus(r: Resultat, numero: str | None = None, second: str | None = None) -> Resultat:
    """Mécanisme commun : un numéro DICTÉ et retenu dans cet appel du geste est dit par le code, tel que retenu (« Je note le zéro six, vingt-deux, ... »),
    jamais relu de mémoire par le modèle qui peut avoir gardé l'ancien après une correction. Le fait (``numero_retenu_dit``) et la phrase, en tête de
    la suggestion, portent le même texte. ``numero``/``second`` : E.164 retenus, ``None`` s'il n'y a rien à dire (numéro qui s'affiche, déjà dit,
    refusé). Aucun mot de métier."""
    if r.statut in _STATUTS_FINAUX or not (numero or second):
        return r
    faits, phrases = dict(r.faits), []
    if numero:
        faits[CLE_NUMERO_RETENU] = numero_en_lettres(numero)
        phrases.append(f"Je note le {faits[CLE_NUMERO_RETENU]}.")
    if second:
        faits[CLE_SECOND_NUMERO_RETENU] = numero_en_lettres(second)
        phrases.append(f"Pour le second numéro, je note le {faits[CLE_SECOND_NUMERO_RETENU]}.")
    suite = (r.suggestion or "").strip()
    return Resultat(r.statut, faits, " ".join(phrases + ([suite] if suite else [])), r.manque)


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


def _phrase_du_code_dans_un_resultat(ctx, motif_id: str) -> str | None:
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
    return texte_dans_un_resultat(motif_id, resolue=resolue, configurations=getattr(ctx, "configurations", None))


def question_du_numero_dicte(ctx) -> str | None:
    """DC10 : la relecture du numéro dicté avant l'enregistrement, réglable à l'écran (motif ``numero_dicte_relu`` : groupe, agent, étape), allumée
    par défaut. ``None`` : éteinte, le numéro est enregistré dès qu'il est dit. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import NUMERO_DICTE_RELU

    return _phrase_du_code_dans_un_resultat(ctx, NUMERO_DICTE_RELU)


def question_du_numero_affiche(ctx) -> str | None:
    """M98 : la question qui finit la relecture quand le numéro qui s'affiche est gardé, réglable à l'écran (motif ``numero_affiche_garde`` des
    phrases du code : groupe, agent, étape). ``None`` : phrase éteinte, la relecture finit par « C'est bon ? ». ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import NUMERO_AFFICHE_GARDE

    return _phrase_du_code_dans_un_resultat(ctx, NUMERO_AFFICHE_GARDE)


def question_apres_enregistrement(ctx) -> str | None:
    """M108 : la question qui finit la confirmation d'un enregistrement dite par le code, réglable à l'écran (motif ``apres_enregistrement`` :
    groupe, agent, étape). ``None`` : phrase éteinte, la confirmation est dite seule. ⛔ Ne lève jamais."""
    from api.services.phrases.catalogue import APRES_ENREGISTREMENT

    return _phrase_du_code_dans_un_resultat(ctx, APRES_ENREGISTREMENT)
