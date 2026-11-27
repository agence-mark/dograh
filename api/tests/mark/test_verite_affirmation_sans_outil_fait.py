"""[.mark] SA-36 (M87) : l'agent annonce comme fait ce qu'aucun outil de ce tour n'a rendu fait.

Constats (production, « Tester au clavier », workflow 299 -> agent de commande 300) :

- appel 2571, dernier tour : « À emporter. » ; trois ``ajouter`` rendent ``INCOMPLETE`` (``manque: mode``), le quatrième ``plafond``.
  L'agent dit « C'est noté pour vos deux pizzas Regina normales à emporter pour demain soir, mardi dix-sept novembre à huit heures et
  demie. » Rien n'est posé. La réplique d'origine avait été retenue pour « 8 h 30 » (chiffre sans source) ; la RELANCE, rendue telle
  quelle sans contrôle, a dit le faux.
- appel 2572, tour 2 : « Huit heures et demie, à emporter. » ; seul ``resoudre_une_date`` rend ``AMBIGU`` (``manque: heure``). L'agent dit
  « C'est noté pour le retrait de vos deux Regina normales mardi dix-sept novembre. » ; « noté » n'était pas dans les tournures contrôlées.

Le mécanisme (commun, aucun mot de métier) : quand TOUS les résultats d'outil du tour disent « pas fait » (``manque``, statut incomplet,
ambigu, invalide, plafond, échec, refus), une réplique qui affirme que c'est fait (« c'est noté », « j'ai ajouté », « c'est enregistré »…)
est retenue et REMPLACÉE par ce que le dernier outil demande (``texte_a_dire`` / ``suggestion``), sans relance. La relance d'une autre
retenue est contrôlée de même.

| Test | Ce qu'il prouve |
|---|---|
| 2571 | la réplique de production est remplacée par « À emporter ou en livraison ? », aucune relance |
| 2571 relance | une réplique retenue pour un chiffre, dont la relance affirme le faux : la relance est remplacée par la question de l'outil |
| 2572 | la réplique de production est remplacée par la question de l'heure |
| sains | un tour avec un outil qui a fait, un tour sans outil, une question, une réplique qui pose la question : rien n'est retenu |
| sans question | aucun outil ne propose de texte : la retenue relance le modèle avec la consigne, comme avant |
"""

from __future__ import annotations

import json

from api.services.workflow import chiffres_sans_source as c
from api.services.workflow.verite_des_actions import RAISON_ACTION_NON_FAITE, VerificateurDeReplique
from api.tests.mark.test_verite_des_actions import Banc, _morceau, _reponse, _service, _texte  # noqa: F401
from api.tests.mark.test_verite_des_actions import _Contexte

RESTITUTION = "Reformule ce texte avec tes mots, naturellement, en gardant exactement les mêmes faits (montants, heures, noms, quantités)."


