"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): « Manage labels ». Every label with the number of elements that carry it; rename
 * (the new name applies everywhere, refused if it exists) or delete (removed from all its elements, never an element).
 */
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    creerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPost,
    renommerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPut,
    supprimerUneEtiquetteApiV1BuilderBibliothequeEtiquettesDelete,
} from "@/client";
import type { VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
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
    const [nouvelle, setNouvelle] = useState("");

    const verifier = (reponse: { error?: unknown }, secours: string) => {
        if (reponse.error) {
            notifier.echec({ fr: "Étiquettes non enregistrées. Réessayez.", en: "Labels not saved. Try again." }, { erreur: reponse.error });
            return false;
        }
        apres();
        return true;
    };

    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={t({ en: "Manage labels", fr: "Gérer les étiquettes" })}
            info={t({
                en: "A label serves the whole library. Renaming applies everywhere. Deleting removes it from its elements; no element is ever deleted.",
                fr: "Une étiquette sert à toute la bibliothèque. Renommer s'applique partout. Supprimer la retire de ses éléments ; aucun élément n'est jamais supprimé.",
            })}
            valider={t({ en: "Close", fr: "Fermer" })}
            sections={[]}
            corps={
                <div className="space-y-3" data-testid="gestion-etiquettes">
                    <div className="flex gap-2">
                        <Input
                            value={nouvelle}
                            aria-label={t({ en: "New label", fr: "Nouvelle étiquette" })}
                            placeholder={t({ en: "New label", fr: "Nouvelle étiquette" })}
                            onChange={(e) => setNouvelle(e.target.value)}
                        />
                        <Button
                            variant="outline"
                            disabled={!nouvelle.trim()}
                            onClick={async () => {
                                const ok = verifier(
                                    await creerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPost({ body: { nom: nouvelle.trim() } }),
                                    t({ en: "The label was not created.", fr: "L'étiquette n'a pas été créée." }),
                                );
                                if (ok) setNouvelle("");
                            }}
                        >
                            {t({ en: "Create", fr: "Créer" })}
                        </Button>
                    </div>
                    {etiquettes.length === 0 && <p className="text-sm text-muted-foreground">{t({ en: "No label yet.", fr: "Aucune étiquette pour l'instant." })}</p>}
                    <ul className="divide-y">
                        {etiquettes.map((e) => (
                            <li key={e.nom} className="flex items-center gap-3 py-2 text-sm">
                                {renomme?.ancien === e.nom ? (
                                    <>
                                        <Input
                                            autoFocus
                                            value={renomme.nom}
                                            aria-label={t({ en: "New name", fr: "Nouveau nom" })}
                                            onChange={(x) => setRenomme({ ancien: e.nom, nom: x.target.value })}
                                        />
                                        <Button
                                            size="sm"
                                            disabled={!renomme.nom.trim()}
                                            onClick={async () => {
                                                const ok = verifier(
                                                    await renommerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPut({
                                                        query: { ancien: e.nom },
                                                        body: { nom: renomme.nom.trim() },
                                                    }),
                                                    t({ en: "The label was not renamed.", fr: "L'étiquette n'a pas été renommée." }),
                                                );
                                                if (ok) setRenomme(null);
                                            }}
                                        >
                                            {t({ en: "Rename", fr: "Renommer" })}
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <span className="font-medium">{e.nom}</span>
                                        <span className="text-muted-foreground">
                                            {t({ en: `${e.elements} element(s)`, fr: `${e.elements} élément(s)` })}
                                        </span>
                                        <span className="ml-auto flex gap-2">
                                            <Button variant="outline" size="sm" onClick={() => setRenomme({ ancien: e.nom, nom: e.nom })}>
                                                {t({ en: "Rename", fr: "Renommer" })}
                                            </Button>
                                            {aSupprimer === e.nom ? (
                                                <Button
                                                    variant="destructive"
                                                    size="sm"
                                                    onClick={async () => {
                                                        verifier(
                                                            await supprimerUneEtiquetteApiV1BuilderBibliothequeEtiquettesDelete({ query: { nom: e.nom } }),
                                                            t({ en: "The label was not deleted.", fr: "L'étiquette n'a pas été supprimée." }),
                                                        );
                                                        setASupprimer(null);
                                                    }}
                                                >
                                                    {t({ en: `Remove from ${e.elements} element(s)`, fr: `Retirer de ${e.elements} élément(s)` })}
                                                </Button>
                                            ) : (
                                                <Button variant="outline" size="sm" onClick={() => setASupprimer(e.nom)}>
                                                    {t({ en: "Delete", fr: "Supprimer" })}
                                                </Button>
                                            )}
                                        </span>
                                    </>
                                )}
                            </li>
                        ))}
                    </ul>
                </div>
            }
        />
    );
}
