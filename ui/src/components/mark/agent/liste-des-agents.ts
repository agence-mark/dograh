/** [.mark] Où mène la flèche retour d'un agent : la liste de l'espace d'où l'on vient (le Labo par défaut). */
export const adresseDesAgents = (espace: number | "labo" | null): string =>
    typeof espace === "number" ? `/clients/${espace}/agents` : "/labo/agents";
