"use client";

/**
 * [.mark] « Create by copy » (chantier agents-specialises, lot 11 = lot 4 of the fiche plan, F2/M2).
 *
 * A small centred window (never a side panel): which fiche to copy, the name and the identifier of the
 * new one. The server copies everything that describes the place and, with a client database, the
 * appointment settings and types; NEVER the numbers (a copied number would send calls to the wrong
 * place) nor the immediate closing. The copy is written at once, by the server, with the same controls
 * as a save: this window hands back what the server made so the list can be read again.
 */
import { useEffect, useState } from "react";

import { copierEtablissementApiV1OrganizationsEtablissementsCopierPost } from "@/client/sdk.gen";
import type { Etablissement, ResultatCopieEtablissement } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";
import { identifiantPour } from "./ModaleEtablissements";

export function ModaleCopieFiche({
    ouverte,
    fiches,
    sourceInitiale,
    onFermer,
}: {
    ouverte: boolean;
    fiches: Etablissement[];
    sourceInitiale: string;
    /** The server's answer when the copy was made, null when cancelled. */
    onFermer: (resultat: ResultatCopieEtablissement | null) => void;
}) {
    const { t } = useLangue();
    const [source, setSource] = useState(sourceInitiale);
    const [nom, setNom] = useState("");
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        setSource(sourceInitiale);
        setNom("");
        setErreur(null);
    }, [ouverte, sourceInitiale]);

    const identifiant = identifiantPour(nom, fiches.map((f) => f.id));
    const valide = nom.trim().length > 0 && source !== "";

    const copier = async () => {
        setEnCours(true);
        setErreur(null);
        const reponse = await copierEtablissementApiV1OrganizationsEtablissementsCopierPost({
            body: { source, id: identifiant, nom: nom.trim() },
        });
        setEnCours(false);
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "Copy failed"));
            return;
        }
        onFermer(reponse.data);
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(null))}>
            <DialogContent className="sm:max-w-lg" data-testid="modale-copie-fiche">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Create an establishment by copy", fr: "Créer un établissement par copie" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Everything that describes the place is copied: address, hours, announcements, sentences, terms, appointment settings and types. Never the numbers, nor the immediate closing: fill them on the new fiche.",
                            fr: "Tout ce qui décrit le lieu est copié : adresse, horaires, annonces, phrases, termes, réglages et types de rendez-vous. Jamais les numéros, ni la fermeture immédiate : à renseigner sur la nouvelle fiche.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="space-y-1">
                        <label htmlFor="copie-source" className="text-sm font-medium">
                            {t({ en: "Fiche to copy", fr: "Fiche à copier" })}
                        </label>
                        <select
                            id="copie-source"
                            className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                            value={source}
                            onChange={(e) => setSource(e.target.value)}
                        >
                            {fiches.map((f) => (
                                <option key={f.id} value={f.id}>
                                    {f.nom}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="space-y-1">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <label htmlFor="copie-nom" className="text-sm font-medium">
                                {t({ en: "Name of the new fiche", fr: "Nom de la nouvelle fiche" })}
                            </label>
                            <code className="text-xs text-muted-foreground" data-testid="copie-identifiant">
                                {nom.trim() ? identifiant : ""}
                            </code>
                        </div>
                        <Input id="copie-nom" value={nom} maxLength={100} onChange={(e) => setNom(e.target.value)} />
                        <p className="text-xs text-muted-foreground">
                            {t({
                                en: "The identifier follows the name and never changes once the fiche exists.",
                                fr: "L'identifiant suit le nom et ne change plus une fois la fiche créée.",
                            })}
                        </p>
                    </div>
                    {erreur && (
                        <p className="text-sm text-destructive" role="alert" data-testid="erreur-copie-fiche">
                            {erreur}
                        </p>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(null)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void copier()} disabled={enCours || !valide} data-testid="copier-la-fiche">
                        {t({ en: "Create the copy", fr: "Créer la copie" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
