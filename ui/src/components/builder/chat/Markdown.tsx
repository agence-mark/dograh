"use client";

/**
 * [.mark] builder partie 2, U5 : le rendu Markdown du texte du builder (titres, listes, gras, code). Écrit à la main, sans
 * `dangerouslySetInnerHTML` : tout passe par React, aucun HTML venu du modèle n'est jamais interprété.
 */
import type { ReactNode } from "react";

function enLigne(texte: string, cle: string): ReactNode[] {
    const morceaux: ReactNode[] = [];
    const motif = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let dernier = 0;
    let n = 0;
    for (const m of texte.matchAll(motif)) {
        const debut = m.index ?? 0;
        if (debut > dernier) morceaux.push(texte.slice(dernier, debut));
        const brut = m[0];
        morceaux.push(
            brut.startsWith("**") ? (
                <strong key={`${cle}-${n++}`}>{brut.slice(2, -2)}</strong>
            ) : (
                <code key={`${cle}-${n++}`} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
                    {brut.slice(1, -1)}
                </code>
            ),
        );
        dernier = debut + brut.length;
    }
    if (dernier < texte.length) morceaux.push(texte.slice(dernier));
    return morceaux;
}

export function Markdown({ texte }: { texte: string }) {
    const lignes = texte.split("\n");
    const blocs: ReactNode[] = [];
    let i = 0;
    let n = 0;
    while (i < lignes.length) {
        const ligne = lignes[i];
        if (ligne.trim().startsWith("```")) {
            const code: string[] = [];
            i++;
            while (i < lignes.length && !lignes[i].trim().startsWith("```")) code.push(lignes[i++]);
            i++;
            blocs.push(
                <pre key={n++} className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                    <code>{code.join("\n")}</code>
                </pre>,
            );
        } else if (/^\s*([-*]|\d+\.)\s+/.test(ligne)) {
            const ordonnee = /^\s*\d+\./.test(ligne);
            const items: string[] = [];
            while (i < lignes.length && /^\s*([-*]|\d+\.)\s+/.test(lignes[i])) items.push(lignes[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""));
            const Liste = ordonnee ? "ol" : "ul";
            blocs.push(
                <Liste key={n++} className={`ml-5 space-y-1 ${ordonnee ? "list-decimal" : "list-disc"}`}>
                    {items.map((item, k) => (
                        <li key={k}>{enLigne(item, `l${n}-${k}`)}</li>
                    ))}
                </Liste>,
            );
        } else if (/^#{1,4}\s+/.test(ligne)) {
            blocs.push(
                <p key={n++} className="font-semibold">
                    {enLigne(ligne.replace(/^#{1,4}\s+/, ""), `h${n}`)}
                </p>,
            );
            i++;
        } else if (ligne.trim() === "") {
            i++;
        } else {
            const para: string[] = [];
            while (i < lignes.length && lignes[i].trim() !== "" && !/^\s*([-*]|\d+\.)\s+/.test(lignes[i]) && !lignes[i].trim().startsWith("```") && !/^#{1,4}\s+/.test(lignes[i])) {
                para.push(lignes[i++]);
            }
            blocs.push(<p key={n++}>{enLigne(para.join("\n"), `p${n}`)}</p>);
        }
    }
    return <div className="space-y-2 text-sm leading-relaxed whitespace-pre-wrap">{blocs}</div>;
}
