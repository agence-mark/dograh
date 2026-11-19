"""[.mark] Banc A sur la fiche (chantier Partie 1, lot 3, D48) : les runs 2636 à 2678 écrits en fiches, À LA MAIN, une fiche par tour.

Règle (décision du coordinateur, 19/11) : chaque fiche porte EXACTEMENT les valeurs de l'ancien appel du tour (``donnees/runs_2636_2678.json``),
rien d'ajouté ni d'enlevé ; une fiche B12 du même scénario est prise telle quelle quand elle existe. Aucun traducteur automatique. Conventions
d'écriture, toutes sans choix de sens :

- ``dit`` : les ``mots`` de l'ancien appel (ce que la personne a dit dans ce tour) ; vide quand l'appel n'en portait pas ;
- le mode, l'adresse, la commune et la consigne que l'ancien code lisait dans les notes du greffier pour CET appel sont recopiés de ces notes ;
- les listes fermées passent d'une liste à l'autre : mode « en livraison », « livrer », « à livrer » → ``livraison`` ; « à emporter » → ``emporter`` ;
  moyen « carte » → ``carte_bancaire``, « especes » → ``especes`` ; sens ``accord`` → ``accepte``, ``refus`` → ``refuse``, tout autre sens → ``autre`` ;
- ``valider_la_commande`` répond par ``reponse`` à la question que l'ancien appel avait en attente (le ``manque`` du dernier geste d'avant : vente
  en plus, relecture, taille) ; sans question en attente, c'est ``c_est_tout`` ; tout autre ancien appel fait PENDANT une question en attente porte
  son ``sens`` en ``reponse`` (``modification`` → ``autre``) ;
- un article en phrase est découpé en champs (nom, quantité, taille dite, retraits) ; « normale(s) », « en taille normale », « en format normal » →
  ``Normale`` ; « mega » → ``Mega`` ; ``choix`` répondu à une question de taille → ``reponse.valeurs`` ;
- ``modifier`` → ``changer_quantite`` (la ligne nommée comme dans l'ancien appel, le montage la retrouve par son nom) ; quantité 0 → ``retirer_article`` ;
- ``lire_la_commande`` et ``heure_annoncee`` → ``lire`` (``produit`` → ``article``, ``offres``, ``delai``, ``commande`` → ``panier``) ;
- ``reponse.question_id`` vaut ``"?"`` : le montage y met l'identifiant de la question en attente (le run répondait à celle-là) ;
- un ancien appel répété dans le même tour n'est pas repris (contrat final : une fiche par tour) ; le code postal n'a pas de case (la commune le porte).

Ce qui imposerait un choix n'est PAS écrit : le run n'a pas de transcription au-delà (``SANS_TRANSCRIPTION``), et le test qui en dépend est en
``xfail(strict=True)`` avec sa ligne dans ``a-trancher.md``.
"""

from __future__ import annotations

from typing import Any

Q = "?"
N = "Normale"
M = "Mega"


def art(nom: str, quantite: int = 1, variante: str | None = None, **plus: Any) -> dict[str, Any]:
    return {"article": nom, "quantite": quantite, **({"variante": variante} if variante else {}), **plus}


def rep(sens: str, *valeurs: str) -> dict[str, Any]:
    return {"question_id": Q, "sens": sens, **({"valeurs": list(valeurs)} if valeurs else {})}


ADRESSE_REPUBLIQUE = {"adresse": "12 Rue de la République", "commune": "Senlis"}