def _outil(resultat: dict, n: int) -> list[dict]:
    return [
        {"role": "assistant", "content": None, "tool_calls": [{"id": f"t{n}", "type": "function", "function": {"name": "outil", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": f"t{n}", "content": json.dumps(resultat, ensure_ascii=False)},
    ]


def _demande(statut: str, suggestion: str, manque: str, faits: dict | None = None) -> dict:
    return {
        "statut": statut, "faits": faits or {}, "suggestion": suggestion, "manque": manque,
        "restitution": "reformule", "texte_a_dire": suggestion, "consigne_de_restitution": RESTITUTION,
    }


MODE = _demande("INCOMPLETE", "À emporter ou en livraison ?", "mode", {"modes": ["emporter", "livraison"], "panier": {"mode": None, "articles": 0}})
PLAFOND = {"statut": "plafond", "consigne": "Tu as déjà fait trois appels d'outil pour cette parole de la personne : n'en fais pas d'autre."}
HEURE = _demande("INCOMPLETE", "À quelle heure, mardi dix-sept novembre ?", "heure", {"jour": "2026-11-17"})
AMBIGU = _demande("AMBIGU", "Est-ce huit heures trente ou vingt heures trente ?", "heure", {"candidats_heure": ["huit heures trente", "vingt heures trente"]})

# Appel 2571 : le premier tour (date, mode invalide), le deuxième (l'heure, sans outil), puis le dernier.
MESSAGES_2571 = [
    {"role": "user", "content": "Bonsoir, je voudrais commander pour demain soir, deux Regina normales."},
    *_outil(HEURE, 1),
    *_outil({**MODE, "statut": "ARGUMENT_INVALIDE"}, 2),
    {"role": "assistant", "content": "C'est entendu pour vos deux pizzas Regina normales pour demain soir. À emporter ou en livraison ?"},
    {"role": "user", "content": "Huit heures et demie."},
    {"role": "assistant", "content": "C'est bien noté. Est-ce que vous souhaitez les récupérer à emporter ou préférez-vous une livraison ?"},
    {"role": "user", "content": "À emporter."},
    *_outil(MODE, 3),
    *_outil(MODE, 4),
    *_outil(MODE, 5),
    *_outil(PLAFOND, 6),
]
DIT_2571 = (
    "C'est noté pour vos deux pizzas Regina normales à emporter pour demain soir, mardi dix-sept novembre à huit heures et demie. "
    "Est-ce que vous désirez autre chose ?"
)

MESSAGES_2572 = [
    {"role": "user", "content": "Bonsoir, je voudrais commander pour demain soir, deux Regina normales."},
    *_outil(HEURE, 1),
    *_outil({**MODE, "statut": "ARGUMENT_INVALIDE"}, 2),
    {"role": "assistant", "content": "C'est entendu pour vos deux Regina normales pour mardi dix-sept novembre. À emporter ou en livraison ?"},
    {"role": "user", "content": "Huit heures et demie, à emporter."},
    *_outil(AMBIGU, 3),
]
DIT_2572 = (
    "C'est noté pour le retrait de vos deux Regina normales mardi dix-sept novembre. "
    "Pour l'heure, est-ce que vous préférez huit heures et demie du matin ou vingt heures et demie du soir ?"
)


def _banc_de_prod() -> Banc:
    """Comme l'agent 300 en production : la garde des chiffres allumée (elle a retenu « 8 h 30 » sur 2571)."""
    banc = Banc()
    banc.agent.reglages = {c.CLE_CHIFFRE_SANS_SOURCE: True}
    return banc


async def _jouer_avec(service, messages):
    return [m async for m in await service.get_chat_completions(_Contexte(list(messages)))]


async def test_2571_c_est_note_apres_trois_incomplets_et_un_plafond_relance_le_modele_sans_dire_le_texte_de_l_outil():
    banc = _banc_de_prod()
    service = _service([_morceau(DIT_2571), _morceau(fin="stop")], banc, _reponse("jamais"))
    morceaux = await _jouer_avec(service, MESSAGES_2571)
    # Lot 8d (périmé par REPRISE.md:30 : « le modèle parle, jamais le code ») : plus remplacée par le texte de l'outil ; le modèle est relancé avec la consigne.
    assert _texte(morceaux) == "jamais" and "À emporter ou en livraison ?" not in _texte(morceaux)
    assert len(service.requetes) == 1
    retenue = VerificateurDeReplique(banc.moteur, banc.agent).controler(DIT_2571, MESSAGES_2571)
    assert retenue.raison == RAISON_ACTION_NON_FAITE and retenue.detail.casefold().startswith("c'est noté")


async def test_2571_la_relance_d_une_retenue_qui_affirme_le_faux_ne_dit_pas_le_texte_de_l_outil():
    banc = _banc_de_prod()
    origine = "Vos deux pizzas seront prêtes à 21 h 15."  # retenue pour le chiffre sans source
    service = _service([_morceau(origine), _morceau(fin="stop")], banc, _reponse(DIT_2571))
    morceaux = await _jouer_avec(service, MESSAGES_2571)
    assert len(service.requetes) == 1  # la relance a bien eu lieu
    assert "À emporter ou en livraison ?" not in _texte(morceaux)  # lot 8d : jamais le texte de l'outil dit par le code


async def test_2572_c_est_note_apres_une_heure_ambigue_relance_le_modele_sans_dire_le_texte_de_l_outil():
    banc = _banc_de_prod()
    service = _service([_morceau(DIT_2572), _morceau(fin="stop")], banc, _reponse("jamais"))
    morceaux = await _jouer_avec(service, MESSAGES_2572)
    assert _texte(morceaux) == "jamais" and "huit heures trente ou vingt" not in _texte(morceaux)  # lot 8d : relancé, jamais remplacé par le texte de l'outil
    assert len(service.requetes) == 1


async def test_sains_rien_n_est_retenu():
    banc = _banc_de_prod()
    v = VerificateurDeReplique(banc.moteur, banc.agent)
    # un outil du tour a fait : « c'est noté » est fondé
    fait = [{"role": "user", "content": "Deux Regina à emporter."}, *_outil(MODE, 1), *_outil({"statut": "OK", "faits": {"panier": {"articles": 2}}}, 2)]
    assert v.controler("C'est noté, deux Regina à emporter. Autre chose ?", fait) is None
    # aucun outil dans ce tour (les « pas fait » d'un tour précédent ne comptent pas) : la règle d'avant
    sans_outil = [*MESSAGES_2572, {"role": "assistant", "content": "Est-ce huit heures trente ou vingt heures trente ?"}, {"role": "user", "content": "Le soir, au nom de Julien."}]
    assert v.controler("C'est noté pour Julien.", sans_outil) is None
    # la réplique pose la question de l'outil, ou une question seulement
    assert v.controler("À emporter ou en livraison ?", MESSAGES_2571) is None
    assert v.controler("Très bien. C'est noté ?", MESSAGES_2571) is None
    assert v.controler("Je n'ai pas encore le mode : à emporter ou en livraison ?", MESSAGES_2571) is None


async def test_sans_question_proposee_la_retenue_relance_le_modele_avec_la_consigne():
    banc = _banc_de_prod()
    messages = [{"role": "user", "content": "À emporter."}, *_outil(PLAFOND, 1)]
    service = _service([_morceau("C'est noté, c'est à emporter."), _morceau(fin="stop")], banc, _reponse("À emporter ou en livraison ?"))
    morceaux = await _jouer_avec(service, messages)
    assert _texte(morceaux) == "À emporter ou en livraison ?"
    [requete] = service.requetes
    assert any("aucun outil de ce tour" in (m.get("content") or "") for m in requete["messages"])
