"use client";

/**
 * [.mark] Grammaire des marques (E19 à E25, E100) : une seule forme de badge, quatre tons, une pastille rouge
 * réservée à ce qui demande une action, des étiquettes en contour, des points d'état. Aucune couleur écrite ici :
 * tout passe par les jetons `--marque-*` de `app/mark-theme.css` (jamais d'orange, E100).
 */
import { ChevronDown, Tag, X } from "lucide-react";

import { useLangue } from "@/components/mark/langue/langue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type TonMarque = "neutre" | "succes" | "attention" | "danger" | "plein";

const TONS: Record<TonMarque, string> = {
    neutre: "bg-(--marque-neutre) text-(--marque-neutre-texte)",
    succes: "bg-(--marque-succes) text-(--marque-succes-texte)",
    attention: "bg-(--marque-attention) text-(--marque-attention-texte)",
    danger: "bg-(--marque-danger) text-(--marque-danger-texte)",
    plein: "bg-(--marque-plein) text-(--marque-plein-texte)",
};

export function Marque({ ton = "neutre", children }: { ton?: TonMarque; children: React.ReactNode }) {
    return (
        <span
            data-ton={ton}
            className={`inline-flex h-5 items-center rounded-full px-1.5 text-[11px] font-medium leading-none tracking-[0.01em] ${TONS[ton]}`}
        >
            {children}
        </span>
    );
}

/** Pastille de notification : rouge seulement quand il faut agir ; sinon un simple compteur gris. */
export function Pastille({ n, urgent = false }: { n?: number; urgent?: boolean }) {
    if (urgent) {
        return (
            <span
                data-urgente=""
                className="inline-flex size-4 items-center justify-center rounded-full bg-(--pastille-urgente) text-[10px] font-semibold text-white"
            >
                {n ?? "!"}
            </span>
        );
    }
    return (
        <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-(--marque-neutre) px-1 text-[10px] font-medium text-muted-foreground">
            {n}
        </span>
    );
}

/** Étiquette posée par l'équipe : contour, icône, croix pour la retirer (si `retirer` est donné). */
export function Etiquette({ children, retirer }: { children: React.ReactNode; retirer?: () => void }) {
    const { t } = useLangue();
    return (
        <span className="inline-flex h-6 items-center gap-1 rounded-full border bg-background px-2 text-xs text-foreground">
            <Tag className="size-3 text-muted-foreground" /> {children}
            {retirer && (
                <button
                    type="button"
                    onClick={retirer}
                    aria-label={t({ en: "Remove the label", fr: "Retirer l'étiquette" })}
                    className="text-muted-foreground hover:text-foreground"
                >
                    <X className="size-3" />
                </button>
            )}
        </span>
    );
}

export type EtatPoint = "publie" | "brouillon" | "panne" | "fini" | "attente";

const POINTS: Record<EtatPoint, string> = {
    publie: "bg-(--point-publie)",
    panne: "bg-(--pastille-urgente)",
    fini: "bg-(--point-fini)",
    // « attend quelqu'un » : le bleu .mark, jamais d'orange (E100).
    attente: "bg-(--acc)",
    brouillon: "border-[1.5px] border-(--point-fini) bg-transparent",
};

/** Point d'état : plein = publié, anneau = brouillon, rouge = en panne, gris = terminé, bleu = attend quelqu'un. */
export function PointEtat({ etat, children }: { etat: EtatPoint; children: React.ReactNode }) {
    return (
        <span className="inline-flex items-center gap-1.5 text-sm">
            <span data-etat={etat} className={`size-2 rounded-full ${POINTS[etat]}`} />
            {children}
        </span>
    );
}

/** Bouton bloquant : la raison est sur le bouton, le détail dans le menu. */
export function BoutonBloque({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="inline-flex h-8 items-stretch overflow-hidden rounded-[10px] bg-(--pastille-urgente) text-[13px] font-medium text-white"
        >
            <span className="flex items-center px-2.5">{children}</span>
            <span className="flex items-center border-l border-white/25 px-1.5">
                <ChevronDown className="size-4" />
            </span>
        </button>
    );
}

/** Précision utile (E20) : un « ! » dans un cercle, le texte au survol. Jamais de phrase d'explication en dur. */
export function Info({ children }: { children: React.ReactNode }) {
    const { t } = useLangue();
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                {/* Un span et non un bouton : le « ! » se pose aussi dans une ligne ou une carte cliquable. */}
                <span
                    role="button"
                    tabIndex={0}
                    aria-label={t({ en: "More information", fr: "Précision" })}
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex size-4 shrink-0 items-center justify-center rounded-full border border-(--point-fini) align-middle text-[10px] font-semibold leading-none text-muted-foreground hover:border-foreground hover:text-foreground"
                >
                    !
                </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs leading-snug">{children}</TooltipContent>
        </Tooltip>
    );
}

/** Gravité d'un point « À améliorer » (E100) : pastille pleine foncée, écriture blanche. */
const GRAVITES = {
    3: { mot: { en: "Serious", fr: "Grave" }, fond: "bg-(--gravite-grave)" },
    2: { mot: { en: "To watch", fr: "À surveiller" }, fond: "bg-(--gravite-surveiller)" },
    1: { mot: { en: "Minor", fr: "Faible" }, fond: "bg-(--gravite-faible)" },
} as const;

export function Gravite({ n }: { n: 1 | 2 | 3 }) {
    const { t } = useLangue();
    const g = GRAVITES[n];
    return (
        <span
            data-gravite={n}
            className={`inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-full px-2 text-[11px] font-medium text-white ${g.fond}`}
        >
            {t(g.mot)}
        </span>
    );
}

/** Note du juge : une pastille rouge quand elle passe sous le seuil ; « – » quand il n'y en a pas. */
export function NoteJuge({ note, seuil = 3.5 }: { note: number | null; seuil?: number }) {
    if (note === null) return <span className="text-muted-foreground">–</span>;
    return (
        <span className="inline-flex items-center gap-1.5 tabular-nums">
            {String(note).replace(".", ",")}
            {note < seuil && <Pastille urgent />}
        </span>
    );
}
