"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49) puis K5 (fidélité à la maquette) : « Étiquettes de la bibliothèque ». Chaque
 * étiquette avec le nombre d'éléments qui la portent ; le crayon la renomme (le nouveau nom vaut partout, refusé s'il existe),
 * la corbeille la supprime après une confirmation qui dit combien d'éléments la perdent (jamais un élément). La création
 * se fait dans le menu « Étiquettes » de la page, comme la maquette.
 */
import { Pencil, Tag, Trash2 } from "lucide-react";
import { useState } from "react";

import { renommerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPut, supprimerUneEtiquetteApiV1BuilderBibliothequeEtiquettesDelete } from "@/client";
import type { VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { FenetreLarge } from "@/components/mark/studio/fenetre-large";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
    etiquettes: VueEtiquette[];
    fermer: () => void;
    /** The list changed on the server: the page reads it again. */
    apres: () => void;
}

export function GestionDesEtiquettes({ etiquettes, fermer, apres }: Props) {
    const { t } = useLangue();
    const [renomme, setRenomme] = useState<{ ancien: string; nom: string } | null>(null);
    const [aSupprimer, setASupprimer] = useState<string | null>(null);

    const verifier = (reponse: { error?: unknown }, echec: { fr: string; en: string }) => {
        if (reponse.error) {
            notifier.echec(echec, { erreur: reponse.error });
            return false;
        }
        apres();
        return true;
    };

    const valider = async () => {
        if (!renomme) return;
        const nom = renomme.nom.trim();
        if (!nom || nom === renomme.ancien) {
            setRenomme(null);
            return;
        }
        const ok = verifier(
            await renommerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPut({ query: { ancien: renomme.ancien }, body: { nom } }),
            { fr: "Étiquette non renommée. Réessayez.", en: "Label not renamed. Try again." },
        );
        if (ok) setRenomme(null);
    };

    return (
        <FenetreLarge
            liste
            large={false}
            testid="gestion-etiquettes"
            fermer={fermer}
            titre={t({ en: "Labels of the library", fr: "Étiquettes de la bibliothèque" })}
            sous={t({ en: `${etiquettes.length} label(s)`, fr: `${etiquettes.length} étiquettes` })}
            pied={
                <>
                    <span className="flex-1" />
                    <Button onClick={fermer}>{t({ en: "Close", fr: "Fermer" })}</Button>
                </>
            }
        >
            <div className="divide-y">
                {etiquettes.map((e) => (
                    <div key={e.nom} className="group flex items-center gap-3 py-3 text-sm">
                        <Tag className="size-3.5 text-muted-foreground" />
                        {renomme?.ancien === e.nom ? (
                            <Input
                                autoFocus
                                value={renomme.nom}
                                aria-label={t({ en: "New name", fr: "Nouveau nom" })}
                                onChange={(x) => setRenomme({ ancien: e.nom, nom: x.target.value })}
                                onKeyDown={(x) => {
                                    if (x.key === "Enter") void valider();
                                    if (x.key === "Escape") setRenomme(null);
                                }}
                                className="h-8 flex-1"
                            />
                        ) : (
                            <span className="flex-1">{e.nom}</span>
                        )}
                        {aSupprimer === e.nom ? (
                            <>
                                <span className="text-xs text-destructive">
                                    {e.elements
                                        ? t({ en: `Removed from ${e.elements} element(s)`, fr: `Retirée de ${e.elements} élément(s)` })
                                        : t({ en: "No element", fr: "Aucun élément" })}
                                </span>
                                <Button variant="outline" size="sm" onClick={() => setASupprimer(null)}>
                                    {t({ en: "No", fr: "Non" })}
                                </Button>
                                <Button
                                    size="sm"
                                    className="bg-(--pastille-urgente) text-white hover:bg-(--pastille-urgente)/90"
                                    onClick={async () => {
                                        // suppression-confirmee : « Non / Supprimer » en place, avec le nombre d'éléments touchés.
                                        verifier(await supprimerUneEtiquetteApiV1BuilderBibliothequeEtiquettesDelete({ query: { nom: e.nom } }), {
                                            fr: "Étiquette non supprimée. Réessayez.",
                                            en: "Label not deleted. Try again.",
                                        });
                                        setASupprimer(null);
                                    }}
                                >
                                    {t({ en: "Delete", fr: "Supprimer" })}
                                </Button>
                            </>
                        ) : (
                            <>
                                <span className="text-xs text-muted-foreground tabular-nums" data-testid={`nb-${e.nom}`}>
                                    {e.elements || "–"}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => setRenomme({ ancien: e.nom, nom: e.nom })}
                                    className="cursor-pointer rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100"
                                    aria-label={t({ en: `Rename ${e.nom}`, fr: `Renommer ${e.nom}` })}
                                >
                                    <Pencil className="size-3.5" />
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setASupprimer(e.nom)}
                                    className="cursor-pointer rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-muted hover:text-destructive focus-visible:opacity-100"
                                    aria-label={t({ en: `Delete ${e.nom}`, fr: `Supprimer ${e.nom}` })}
                                >
                                    <Trash2 className="size-3.5" />
                                </button>
                            </>
                        )}
                    </div>
                ))}
                {etiquettes.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">{t({ en: "No label yet.", fr: "Aucune étiquette pour l'instant." })}</p>}
            </div>
        </FenetreLarge>
    );
}
