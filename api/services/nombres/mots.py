"""[.mark] The French number words, shared by the number reader and the town analysis.

Kept apart so that ``communes.analyse`` can know them without importing the
reader, which itself uses the analysis.
"""

UNITES = (
    "zero un deux trois quatre cinq six sept huit neuf dix onze douze treize "
    "quatorze quinze seize"
).split()
DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
MOTS_NOMBRE = frozenset(UNITES) | frozenset(DIZAINES.values()) | {"cent", "cents", "mille", "vingts"}
