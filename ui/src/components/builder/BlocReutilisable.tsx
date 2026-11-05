"use client";

/**
 * [.mark] Builder partie 3, lot 22 : la carte « Bloc réutilisable » de la fiche d'un élément de la bibliothèque (maquette :
 * `FicheElement` de `bibliotheque.tsx`). Seules les familles qui ÉCRIVENT des prompts en ont une (même liste que le serveur,
 * `etiquettes_prompt/table.FAMILLES_DE_BLOCS`). L'étiquette à déposer, la version que suivent les agents (la dernière en Recette),
 * et « Utilisé dans » avec le choix suivre ou rester par prompt.
 */
import type { Element as ElementBibliotheque } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { STYLE_FAMILLE } from "@/components/mark/variables/etiquettes-objets";
import { UtiliseDans } from "@/components/mark/variables/UtiliseDans";

export const FAMILLES_DE_BLOCS = ["prompt-general", "moules-etape", "personas", "conditions-passage"];

export function BlocReutilisable({ element }: { element: ElementBibliotheque }) {
    const { t } = useLangue();
    if (!FAMILLES_DE_BLOCS.includes(element.famille)) return null;
    const recettes = element.versions.filter((v) => v.statut === "recette").map((v) => v.numero);
    const derniere = recettes.length ? Math.max(...recettes) : null;
    return (
        <section className="space-y-2 rounded-xl border p-4" data-testid="bloc-reutilisable" aria-label={t({ en: "Reusable block", fr: "Bloc réutilisable" })}>
            <h3 className="flex items-center gap-1.5 text-sm font-semibold">
                {t({ en: "Reusable block", fr: "Bloc réutilisable" })}
                <Info>
                    {t({
                        en: "A piece of prompt from the library is dropped into any prompt as a label. Each agent follows the latest version (it gets every new Recipe) or stays on its own. Deleting or rejecting the block turns the labels that cite it red: publishing is blocked.",
                        fr: "Un morceau de prompt de la bibliothèque se dépose dans n'importe quel prompt sous forme d'étiquette. Chaque agent suit la dernière version (il reçoit chaque nouvelle Recette) ou reste sur la sienne. Supprimer ou rejeter le bloc rend rouges les étiquettes qui le citent : la publication est bloquée.",
                    })}
                </Info>
            </h3>
            <p className="flex flex-wrap items-center gap-2 text-sm">
                {t({ en: "In a prompt:", fr: "Dans un prompt :" })}
                <span className="rounded px-1.5 text-xs leading-5 text-white" style={{ background: STYLE_FAMILLE.bloc.couleur }}>
                    {t(STYLE_FAMILLE.bloc.prefixe)} › {element.titre}
                    {derniere ? ` · v${derniere}` : ""}
                </span>
                <code className="text-xs text-muted-foreground">{`{{bloc:${element.slug}}}`}</code>
            </p>
            {derniere === null && (
                <p className="text-xs text-muted-foreground" data-testid="bloc-sans-recette">
                    {t({ en: "No version in Recipe yet: an agent that follows it is blocked at publishing.", fr: "Aucune version en Recette : un agent qui le suit est bloqué à la publication." })}
                </p>
            )}
            <UtiliseDans cle={`bloc:${element.slug}`} versionRecette={derniere} />
        </section>
    );
}
