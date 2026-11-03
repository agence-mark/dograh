"""[.mark] Builder, lot M (pièce 9 de Cognigy, licence MIT) : la batterie de non-régression du BUILDER lui-même (pas celle des agents).

Un cas s'écrit comme une demande d'utilisateur (sans nommer l'action), avec des correcteurs (action appelée ou interdite, ordre,
motif dans la trace, juge à rubrique), une plateforme simulée (réponses imposées par cas) et une référence enregistrée avec une
empreinte par cas : la comparaison échoue si un cas passe moins souvent qu'avant.

Rien ici n'appelle un modèle : les cas de ce dépôt rejouent un cerveau SCRIPTÉ (le comportement attendu), ce qui prouve les correcteurs,
la plateforme simulée et la référence. Rejouer la batterie avec un vrai cerveau est une dépense : ``lancer`` accepte n'importe quel cerveau,
mais personne ne le lance sans la phrase d'Evan. « Un succès peut l'être pour une mauvaise raison » : la trace de chaque essai est gardée.
"""
