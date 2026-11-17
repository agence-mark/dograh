"""[.mark] The internal connector « Order » (module Restauration, lot 5, T-18): the order on a closed catalogue, taken item by item.

No software, no Nango: the actions run in the fork (``services/commande/action.py``) and the catalogue is a SOURCE (the client's database, through
``services/restauration/source_commande.py``, is the first one). Sixteen tools, created in « Tools » as ``integration`` tools and placed on the
steps that need them (no new tool category):

- ``choisir_mode`` sets how the order is taken; a closed mode is never set, the closed reason is returned;
- ``ajouter`` adds what the caller said: several items and quantities in one sentence, each looked up in the catalogue, choices, removals,
  extras, a note, halves; a missing choice is returned as ONE question and nothing already said is lost;
- ``modifier``, ``retirer``, ``vider_commande`` change the basket; ``voir_commande`` reads it back with the code's own prices and total;
- ``etat_ouverture`` says what is open now (every mode, or one), ``heure_annoncee`` what the code would announce now for a mode (a delivery, by its zone),
  ``verifier_adresse`` places the address said in the delivery zones (a doubt is never a zone), ``resoudre_une_date`` turns « Saturday at half past seven »
  into an exact date and time, forward only, never guessed;
- ``finaliser`` leads to the saving, one missing piece at a time: it reads the order back first and saves only on the caller's « yes ».

Every answer is a closed status (never a software's own text), the facts, and a SENTENCE PROPOSED: the tool's setting « sentence the tool
proposes » (``restitution``) says whether the model says it word for word or in its own words. The model never sends anything anywhere: the
saving triggers the sending, by the code.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    Parametre,
    declarer,
)


def _jamais(*_args, **_kwargs):
    raise RuntimeError("An internal action never goes through the relay.")


async def _executer(action, arguments, ctx, delai_s):
    from api.services.commande.action import executer

    return await executer(action, arguments, ctx, delai_s)


def _source_du_catalogue() -> None:
    # The client's database is the first catalogue source: it registers itself on import (others register theirs the same way).
    import api.services.restauration.source_commande  # noqa: F401


_source_du_catalogue()

_CHOIX = Parametre(
    "choix",
    description="Her words for a choice or extra of the item, or her answer to the choice the tool asked.",
    obligatoire=False,
)
# Agent fiable (appel 2616) : l'enveloppe commune des outils qui reçoivent une réponse. Le modèle dit le sens et transmet les mots ;
# le code les applique à la question en attente (``commande.action.vers_la_question_en_attente``).
_MOTS = Parametre("mots", description="What she just said, word for word.", obligatoire=False)
_SENS = Parametre(
    "sens", description="The meaning of what she just said: accord, refus, modification, annulation, question or autre.", obligatoire=False
)
_SANS = Parametre("sans", description="What she wants removed, in her words.", obligatoire=False)
_NOTE = Parametre("note", description="A request about the item that has no price, in her words.", obligatoire=False)
_MOITIES = Parametre("moities", description="The two halves of a half-and-half item, in her words.", obligatoire=False)
_LIGNE = Parametre("ligne", description="The line: its number or its name, in her words.", obligatoire=False)

def _action_ouverte(fiche: dict) -> dict | None:
    """Un panier avec au moins une ligne, jamais enregistré : l'action ouverte, à finir par ``finaliser``."""
    from api.services.commande import panier

    p = fiche.get(panier.CLE) if isinstance(fiche, dict) else None
    if isinstance(p, dict) and p.get("lignes") and not p.get("enregistree"):
        return {"outil": "finaliser"}
    return None


