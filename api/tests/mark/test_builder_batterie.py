"""[.mark] Builder partie 2, lot M (pièce 9 de Cognigy) : la batterie de non-régression du builder lui-même.

Cerveau scripté, plateforme simulée : aucun appel de modèle, aucune base.

| Test | Ce qu'il prouve |
|---|---|
| cas du dépôt | chacun passe 3 fois sur 3 avec son script, et la référence du dépôt est à jour (empreintes) |
| correcteurs | action appelée, interdite, ordre, motif ; un juge absent = non jugé = pas un succès ; un juge fourni tranche |
| régression | un cas dont le comportement dérive passe moins souvent : la comparaison échoue ; un cas modifié ou sans référence aussi |
"""

from __future__ import annotations

import pytest

from api.services.builder.batterie import cas as modele_cas
from api.services.builder.batterie import lancer
from api.services.builder.batterie.cas import Cas, Correcteur
from api.services.builder.batterie.correcteurs import Trace, corriger
from api.services.builder.cerveau.factice import CerveauFactice, appel, texte, tour


def un_cas(**extras) -> Cas:
    base = {
        "id": "c",
        "demande": "Montre-moi mon agent.",
        "tours": [[{"appel": "agent_montrer_le_graphe"}], [{"texte": "Voilà."}]],
        "correcteurs": [{"genre": "appelee", "actions": ["agent_montrer_le_graphe"]}],
    }
    return Cas.model_validate({**base, **extras})


async def test_les_cas_du_depot_passent_tous_et_la_reference_est_a_jour():
    cas = modele_cas.charger()
    assert len(cas) >= 6 and len({c.id for c in cas}) == len(cas)
    resultats = await lancer.lancer()
    assert all(r["reussis"] == r["essais"] == 3 for r in resultats.values()), {k: v["raisons"] for k, v in resultats.items() if v["reussis"] < 3}
    assert lancer.comparer(resultats, lancer.lire_la_reference()) == []  # référence et empreintes à jour


async def test_les_correcteurs_lisent_la_trace():
    trace = Trace(
        appels=[{"nom": "a", "arguments": {}, "resultat": {}}, {"nom": "b", "arguments": {}, "resultat": {}}, {"nom": "a", "arguments": {}, "resultat": {}}],
        textes=["Rien n'est publié."],
    )
    assert (await corriger(Correcteur(genre="appelee", actions=["a", "b"]), trace))[0] is True
    assert (await corriger(Correcteur(genre="appelee", actions=["c"]), trace))[0] is False
    assert (await corriger(Correcteur(genre="interdite", actions=["c"]), trace))[0] is True
    assert (await corriger(Correcteur(genre="interdite", actions=["b"]), trace))[0] is False
    assert (await corriger(Correcteur(genre="ordre", actions=["a", "b", "a"]), trace))[0] is True
    assert (await corriger(Correcteur(genre="ordre", actions=["b", "a", "b"]), trace))[0] is False
    assert (await corriger(Correcteur(genre="motif", motif="rien n'est publié"), trace))[0] is True
    assert (await corriger(Correcteur(genre="motif", motif="publié sans"), trace))[0] is False


async def test_un_correcteur_juge_sans_juge_n_est_jamais_un_succes():
    juge_seul = un_cas(correcteurs=[{"genre": "juge", "rubrique": "poli"}])
    sans = await lancer.jouer(juge_seul, lancer.cerveau_scripte(juge_seul))
    assert sans.reussi is False and sans.non_juge is True

    async def juge(rubrique, trace):
        return ("Voilà" in trace, "ok" if "Voilà" in trace else "non")

    avec = await lancer.jouer(juge_seul, lancer.cerveau_scripte(juge_seul), juge)
    assert avec.reussi is True and avec.non_juge is False

    async def juge_severe(rubrique, trace):
        return False, "pas poli"

    assert (await lancer.jouer(juge_seul, lancer.cerveau_scripte(juge_seul), juge_severe)).raisons == ["pas poli"]


async def test_la_plateforme_simulee_impose_la_reponse_du_cas():
    cas = un_cas(plateforme={"agent_montrer_le_graphe": {"ok": False, "erreur": "Imposée."}}, correcteurs=[{"genre": "motif", "motif": "Imposée"}])
    essai = await lancer.jouer(cas, lancer.cerveau_scripte(cas))
    assert essai.reussi and "Imposée" in essai.trace


async def test_un_script_epuise_laisse_les_correcteurs_juger_ce_qui_a_eu_lieu():
    cas = un_cas(tours=[])
    essai = await lancer.jouer(cas, lancer.cerveau_scripte(cas))
    assert essai.reussi is False and "never called" in essai.raisons[0]


async def test_un_cas_qui_derive_passe_moins_souvent_et_la_comparaison_echoue():
    cas = un_cas()
    reference = await lancer.lancer(cas_a_jouer=[cas])
    assert reference["c"]["reussis"] == 3 and lancer.comparer(reference, reference) == []

    def ne_fait_plus_l_action(_cas):
        return CerveauFactice(tour(texte("Je ne sais pas.")))

    regresse = await lancer.lancer(ne_fait_plus_l_action, cas_a_jouer=[cas])
    assert regresse["c"]["reussis"] == 0
    assert "passes 0/3, it passed 3/3" in lancer.comparer(regresse, reference)[0]

    # Un cas à moitié réussi (2 sur 3) passe moins souvent qu'une référence à 3 sur 3.
    cerveaux = iter([lancer.cerveau_scripte(cas), CerveauFactice(tour(texte("non"))), lancer.cerveau_scripte(cas)])
    moitie = await lancer.lancer(lambda _c: next(cerveaux), cas_a_jouer=[cas])
    assert moitie["c"]["reussis"] == 2 and lancer.comparer(moitie, reference)


async def test_un_cas_modifie_ou_sans_reference_est_signale():
    cas = un_cas()
    reference = await lancer.lancer(cas_a_jouer=[cas])
    modifie = await lancer.lancer(cas_a_jouer=[un_cas(demande="Autre demande.")])
    assert "changed since the reference" in lancer.comparer(modifie, reference)[0]
    nouveau = await lancer.lancer(cas_a_jouer=[cas, un_cas(id="autre")])
    assert lancer.comparer(nouveau, reference) == ["autre: case without a reference (record it)"]
    assert lancer.comparer({}, reference) == ["c: case missing from this run"]


def test_un_cas_nomme_une_demande_d_utilisateur_pas_une_action():
    """« Écrits comme une demande d'utilisateur » : la demande ne cite le nom d'aucune action du registre."""
    from api.services.builder import actions

    for cas in modele_cas.charger():
        cites = [nom for nom in actions.REGISTRE if nom in cas.demande]
        assert cites == [], (cas.id, cites)


@pytest.mark.parametrize("genre", ["appelee", "interdite", "ordre", "motif", "juge"])
def test_un_genre_de_correcteur_inconnu_est_refuse(genre):
    assert Correcteur(genre=genre).genre == genre
    with pytest.raises(ValueError):
        Correcteur(genre="inconnu")
