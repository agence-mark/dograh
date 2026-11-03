"use client";

/**
 * [.mark] Réglages › Affichage (K1, forme provisoire E117) : la langue de l'écran et le passage jour / nuit, sortis du
 * pied de la barre latérale (décision d'Evan, 04/11). Aucun réglage nouveau : ce sont les deux d'avant.
 */
import { useEffect, useState } from "react";

import { type Langue, useLangue } from "@/components/mark/langue/langue";
import { LigneChamp } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";

type Theme = "light" | "dark";

export function PanneauAffichage() {
    const { t, langue, choisir } = useLangue();
    const [theme, setTheme] = useState<Theme>("light");
    useEffect(() => setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light"), []);

    const poserTheme = (v: string) => {
        const suivant = v as Theme;
        setTheme(suivant);
        try {
            localStorage.setItem("theme", suivant);
        } catch {
            /* le choix tient jusqu'au rechargement */
        }
        document.documentElement.classList.toggle("dark", suivant === "dark");
    };

    return (
        <div className="divide-y border-y">
            <LigneChamp libelle={t({ en: "Screen language", fr: "Langue de l'écran" })}>
                <Liste
                    className="w-56"
                    valeur={langue}
                    changer={(v) => choisir(v as Langue)}
                    options={[
                        { valeur: "fr", libelle: "Français" },
                        { valeur: "en", libelle: "English" },
                    ]}
                />
            </LigneChamp>
            <LigneChamp libelle={t({ en: "Theme", fr: "Thème" })}>
                <Liste
                    className="w-56"
                    valeur={theme}
                    changer={poserTheme}
                    options={[
                        { valeur: "light", libelle: t({ en: "Day", fr: "Jour" }) },
                        { valeur: "dark", libelle: t({ en: "Night", fr: "Nuit" }) },
                    ]}
                />
            </LigneChamp>
        </div>
    );
}
