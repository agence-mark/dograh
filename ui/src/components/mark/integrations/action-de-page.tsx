"use client";

/**
 * [.mark] K7 : l'action de l'onglet actif d'Intégrations (« Catalogue », « Ajouter un serveur MCP », « Nouvel identifiant ») vit dans la
 * rangée du titre de la page, à droite, comme la maquette : le bouton reste dans le code de son onglet, mais s'affiche dans un
 * emplacement que la page prête. Sans emplacement (l'onglet monté seul), il s'affiche à sa place.
 */
import { createContext, type ReactNode, useContext } from "react";
import { createPortal } from "react-dom";

export const ContexteAction = createContext<{ emplacement: HTMLElement | null; actif: string } | null>(null);

export function ActionDePage({ onglet, children }: { onglet: string; children: ReactNode }) {
    const ctx = useContext(ContexteAction);
    if (ctx === null) return <>{children}</>;
    if (!ctx.emplacement || ctx.actif !== onglet) return null;
    return createPortal(children, ctx.emplacement);
}
