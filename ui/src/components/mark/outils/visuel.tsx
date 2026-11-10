"use client";

/**
 * [.mark] Clôture D2 (É55, É56, É60) : le visuel d'un outil et d'un connecteur, comme la maquette.
 * Un logiciel branché : son logo (jamais redessiné) ; un connecteur maison : sa tuile colorée ; un outil d'un type
 * de la maison : une tuile à la couleur du type (HTTP bleu, MCP nuit, fin d'appel rouge, transfert vert, vers un agent
 * violet, rappel turquoise, calculatrice ardoise). Les couleurs sont des constantes de marque (jamais d'orange).
 */
import { ArrowRightLeft, Calculator, CalendarClock, FolderSearch, Globe, type LucideIcon, PhoneForwarded, PhoneIncoming, PhoneOff, Server, Users } from "lucide-react";

import { logoDe } from "../integrations/logos";

export const COULEURS_TYPE: Record<string, string> = {
    http_api: "var(--outil-http)",
    integration: "var(--outil-http)",
    mcp: "var(--outil-mcp)",
    end_call: "var(--outil-fin)",
    transfer_call: "var(--outil-transfert)",
    transfer_agent: "var(--outil-agent)",
    native: "var(--outil-rappel)",
    calculator: "var(--outil-calcul)",
};
const ICONES_TYPE: Record<string, LucideIcon> = {
    http_api: Globe,
    integration: Globe,
    mcp: Server,
    end_call: PhoneOff,
    transfer_call: PhoneForwarded,
    transfer_agent: ArrowRightLeft,
    native: PhoneIncoming,
    calculator: Calculator,
};
/** Les connecteurs maison (sans logiciel du client) : leur tuile. */
const MAISON: Record<string, { couleur: string; icone: LucideIcon }> = {
    planificateur: { couleur: "var(--outil-http)", icone: CalendarClock },
    equipe: { couleur: "var(--outil-transfert)", icone: Users },
    dossier: { couleur: "var(--outil-agent)", icone: FolderSearch },
};

export function TuileMaison({ couleur, icone: I, taille = 40 }: { couleur: string; icone: LucideIcon; taille?: number }) {
    return (
        <span style={{ width: taille, height: taille, background: couleur }} className="inline-flex shrink-0 items-center justify-center rounded-lg text-white" aria-hidden>
            <I className="size-[48%]" strokeWidth={2.2} />
        </span>
    );
}

/** La tuile d'un connecteur maison (`null` quand ce n'en est pas un). */
export function tuileConnecteur(cle: string | null | undefined, integration: string | null | undefined, taille: number) {
    if (integration !== "interne") return null;
    const m = cle ? MAISON[cle] : undefined;
    return m ? <TuileMaison couleur={m.couleur} icone={m.icone} taille={taille} /> : null;
}

/** Le visuel d'un outil de la liste : logo du logiciel, tuile du connecteur maison, sinon tuile du type. */
export function VisuelOutil({
    categorie,
    integration,
    connecteur,
    initiales,
    taille = 32,
}: {
    categorie: string;
    /** `integration` du catalogue pour une action de logiciel. */
    integration?: string | null;
    connecteur?: string | null;
    initiales: React.ReactNode;
    taille?: number;
}) {
    if (categorie === "integration") {
        const logo = logoDe(integration);
        if (logo)
            return (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={logo} alt="" style={{ width: taille, height: taille }} className="inline-block shrink-0 rounded-lg border bg-white object-contain p-1" aria-hidden />
            );
        const maison = tuileConnecteur(connecteur, integration, taille);
        if (maison) return maison;
        return <>{initiales}</>;
    }
    const I = ICONES_TYPE[categorie];
    return I ? <TuileMaison couleur={COULEURS_TYPE[categorie] ?? "var(--outil-calcul)"} icone={I} taille={taille} /> : <>{initiales}</>;
}
