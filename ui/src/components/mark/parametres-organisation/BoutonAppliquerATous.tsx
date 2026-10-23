"use client";

/**
 * [.mark] « Apply to all establishments » (cloture-code, D152, Evan 22/10).
 *
 * Every establishment has its own complete values (F-8): a change shared by ten places would be typed
 * ten times. This button, put next to a setting of an establishment, copies THAT setting, as saved, into
 * all the other establishments of the organization, in one go on the server (all or none, journalled
 * establishment by establishment).
 *
 * A small centred window (never a side panel) names the establishments that will be written and asks to
 * confirm. The value copied is the one SAVED on the source: the server reads it, this screen sends only
 * which setting. So the button is off while something waits to be saved (`enAttente`), and hidden when
 * the organization has a single establishment (nobody to apply it to).
 */
import { useState } from "react";
import { toast } from "sonner";

import { appliquerATousLesEtablissementsApiV1OrganizationsEtablissementsIdentifiantAppliquerATousPost } from "@/client/sdk.gen";
import type { DemandeAppliquerATous, ResultatAppliquerATous } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

export type ReglageAppliquable = DemandeAppliquerATous["reglage"];
export interface LieuAppliquable {
    id: string;
    nom: string;
}

export const APPLIQUER_A_TOUS: Texte = { en: "Apply to all establishments", fr: "Appliquer à tous les établissements" };

export function BoutonAppliquerATous({
    source,
    etablissements,
    reglage,
    cle,
    libelle,
    valeur,
    enAttente = false,
    onApplique,
}: {
    /** The establishment whose saved value is copied. */
    source: LieuAppliquable;
    /** All the establishments of the organization, as saved (the source among them). */
    etablissements: LieuAppliquable[];
    reglage: ReglageAppliquable;
    cle: string;
    /** The setting's name, said in the window. */
    libelle: Texte;
    /** The value, as text, shown in the window (empty: « nothing »). Optional. */
    valeur?: string | null;
    /** Something waits to be saved on this screen: the server copies the saved value, so save first. */
    enAttente?: boolean;
    /** Called once the server answered: the caller reads the screen again. */
    onApplique: (resultat: ResultatAppliquerATous) => void | Promise<void>;
}) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    const autres = etablissements.filter((e) => e.id !== source.id);
    // Nobody to apply it to: nothing is drawn.
    if (autres.length === 0) return null;

    const appliquer = async () => {
        setEnCours(true);
        setErreur(null);
        const reponse = await appliquerATousLesEtablissementsApiV1OrganizationsEtablissementsIdentifiantAppliquerATousPost({
            path: { identifiant: source.id },
            body: { reglage, cle },
        });
        setEnCours(false);
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "Not applied"));
            return;
        }
        setOuverte(false);
        const n = reponse.data.etablissements?.length ?? 0;
        toast.success(
            t({
                en: `Applied to ${n} other establishment(s).`,
                fr: `Appliqué aux ${n} autres établissements.`,
            }),
        );
        await onApplique(reponse.data);
    };

    return (
        <>
            <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={enAttente}
                title={enAttente ? t({ en: "Save the changes first: the saved value is the one copied.", fr: "Enregistrez d'abord les changements : c'est la valeur enregistrée qui est recopiée." }) : undefined}
                onClick={() => {
                    setErreur(null);
                    setOuverte(true);
                }}
                data-testid={`appliquer-a-tous-${reglage}-${cle}`}
            >
                {t(APPLIQUER_A_TOUS)}
            </Button>
            <Dialog open={ouverte} onOpenChange={(o) => (o || enCours ? null : setOuverte(false))}>
                <DialogContent className="sm:max-w-md" data-testid="modale-appliquer-a-tous">
                    <DialogHeader>
                        <DialogTitle>{t(APPLIQUER_A_TOUS)}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: `« ${t(libelle)} » of « ${source.nom} » is copied, as saved, into the establishments below. What they have for it today is replaced.`,
                                fr: `« ${t(libelle)} » de « ${source.nom} » est recopié, tel qu'enregistré, dans les établissements ci-dessous. Ce qu'ils ont aujourd'hui pour ce réglage est remplacé.`,
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        {valeur !== undefined && (
                            <p className="whitespace-pre-line rounded border border-border bg-muted/40 p-2 text-sm" data-testid="valeur-appliquee">
                                {valeur && valeur.trim() ? valeur : t({ en: "Empty: nothing for this setting.", fr: "Vide : rien pour ce réglage." })}
                            </p>
                        )}
                        <div>
                            <p className="mb-1 text-sm font-medium">{t({ en: "Establishments written", fr: "Établissements modifiés" })}</p>
                            <ul className="list-disc space-y-0.5 pl-5 text-sm" data-testid="etablissements-touches">
                                {autres.map((e) => (
                                    <li key={e.id}>{e.nom}</li>
                                ))}
                            </ul>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {t({
                                en: "All or none: if one of them cannot be written, none is changed. Each change is journalled.",
                                fr: "Tout ou rien : si l'un d'eux ne peut pas être écrit, aucun n'est modifié. Chaque changement est journalisé.",
                            })}
                        </p>
                        {erreur && (
                            <p className="text-sm text-destructive" role="alert" data-testid="erreur-appliquer-a-tous">
                                {erreur}
                            </p>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setOuverte(false)} disabled={enCours}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                        <Button onClick={() => void appliquer()} disabled={enCours} data-testid="confirmer-appliquer-a-tous">
                            {t({ en: `Apply to ${autres.length}`, fr: `Appliquer aux ${autres.length}` })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
