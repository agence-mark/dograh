"""[.mark] Le retour fermé d'un geste de la commande : le même que celui du classeur (``Resultat(statut, faits, suggestion, manque)``).

Seul point de contact du mécanisme commun avec la couche d'accès : le reste du paquet importe d'ici, jamais du classeur.
"""

from api.db.bases_clients.restauration_commun import STATUTS, Resultat
from api.services.mots_dits import numero_en_lettres

__all__ = ["STATUTS", "Resultat", "avec_numeros_retenus"]

CLE_NUMERO_RETENU = "numero_retenu_dit"
CLE_SECOND_NUMERO_RETENU = "second_numero_retenu_dit"
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


def numero_est_dit(r_faits: dict) -> bool:
    """Ce résultat porte un numéro retenu à dire : il part à la voix tel quel, comme la relecture (W17)."""
    return CLE_NUMERO_RETENU in r_faits or CLE_SECOND_NUMERO_RETENU in r_faits
