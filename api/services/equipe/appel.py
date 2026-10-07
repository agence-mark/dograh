"""[.mark] The team the agent knows during a call (chantier l-agent-collegue, L1, C4 to C6).

At pick-up, when the agent's switch ``equipe_connue`` is on (off by default, C5), the call
receives:

- ``equipe``: one line per ACTIVE person of the establishment served and of the whole
  company (no establishment): first name, last name, role, what the person takes care of.
  ⛔ Never a phone number nor an e-mail address, except the one the client allowed for
  that person (``divulguer_telephone``, ``divulguer_mail``): only then is it on its line.
  The line ends with the person's key, the name the tool « direct to a person » takes.
  .mark places ``{{equipe}}`` in the prompt, like the sentences;
- ``equipe_cles``: the closed list of those keys (C7), the only ones the tool accepts.

What was injected is stamped on the run (``runtime_configuration.equipe``): how many
people, their keys, where the team was read. Switch off: nothing changes, not even the
stamp (X2, zero loss). Nothing here raises.
"""

from __future__ import annotations

from loguru import logger

from api.schemas.base_client import Equipe, Personne

INTERRUPTEUR = "equipe_connue"
CLE_EQUIPE = "equipe"
CLE_CLES = "equipe_cles"


def interrupteur_allume(run_configs: dict | None) -> bool:
    return bool((run_configs or {}).get(INTERRUPTEUR))


def personnes_de_lappel(equipe: Equipe | None, etablissement_id: str | None) -> list[Personne]:
    """The active people of the establishment served and of the whole company, in the
    order of the team. No establishment served: the whole-company people only."""
    if equipe is None:
        return []
    return [
        p
        for p in equipe.personnes
        if p.actif and (p.etablissement is None or p.etablissement == etablissement_id)
    ]


def nom_complet(personne: Personne) -> str:
    return " ".join(x for x in (personne.prenom, personne.nom) if x and x.strip())


def ligne(personne: Personne) -> str:
    """The line the agent reads. Coordinates only when allowed (C4)."""
    texte = nom_complet(personne)
    if personne.role:
        texte += f", {personne.role}"
    if personne.description:
        texte += f" : {personne.description}"
    coordonnees = []
    if personne.divulguer_telephone and personne.telephone:
        coordonnees.append(f"téléphone {personne.telephone}")
    if personne.divulguer_mail and personne.mail:
        coordonnees.append(f"e-mail {personne.mail}")
    if coordonnees:
        texte += f" ({' ; '.join(coordonnees)})"
    return f"- {texte} [clé : {personne.cle}]"


def injecter_equipe(
    contexte: dict,
    run_configs: dict | None,
    equipe: Equipe | None,
    etablissement_id: str | None,
    lu_depuis: str | None = None,
) -> tuple[dict, dict | None]:
    """The context with ``equipe`` and ``equipe_cles``, and the stamp (None: switch off).
    The text ``equipe`` already in the context is kept (a replay, a pre-call fetch); the closed
    list ``equipe_cles`` NEVER is: it decides who the tool may reach, so it is always the one
    the code just built (revue du 07/10). Never raises."""
    if not interrupteur_allume(run_configs):
        return contexte, None
    try:
        personnes = personnes_de_lappel(equipe, etablissement_id)
        enrichi = dict(contexte)
        if not enrichi.get(CLE_EQUIPE):
            enrichi[CLE_EQUIPE] = "\n".join(ligne(p) for p in personnes)
        enrichi[CLE_CLES] = [p.cle for p in personnes]
        estampille = {
            "personnes": len(personnes),
            "cles": [p.cle for p in personnes],
            "etablissement": etablissement_id,
            "lu_depuis": lu_depuis,
        }
        if not personnes:
            logger.warning(
                "[.mark] « Team known to the agent » is on but no one is in the team of this call "
                "(no client database, or no active person here)"
            )
        return enrichi, estampille
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.error(f"[.mark] Team not injected, the call goes on without it: {erreur!r}")
        return contexte, {"personnes": 0, "erreur": type(erreur).__name__}


def cles_de_lappel(contexte: dict | None) -> tuple[list[str], str | None]:
    """The closed list and the establishment served, as the CODE stamped them on the run
    (``runtime_configuration.equipe``: a reserved key, no pre-call fetch nor caller can write
    it). ([], None) when nothing was stamped: the tool then reaches no one."""
    estampille = ((contexte or {}).get("runtime_configuration") or {}).get("equipe")
    if not isinstance(estampille, dict):
        return [], None
    cles = estampille.get("cles")
    etablissement = estampille.get("etablissement")
    return (
        [c for c in cles if isinstance(c, str)] if isinstance(cles, list) else [],
        etablissement if isinstance(etablissement, str) else None,
    )


def reaffirmer_equipe(contexte: dict) -> dict:
    """After the pre-call fetch (which is merged over the context and may carry any key): the
    closed list is again the stamped one, or absent when nothing was stamped."""
    reaffirme = dict(contexte)
    cles, _etablissement = cles_de_lappel(contexte)
    if ((contexte.get("runtime_configuration") or {}).get("equipe")) is None:
        reaffirme.pop(CLE_CLES, None)
    else:
        reaffirme[CLE_CLES] = cles
    return reaffirme


def noms_pour_la_synthese(equipe: Equipe | None) -> list[str]:
    """C6: the names of the active people, spelled as the client wrote them."""
    if equipe is None:
        return []
    return [nom_complet(p) for p in equipe.personnes if p.actif and nom_complet(p)]