COMMANDE = declarer(
    Connecteur(
        nom="commande",
        action_ouverte=_action_ouverte,
        libelle="Order (internal)",
        integration="interne",
        interne=True,
        executer_interne=_executer,
        actions=(
            Action(
                nom="etat_ouverture",
                description="What is open right now: every mode the catalogue offers, or only the one asked, with the reason and the reopening time when closed. Changes nothing.",
                parametres=(Parametre("mode", description="One mode, in her words. Empty: all.", obligatoire=False),),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="heure_annoncee",
                description=(
                    "The time the code announces right now for a mode (the order's mode by default; a delivery needs its zone first). "
                    "Say the sentence as returned: never compute a time yourself."
                ),
                parametres=(Parametre("mode", description="The mode, in her words. Empty: the order's.", obligatoire=False),),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="verifier_adresse",
                description=(
                    "Place the delivery address said by the caller in the delivery zones. Sure: the zone, fees and minimum are set on the order. "
                    "A doubt (several towns, town not heard) sets nothing and returns the candidates to confirm: ask, do not choose. Out of zone: say so."
                ),
                parametres=(Parametre("adresse", description="The address in her words, with the town."), _SENS, _MOTS),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="resoudre_une_date",
                description=(
                    "Turn a day and time said by the caller (tomorrow, Saturday, the 24th, half past seven in the evening) into the exact moment, "
                    "forward only. Sure: the ISO moment to give to the finalise tool. A doubt returns the candidates: ask, do not choose."
                ),
                parametres=(
                    Parametre("texte", description="The day as said."),
                    Parametre("heure", description="The time as said. Empty: the tool asks for it.", obligatoire=False),
                ),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="choisir_mode",
                description='Set how she orders (to take away or delivered). Call it on her first order request, with what she already said.',
                parametres=(
                    _SENS,
                    _MOTS,
                    Parametre("mode", description="The mode in her words. Empty if she did not say it.", obligatoire=False),
                    Parametre("articles", description="The items she already said, in her words.", obligatoire=False),
                    Parametre("heure", description="When she wants the order, in her words, if she said it.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="ajouter",
                description='Add the items she just said. Call it each time she names an item.',
                parametres=(
                    _SENS,
                    _MOTS,
                    Parametre(
                        "articles",
                        description="The items and quantities in her words, card numbers included.",
                        obligatoire=False,
                    ),
                    _CHOIX,
                    _SANS,
                    _NOTE,
                    _MOITIES,
                    Parametre("heure", description="When she wants the order, in her words, if she said it.", obligatoire=False),
                    Parametre("mode", description="The mode, if she says it in this sentence.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="modifier",
                description='Change or remove one line of the order (quantity zero removes it).',
                parametres=(
                    _SENS,
                    _MOTS,
                    _LIGNE,
                    Parametre("quantite", type="number", description="The new quantity; zero removes the line.", obligatoire=False),
                    _CHOIX,
                    _SANS,
                    _NOTE,
                    _MOITIES,
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="retirer",
                description="Remove one line from the order, by its number or its name.",
                parametres=(_LIGNE,),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="vider_commande",
                description="Empty the items of the order. The mode, the zone and the caller stay.",
                parametres=(),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="voir_commande",
                description='Read what she asks about: the order and its total, an item and its allergens, the waiting time, or the offers. With vider, start over.',
                parametres=(
                    Parametre("quoi", description="What to read: commande, produit, delai or offres.", choix=("commande", "produit", "delai", "offres"), obligatoire=False),
                    Parametre("produit", description="The item or kind of item, in her words.", obligatoire=False),
                    Parametre("a_eviter", description="What she wants to avoid, only if she said it.", obligatoire=False),
                    Parametre("vider", type="boolean", description="She wants to start the order over.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="remises_disponibles",
                description=(
                    "What can be said about the offers, and WHEN: the code counts, you only say what it returns. With ``demande`` true (the caller asks what "
                    "offers there are), it always answers. Otherwise it speaks only if something applies to the order or a threshold is nearly reached, a "
                    "limited number of times per call, never to a caller in a hurry (``presse``) nor after a no (``refus``). ``a_dire`` false: say nothing."
                ),
                parametres=(
                    Parametre("demande", type="boolean", description="She asked about the offers.", obligatoire=False),
                    Parametre("presse", type="boolean", description="She is in a hurry.", obligatoire=False),
                    Parametre("refus", type="boolean", description="She just refused an offer.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="voir_produit",
                description=(
                    "What the catalogue says about ONE item. Without ``a_eviter``: what it is made of (« what is in the Reine »), nothing else. "
                    "With ``a_eviter``, ONLY when the caller himself speaks of an allergy, an intolerance or a diet: what the sheet says about that one thing. "
                    "« What do you have without gluten / vegetarian? »: ``produit`` is the kind he names (« pizzas ») or empty, ``a_eviter`` the thing. "
                    "Never say « without » when the result does not say it: say it as is, do not guess."
                ),
                parametres=(
                    Parametre("produit", description="The item or kind of item, in her words. Empty: the whole menu.", obligatoire=False),
                    Parametre("a_eviter", description="What she wants to avoid, only if she said it.", obligatoire=False),
                ),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="reconnaitre_le_client",
                description=(
                    "Recognise the caller by the number that shows (never a dictated number): his first name and his habits (« ring the second bell »), "
                    "to read back so he confirms them. With ``confirmer_consignes`` true, once he said yes, the habits are joined to the order's note. "
                    "Hidden or unknown number: nothing to say, go on as with anyone."
                ),
                parametres=(
                    Parametre("confirmer_consignes", type="boolean", description="True ONLY once the caller confirmed his usual habits.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="retrouver_commande",
                description=(
                    "Where a TODAY's order stands, read in the book: by its number, or by the number that shows. Say only what it returns "
                    "(the order is recorded, and for when): never invent a stage. Several orders: it asks which."
                ),
                parametres=(Parametre("numero", description="The order's number as the caller says it. Empty: the order of the number that shows.", obligatoire=False),),
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="envoyer_un_message",
                description=(
                    "Send the caller a message he asks for (the menu, the link to leave a review) to the number that shows. The text is the one the place wrote, "
                    "never yours. Off unless the place turned it on: then the tool says it cannot, say it as is. Once per call."
                ),
                parametres=(Parametre("quoi", description="What he asks to receive: carte (the menu) or avis (the review link).", choix=("carte", "avis")),),
                ecrit=False,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="finaliser",
                description='Take the order to its saving, one missing thing at a time. Call it when she says that is all, then with each of her answers.',
                parametres=(
                    _SENS,
                    _MOTS,
                    Parametre("second_numero", description="A second number she dictated.", obligatoire=False),
                    Parametre("second_qui", description="Whose the second number is.", obligatoire=False),
                    Parametre("second_pourquoi", description="Why the second number.", obligatoire=False),
                    Parametre("moyen", description="How she pays: carte, especes, carte_livraison, titre_restaurant, cheque, en_ligne.", obligatoire=False),
                    Parametre("part", type="number", description="Split payment: euros paid the first way.", obligatoire=False),
                    Parametre("moyen_reste", description="Split payment: how she pays the rest.", obligatoire=False),
                    Parametre("rendu_sur", type="number", description="Cash: the note she pays with, in euros.", obligatoire=False),
                    Parametre("consigne", description="A habit to remember next time, never an allergy.", obligatoire=False),
                    Parametre("heure", description="When she wants the order, in her words.", obligatoire=False),
                    Parametre("articles", description="Another item she names in the same sentence.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