# run -> [(tour, dit, fiche ou lecture)] ; une lecture s'écrit {"_lire": {...}}.
FICHES: dict[int, list[tuple[int, str, dict[str, Any]]]] = {
    2636: [
        (1, "je voudrais commander s'il vous plaît", {}),
        (2, "En livraison", {"mode_de_retrait": "livraison"}),
        (3, "12 rue de la République à Senlis", dict(ADRESSE_REPUBLIQUE)),
        (4, "Une reine normale et un coca", {"ajouter": [art("reine", 1, N), art("coca")]}),
        # B12, conv1-livraison-refus, tour 1 (même commande, même adresse, même proposition, mêmes mots) : prise telle quelle.
        (5, "Non merci, c'est tout", {"c_est_tout": True, "reponse": rep("refuse")}),
        (6, "Non, j'ai pas pris la mousse, enlevez-la", {"retirer_article": ["mousse au chocolat"], "reponse": rep("autre")}),
        (7, "Oui c'est ça", {"reponse": rep("accepte")}),
        (8, "Oui", {"reponse": rep("accepte")}),
        (9, "Par carte", {"moyen_de_paiement": "carte_bancaire"}),
        (10, "0600000000", {"moyen_de_paiement": "carte_bancaire", "telephone": "0600000000"}),
    ],
    2637: [
        (1, "Bonsoir, euh, c'est pour passer une commande", {}),
        (2, "Euh, en livraison", {"mode_de_retrait": "livraison"}),
        (3, "C'est au 12 rue de la République, Senlis", dict(ADRESSE_REPUBLIQUE)),
    ],
    2638: [
        (1, "je voudrais une reine normale en livraison au 12 rue de la République à Senlis, je paie par carte, c'est pour Evan",
         {"ajouter": [art("reine", 1, N)], "mode_de_retrait": "livraison", **ADRESSE_REPUBLIQUE}),
        (2, "Non, une seule reine", {"changer_quantite": [{"ligne": "Regina Normale", "quantite": 1}]}),
        (3, "Oui c'est tout", {"c_est_tout": True}),
        (4, "Non merci", {"reponse": rep("refuse")}),
        (5, "Oui", {"reponse": rep("accepte"), "moyen_de_paiement": "carte_bancaire", "prenom": "Evan"}),
        (6, "", {"moyen_de_paiement": "carte_bancaire", "prenom": "Evan", "telephone": "0600000000"}),
    ],
    2639: [
        (1, "Oui bonsoir, alors c'est pour Evan, je voudrais me faire livrer une reine en taille normale, au 12 rue de la République à Senlis, "
            "et je réglerai en carte", {"ajouter": [art("reine", 1, N)], "mode_de_retrait": "livraison", **ADRESSE_REPUBLIQUE}),
        (2, "Euh non, ce sera tout", {"c_est_tout": True}),
        (3, "Allez oui, un coca", {"reponse": rep("accepte", "un coca")}),
        (4, "Impeccable", {"reponse": rep("accepte")}),
        (5, "Je vous l'ai dit, en carte", {"moyen_de_paiement": "carte_bancaire"}),
        (6, "0600000000", {"prenom": "Evan", "telephone": "0600000000"}),
    ],
    2640: [
        (1, "Bonsoir, je voudrais commander en livraison s'il vous plaît", {"mode_de_retrait": "livraison"}),
        (2, "12 rue de la République, à Senlis", {"adresse": "12 rue de la République", "commune": "Senlis"}),
        (3, "", {"_lire": {"sujet": "article", "article": "pizza avec des sardines"}}),
        (4, "", {"_lire": {"sujet": "offres"}}),
        (6, "", {"_lire": {"sujet": "article", "article": "Neptune"}}),
        (7, "Oui, une Neptune normale", {"ajouter": [art("Neptune")]}),
    ],
    2642: [
        (1, "Bonsoir, c'est pour une commande à emporter", {"mode_de_retrait": "emporter"}),
        (2, "Alors une Reine normale, 1 4 fromages mega et une Calzone", {"ajouter": [art("Reine", 1, N), art("quatre fromages", 1, M), art("Calzone")]}),
        (3, "Normale", {"reponse": rep("accepte", "Normale")}),
        (4, "Ah super, oui un coca", {"reponse": rep("accepte", "Coca-Cola")}),
    ],
    2647: [
        (1, "Une calzone normale à livrer à Gouvieux s'il vous plaît", {"ajouter": [art("calzone", 1, N)], "mode_de_retrait": "livraison", "commune": "Gouvieux"}),
    ],
    2653: [
        (1, "Bonsoir, à emporter : une Regina normale, une Margherita mega et deux Coca",
         {"ajouter": [art("Regina", 1, N), art("Margherita", 1, M), art("Coca", 2)], "mode_de_retrait": "emporter"}),
        (2, "Ah, en fait la Regina, mettez-la plutôt en mega", {"changer_quantite": [{"ligne": "Regina", "variante": M}]}),
        (3, "Et 3 cocas au lieu de deux", {"changer_quantite": [{"ligne": "Coca-Cola", "quantite": 3}]}),
        (4, "Non c'est tout", {"c_est_tout": True}),
        (5, "Non, pas de dessert", {"reponse": rep("refuse")}),
        (6, "Non, la Regina je l'ai demandée en mega", {"changer_quantite": [{"ligne": "Regina", "variante": M}], "reponse": rep("autre")}),
        (7, "", {"_lire": {"sujet": "panier"}}),
        (8, "Non. Enlevez la Regina normale et mettez une Regina mega à la place",
         {"changer_quantite": [{"ligne": "Regina Normale", "variante": M, "quantite": 1}], "ajouter": [art("Regina", 1, M)]}),
        (9, "Non c'est tout", {"c_est_tout": True}),
        (10, "Non ! Il faut retirer la Regina normale, je veux une seule Regina, en mega",
         {"retirer_article": ["Regina Normale"], "ajouter": [art("Regina", 1, M)], "reponse": rep("autre")}),
    ],
    2663: [
        (1, "une reine normale sans champignons s'il vous plaît", {"ajouter": [art("reine", 1, N, sans=["champignons"])], "mode_de_retrait": "emporter"}),
        (2, "Et je voudrais aussi une pizza moitié reine moitié 4 fromages, en mega", {"ajouter": [art("pizza moitié-moitié", 1, M, moities=["reine", "4 fromages"])]}),
    ],
    2664: [
        (1, "Vous pouvez me faire une pizza moitié margherita moitié calzone ? En normale",
         {"ajouter": [art("pizza moitié-moitié", 1, moities=["margherita", "calzone"])], "mode_de_retrait": "emporter"}),
    ],
    2667: [
        (1, "je voudrais une commande à emporter pour 7 heures", {"mode_de_retrait": "emporter", "heure": "dix-neuf heures"}),
        (2, "Deux reines normales", {"ajouter": [art("reines", 2)]}),
        (3, "Normales j'ai dit", {"reponse": rep("autre", "Normale")}),
        (4, "Non merci, ça ira", {"reponse": rep("refuse")}),
        (5, "Ah non en fait, je préférerais la récupérer demain à 3 heures du matin", {"heure": "trois heures du matin demain", "reponse": rep("autre")}),
        (6, "À emporter, toujours", {"heure": "trois heures du matin demain", "mode_de_retrait": "emporter"}),
        (7, "Non c'est tout", {"c_est_tout": True}),
        (8, "Bon, alors midi", {"heure": "midi"}),
    ],
    2668: [
        (1, "je voudrais commander pour 8 heures et demie, à emporter, 3 margherita normales",
         {"ajouter": [art("margherita", 3, N)], "heure": "vingt heures trente", "mode_de_retrait": "emporter"}),
        (2, "Pas besoin, merci", {"reponse": rep("refuse")}),
    ],
    2671: [
        (1, "", {"_lire": {"sujet": "delai"}}),
        (2, "Livrer. C'est au 4 rue de Beauvais à Chantilly, deuxième étage, sonnez chez Dupont",
         {"mode_de_retrait": "livraison", "adresse": "4 rue de Beauvais", "commune": "Chantilly", "consigne_livreur": "deuxième étage, sonnez chez Dupont"}),
        (5, "Une margherita normale", {"ajouter": [art("margherita", 1, N)]}),
    ],
    2672: [
        (1, "je voudrais me faire livrer à Chantilly, une pizza Napoli normale", {"ajouter": [art("Napoli", 1, N)], "mode_de_retrait": "livraison", "commune": "Chantilly"}),
        (2, "", {"_lire": {"sujet": "delai"}}),
        (3, "Ajoutez une deuxième Napoli normale. C'est au 9 avenue du Bouteiller, et le livreur doit sonner à l'interphone 12",
         {"ajouter": [art("Napoli", 1, N)], "adresse": "9 avenue du Bouteiller", "consigne_livreur": "le livreur doit sonner à l'interphone 12"}),
    ],
    2677: [
        (2, "c'est pour une Salmone normale à emporter, je paie par carte, c'est Paul, 0600000000", {"ajouter": [art("Salmone", 1, N)], "mode_de_retrait": "emporter"}),
        (3, "Non c'est tout", {"c_est_tout": True}),
        (4, "Non", {"reponse": rep("refuse")}),
        (5, "Oui", {"reponse": rep("accepte"), "moyen_de_paiement": "carte_bancaire", "prenom": "Paul", "telephone": "0600000000"}),
        (6, "Ah mince, en fait je la voulais en mega, vous pouvez changer ?", {"changer_quantite": [{"ligne": "Salmone Normale"}]}),
    ],
}

