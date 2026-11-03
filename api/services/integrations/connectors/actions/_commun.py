"""[.mark] Shared pieces of the connectors of the catalogue (U3 sexies, point 8, F2).

Not a connector: it declares nothing. It holds what every CRM and every calendar software of the
catalogue says the same way, so that each software's file only spells its own API:

- the four actions every CRM offers, with the SAME names and parameters (the agent's prompts do not
  change from one CRM to another): ``find_contact`` (reads, may be anticipated), ``create_contact``,
  ``add_call_note``, ``create_deal`` (write, never anticipated);
- the reading of the caller's identity from the common model (D16), never from the raw record;
- the translator of the domain « dossier » (caller verification), which reads a contact by phone.

The model never chooses the organization nor the account (D6): an action reads only the
parameters it declares, plus the settings of the client.
"""

from __future__ import annotations

from typing import Any

from api.schemas.apres_appel import numero_e164
from api.services.hub.traducteurs import (
    ObjetTraduit,
    Operation,
    Traducteur,
    declarer_traducteur,
)
from api.services.integrations.connectors.catalogue import (
    Action,
    ContexteAction,
    Parametre,
)


def formes_du_numero(brut: str | None) -> list[str]:
    """The ways a French number is typed in a CRM: « +33612345678 » and « 0612345678 ». Empty when
    it is not a number."""
    e164 = numero_e164(brut)
    if not e164:
        return []
    formes = [e164]
    if e164.startswith("+33") and len(e164) == 12:
        formes.append("0" + e164[3:])
    return formes


def nom_complet(prenom: str | None, nom: str | None) -> str:
    return " ".join(x for x in (prenom, nom) if x)


def identite(params: dict, ctx: ContexteAction) -> dict[str, str | None]:
    """The contact to create: what the model gave, else the common model of the call."""
    c = ctx.modele.contact
    lu = {
        "prenom": params.get("prenom") or c.prenom,
        "nom": params.get("nom") or c.nom,
        "mail": params.get("mail") or c.mail,
        "telephone": numero_e164(params.get("telephone") or c.telephone),
    }
    if not (lu["nom"] or lu["prenom"] or lu["telephone"] or lu["mail"]):
        raise ValueError("A contact needs a name, a phone number or an e-mail address.")
    return lu


def criteres(params: dict, ctx: ContexteAction) -> tuple[list[str], str | None]:
    """What identifies the contact to look for: his phone number (every typing of it), else his
    e-mail. The caller's own number is the default."""
    mail = params.get("mail") or None
    formes = formes_du_numero(params.get("telephone") or ctx.modele.contact.telephone)
    if not formes and not mail:
        raise ValueError("Nothing to look the contact up with: no phone number, no e-mail.")
    return formes, mail


def texte_de_la_note(params: dict, ctx: ContexteAction) -> str:
    lignes = [str(params["resume"]).strip()]
    if ctx.modele.motif:
        lignes.append(f"Motif : {ctx.modele.motif}")
    lignes.append("Note posée par l'assistant vocal.")
    return "\n".join(lignes)


def trouves(contacts: list[tuple[Any, str | None]], limite: int = 3) -> dict:
    """The USEFUL result of a search (D8): an identifier and a name, never the record."""
    sortie = [
        {"identifiant": str(i), "nom": (n or "").strip() or None}
        for i, n in contacts
        if i not in (None, "")
    ][:limite]
    return {"contacts": sortie} if sortie else {"contacts": [], "aucun": True}


def _identifiant(reponse: Any, *chemins: str) -> Any:
    for chemin in chemins:
        courant = reponse
        for morceau in chemin.split("."):
            courant = courant.get(morceau) if isinstance(courant, dict) else None
        if courant not in (None, ""):
            return courant
    return None


def identifiant_de(reponse: Any, *chemins: str) -> str | None:
    """The identifier of what a software just created, at the first path that holds one."""
    trouve = _identifiant(reponse, *chemins)
    return None if trouve is None else str(trouve)


def action_trouver(preparer, resultat) -> Action:
    return Action(
        nom="find_contact",
        description=(
            "Look up the caller in the business's CRM. Without parameters it uses the number he "
            "is calling from. Returns up to three contacts (identifier and name)."
        ),
        parametres=(
            Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
            Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
        ),
        ecrit=False,
        anticipable_permis=True,
        preparer=preparer,
        resultat=resultat,
    )


def action_creer_contact(preparer, resultat, reglages: dict | None = None) -> Action:
    return Action(
        nom="create_contact",
        description="Create the caller in the business's CRM. Search first: never create twice.",
        parametres=(
            Parametre("prenom", description="His first name.", obligatoire=False),
            Parametre("nom", description="His last name.", obligatoire=False),
            Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
            Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
        ),
        ecrit=True,
        preparer=preparer,
        resultat=resultat,
        reglages_par_defaut=reglages or {},
    )


def action_note(preparer, resultat, reglages: dict | None = None) -> Action:
    return Action(
        nom="add_call_note",
        description="Write a note about this call on the caller's contact in the CRM.",
        parametres=(
            Parametre("identifiant", description="The identifier of the contact, as returned by find_contact or create_contact."),
            Parametre("resume", description="What the caller asked and what was agreed, in two or three sentences."),
        ),
        ecrit=True,
        preparer=preparer,
        resultat=resultat,
        reglages_par_defaut=reglages or {},
    )


def action_affaire(preparer, resultat, reglages: dict | None = None) -> Action:
    return Action(
        nom="create_deal",
        description="Open a deal (an opportunity) for the caller's contact, in the pipeline the business chose.",
        parametres=(
            Parametre("identifiant", description="The identifier of the contact, as returned by find_contact or create_contact."),
            Parametre("titre", description="A short title for the deal. Leave empty to use the reason of the call.", obligatoire=False),
        ),
        ecrit=True,
        preparer=preparer,
        resultat=resultat,
        reglages_par_defaut=reglages or {},
    )


def titre_affaire(params: dict, ctx: ContexteAction) -> str:
    c = ctx.modele.contact
    return (
        params.get("titre")
        or ctx.modele.motif
        or f"Appel de {nom_complet(c.prenom, c.nom) or 'un appelant'}"
    )


def resultat_creation(*chemins: str):
    """``resultat`` of an action that creates something: the identifier, nothing else."""

    def _lire(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
        identifiant = identifiant_de(reponse, *chemins)
        if identifiant is None:
            raise ValueError("The software gave no identifier for what it created.")
        return {"cree": True, "identifiant": identifiant}

    return _lire


def resultat_note(_reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return {"note": True}


def declarer_dossier(
    *,
    systeme: str,
    libelle: str,
    integration: str,
    chercher,
    lire_liste,
    lire,
    lire_un,
) -> Traducteur:
    """The translator « dossier » of a CRM: the contact found by phone, then read by identifier.
    It returns identity and phone numbers only (never a note, a deal or a history)."""
    return declarer_traducteur(
        Traducteur(
            systeme=systeme,
            libelle=libelle,
            integration=integration,
            domaine="dossier",
            objets=(
                ObjetTraduit(
                    "dossier",
                    correspondance=(),
                    operations={
                        "chercher": Operation(chercher, lire_liste),
                        "lire": Operation(lire, lire_un),
                    },
                ),
            ),
        )
    )
