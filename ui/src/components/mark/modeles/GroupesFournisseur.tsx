"use client";

/**
 * [.mark] The settings of a provider, in sub-menus by group (chantier
 * reorganisation-ecran-reglages, step 6, convention E2).
 *
 * The groups are declared in the Python schema (`mark_groupe`, with the label
 * `mark_libelle`, in `api/services/configuration/registry.py`); their titles
 * and order live here, with every text in both languages. A provider whose
 * fields declare no group is drawn by `ServiceConfigurationForm` as before.
 *
 * - A group with a single visible setting is drawn flat, without a sub-menu.
 * - A field without a group goes in « Other », last: a field added upstream is
 *   never lost, it just waits to be filed.
 * - Which fields are visible is decided by the form (`getConfigFields`, the
 *   model rule), never here: grouping only arranges what the form shows.
 * - A closed sub-menu keeps its values: the form holds them, not the inputs.
 */
import { ChevronDown } from "lucide-react";
import { type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";

/** The groups, in the order they are shown. */
export const GROUPES_FOURNISSEUR: Record<string, Texte> = {
    langue: { en: "Language", fr: "Langue" },
    voix: { en: "Voice", fr: "Voix" },
    generation: { en: "Generation", fr: "Génération" },
    repetition: { en: "Repetition", fr: "Répétitions" },
    fin_de_tour: { en: "End of turn", fr: "Fin de tour" },
    mise_en_forme: { en: "Text formatting", fr: "Mise en forme du texte" },
    vocabulaire: { en: "Vocabulary", fr: "Vocabulaire" },
    hebergement: { en: "Hosting and privacy", fr: "Hébergement et confidentialité" },
    analyse: { en: "Analysis", fr: "Analyse" },
    technique: { en: "Technical", fr: "Technique" },
};

export const AUTRES = "autres";
const TITRE_AUTRES: Texte = { en: "Other", fr: "Autres" };

export interface MetaChamp {
    mark_groupe?: string;
    mark_libelle?: Texte;
}

/** The visible fields, in groups, in the order above ; unknown groups after, « Other » last. */
export const grouperChamps = (champs: string[], meta: (champ: string) => MetaChamp | undefined) => {
    const parGroupe = new Map<string, string[]>();
    for (const champ of champs) {
        const groupe = meta(champ)?.mark_groupe ?? AUTRES;
        parGroupe.set(groupe, [...(parGroupe.get(groupe) ?? []), champ]);
    }
    const rang = (groupe: string) => {
        if (groupe === AUTRES) return Number.MAX_SAFE_INTEGER;
        const i = Object.keys(GROUPES_FOURNISSEUR).indexOf(groupe);
        return i === -1 ? Number.MAX_SAFE_INTEGER - 1 : i;
    };
    return [...parGroupe.entries()]
        .sort(([a], [b]) => rang(a) - rang(b))
        .map(([id, liste]) => ({ id, champs: liste }));
};

export const titreGroupe = (id: string): Texte =>
    id === AUTRES ? TITRE_AUTRES : GROUPES_FOURNISSEUR[id] ?? { en: id, fr: id };

/** A readable label and the technical name in grey (E5). */
export const LibelleChamp = ({ champ, libelle, htmlFor }: { champ: string; libelle?: Texte; htmlFor?: string }) => {
    const { t } = useLangue();
    return (
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <label htmlFor={htmlFor} className="text-sm font-medium leading-none">
                {libelle ? t(libelle) : champ.replace(/_/g, " ")}
            </label>
            <code className="text-[11px] text-muted-foreground/80" data-cle-technique={champ}>
                {champ}
            </code>
        </span>
    );
};

export const SousMenuFournisseur = ({
    id,
    nombre,
    children,
}: {
    /** `${service}.${groupe}`, unique on the page. */
    id: string;
    nombre: number;
    children: ReactNode;
}) => {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    const groupe = id.split(".").pop() ?? id;
    const idContenu = `sous-menu-${id.replace(/\./g, "-")}`;
    return (
        <div className="rounded-md border" data-sous-menu={id}>
            <button
                type="button"
                aria-expanded={ouvert}
                aria-controls={idContenu}
                onClick={() => setOuvert((avant) => !avant)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
                <span className="flex-1 text-sm font-medium">{t(titreGroupe(groupe))}</span>
                <span className="text-xs text-muted-foreground">
                    {nombre} {t({ en: "settings", fr: "réglages" })}
                </span>
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", ouvert && "rotate-180")} />
            </button>
            {ouvert && (
                <div id={idContenu} className="grid grid-cols-2 gap-4 border-t px-4 py-4">
                    {children}
                </div>
            )}
        </div>
    );
};