# Les runs (ou la suite d'un run) qui ne s'écrivent pas sans choisir un sens : la raison est celle de la ligne de ``a-trancher.md``.
SANS_TRANSCRIPTION: dict[int, str] = {
    2643: "« deux margarita, une grande et une petite » : quelle taille est « grande », laquelle « petite » ? (la carte dit Normale et Mega)",
    2644: "tours 2 et 3 : `type_de_commande` repasse « deux pizzas reines normales » ; la fiche n'a pas de case « article déjà dit », seulement `ajouter` (qui additionne, E3)",
    2645: "tour 2 : « normales toutes les deux » est dans les mots et dans un `choix` libre, pas sur les articles ; le porter sur chaque article est un choix",
    2650: "tour 4 : `valider_la_commande` porte `sens: accord` sur « Non, c'est tout » ; recopier `accepte` contredit les mots, écrire `refuse` change la valeur",
    2652: "tour 2 : `type_de_commande` repasse « deux margherita normales » (même raison que 2644)",
    2668: "tours 3 et 4 : `type_de_commande` repasse « trois pizzas margherita normales » (même raison que 2644)",
    2670: "tour 2 et suivants : `sens: modification` avec la phrase entière en `articles` pendant une question d'ambiguïté : réponse ou nouvel ajout, c'est un choix",
}
