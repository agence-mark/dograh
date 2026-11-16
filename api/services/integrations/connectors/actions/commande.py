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
    description=(
        "The caller's own words for the choices and extras of the item (« barbecue sauce », « extra cheese »), looked up among that item's choices. "
        "Also the answer to the question the tool just asked (a size, a sauce)."
    ),
    obligatoire=False,
)
_SANS = Parametre("sans", description="What the caller wants removed from the item (« no mushrooms »), looked up among what can be removed.", obligatoire=False)
_NOTE = Parametre("note", description="A free request about the item that has no price (« well done », « sauce on the side »).", obligatoire=False)
_MOITIES = Parametre("moities", description="For an item made of two halves: the two halves, in the caller's words.", obligatoire=False)
_LIGNE = Parametre("ligne", description="The line of the order: its number as read back, or its name in the caller's words.", obligatoire=False)

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
                parametres=(Parametre("mode", description="Only one mode, in the caller's words. Empty: all of them.", obligatoire=False),),
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
                parametres=(Parametre("mode", description="The mode, in the caller's words. Empty: the order's mode.", obligatoire=False),),
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
                parametres=(Parametre("adresse", description="The address as the caller said it, with the town."),),
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
                description=(
                    "Set how the order is taken (the modes the catalogue offers, in the caller's own words). Keeps the items already taken. "
                    "A closed mode is not set: the reason is returned, unless the venue takes orders for later (statut FERME_PLANIFIABLE: tell it is closed, say when it reopens, offer a slot of the next opening, the mode is set). When the caller has already said what she wants, pass it in articles: it is added right after the mode."
                ),
                parametres=(
                    Parametre("mode", description="The mode the caller wants, in his words. Empty when he has not said it: the tool asks him (never guess it, never several modes at once).", obligatoire=False),
                    Parametre("articles", description="What the caller has already said she wants (same as for adding items), in her words.", obligatoire=False),
                    Parametre("heure", description="Only if the caller already said when he wants the order (a later time or day): the exact date and time (ISO, from the date tool). Kept until the order is finalised.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="ajouter",
                description=(
                    "Add to the order what the caller just said: one or several items with their quantities in one sentence. Each is looked up in the "
                    "catalogue; a missing compulsory choice comes back as ONE question to ask, and nothing already said is lost. Without articles, it "
                    "answers the open question or completes the last item."
                ),
                parametres=(
                    Parametre(
                        "articles",
                        description="The items and quantities as the caller said them (« two margherita and a coke »). Empty when only answering a question.",
                        obligatoire=False,
                    ),
                    _CHOIX,
                    _SANS,
                    _NOTE,
                    _MOITIES,
                    Parametre("heure", description="Only if the caller already said when he wants the order (a later time or day): the exact date and time (ISO, from the date tool). Kept until the order is finalised.", obligatoire=False),
                    Parametre("mode", description="Only if the caller says the mode in this same sentence, in his words: it is set first, then the items are added.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=False,
                local=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
            Action(
                nom="modifier",
                description="Change ONE line of the order: its quantity (zero removes it), its choices, its removals, its note. All or nothing.",
                parametres=(
                    _LIGNE,
                    Parametre("quantite", type="number", description="The new quantity of the line (zero removes the line).", obligatoire=False),
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
                description="Read the order as the code holds it: the numbered lines, the prices, the fees and the total. The only total there is.",
                parametres=(),
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
                    Parametre("demande", type="boolean", description="True when the caller himself asked about the offers.", obligatoire=False),
                    Parametre("presse", type="boolean", description="True when the caller is in a hurry.", obligatoire=False),
                    Parametre("refus", type="boolean", description="True when the caller just said no to an offer: it is never offered again in this call.", obligatoire=False),
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
                    "With ``a_eviter``, ONLY when the caller himself speaks of an allergy or an intolerance: what the sheet says about that one thing. "
                    "Never say « without » when the sheet does not say: when the answer is « I cannot confirm », say it as is, do not guess."
                ),
                parametres=(
                    Parametre("produit", description="The item, in the caller's words."),
                    Parametre("a_eviter", description="The thing the caller is allergic or intolerant to, in his words. Empty unless he spoke of it.", obligatoire=False),
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
                description=(
                    "Lead the order to its saving. Call it each time something is missing: it asks for ONE thing at a time (an offer of something more, the "
                    "first name, the phone number, how he pays), then reads the order back. Call it with confirmer true ONLY once the caller said yes to "
                    "the reading. The number he calls from is kept without asking him."
                ),
                parametres=(
                    Parametre("prenom", description="The first name the order is made under.", obligatoire=False),
                    Parametre("telephone", description="A phone number the caller dictated, only when his own is hidden or he asks for another.", obligatoire=False),
                    Parametre("second_numero", description="A second number to join to the order (« my wife's »), dictated.", obligatoire=False),
                    Parametre("second_qui", description="Whose the second number is.", obligatoire=False),
                    Parametre("second_pourquoi", description="Why the second number (« I will be at work »).", obligatoire=False),
                    Parametre(
                        "moyen",
                        description="How he pays, as the code names it: carte, especes, carte_livraison (card paid to the delivery person), titre_restaurant, cheque, en_ligne. With a share, the way he pays that share.",
                        obligatoire=False,
                    ),
                    Parametre("part", type="number", description="Only for a split payment: the amount in euros he pays the first way.", obligatoire=False),
                    Parametre("moyen_reste", description="Only for a split payment: how he pays the rest.", obligatoire=False),
                    Parametre("rendu_sur", type="number", description="Cash: the amount in euros of the note he pays with, so the change is prepared.", obligatoire=False),
                    Parametre("note", description="A request about the whole order (an allergy, a floor code), as he said it.", obligatoire=False),
                    Parametre("consigne", description="A habit to remember for his next call (« always without onions »). Never an allergy.", obligatoire=False),
                    Parametre("heure", description="Only for an order for later: the exact date and time (ISO, from the date tool).", obligatoire=False),
                    Parametre("confirmer", type="boolean", description="True ONLY once the caller said yes to the reading of the order.", obligatoire=False),
                    Parametre(
                        "en_plus", type="boolean",
                        description="The caller's answer to the offer of something more the tool just made: true adds the offered item, false adds nothing. Only right after that offer.",
                        obligatoire=False,
                    ),
                    Parametre("articles", description="Only real items the caller names in the same breath (« and a tiramisu »), as he said them. Never a yes, a no or an answer: those are en_plus or nothing.", obligatoire=False),
                ),
                serialise_avec="panier",
                ecrit=True,
                preparer=_jamais,
                resultat=_jamais,
            ),
        ),
    )
)
