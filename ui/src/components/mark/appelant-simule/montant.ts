/** Un montant à deux décimales, à la façon de la langue (virgule en français). Partie 3, lot 12 : dépense du mois d'un rôle. */
export const montant = (valeur: number | undefined, langue: string) =>
    (valeur ?? 0).toLocaleString(langue === "fr" ? "fr-FR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
