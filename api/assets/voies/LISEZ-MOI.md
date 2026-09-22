# Les rues de France, par département

Ces fichiers servent à vérifier la rue qu'un appelant donne à l'agent vocal
(`api/services/voies/`). Un fichier par département, compressé, lu en lecture
seule et décompressé une fois au premier usage.

## Origine et licence

**Base Adresse Nationale** — <https://adresse.data.gouv.fr>
Export hebdomadaire **figé du 2026-09-16** (`weekly`), adresses **et** lieux-dits.

Données publiées sous **Licence Ouverte 2.0** (Etalab). Réutilisation libre, y
compris commerciale, sous réserve de mentionner la source et la date de la
version utilisée — ce que fait ce fichier.

## Ce que contient chaque fichier

Une base SQLite d'une table `voies`, une ligne par rue et par commune :

| Colonne | Contenu |
|---|---|
| `insee` | le code de la commune |
| `nom` | le nom officiel de la rue |
| `coeur` | le nom sans son type (« rue de la République » → « republique ») |
| `cle_sonore`, `cle_phon`, `son` | les trois clés de comparaison, **précalculées** |
| `numeros` | les numéros connus sur cette rue |

**2 443 800 rues, 34 882 communes**, France et outre-mer. Les arrondissements de
Paris, Lyon et Marseille sont ramenés au code de leur commune.

⚠️ La BAN ne couvre pas la Polynésie, la Nouvelle-Calédonie, Wallis-et-Futuna ni
les TAAF : 82 communes y sont sans rue, plus 5 en métropole quasiment inhabitées
(dont trois villages détruits de Verdun). Pour un appelant de ces communes, la
rue sort « introuvable » et l'agent la fait épeler une fois.

## Mettre à jour (environ une fois par an)

```bash
PYTHONPATH=. api/.venv/Scripts/python.exe -m api.scripts.mark.generer_base_voies
```

Puis, **dans le même commit** :

1. pointer `EXPORT` sur la nouvelle date dans `api/services/voies/base.py` ;
2. régénérer l'index de test
   (`api.scripts.mark.extraire_index_de_test <dossier de l'index complet>`) ;
3. supprimer les anciens fichiers de ce dossier ;
4. relancer `api/tests/mark/test_recherche_voie.py`.

⛔ Les quatre ensemble : sinon le contrôle de démarrage signale une erreur sur un
simple décalage de commit.

🔑 Les clés sont calculées par le script, **jamais à l'appel** (1,9 s pour Paris
sinon). Changer `sans_type`, `normaliser` ou les clés sonores oblige à
régénérer : `test_recherche_voie.py` compare les clés stockées à celles que le
code recalcule, et rougit en cas d'écart.
