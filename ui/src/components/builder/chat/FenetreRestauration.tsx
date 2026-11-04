"use client";

/**
 * [.mark] builder partie 2, lot M (pièce 4 de Cognigy) : la fenêtre « Revenir à cette version ». Avant d'écrire quoi que ce soit, elle
 * montre ce qui sera perdu et ce qui sera retrouvé (lecture seule, `GET .../versions/{n}/apercu`), puis demande la confirmation.
 * Conçue sans maquette : composants de la maquette (`Section`, `EtatVide`, `Info`), fenêtre centrée à corps blanc, jetons seulement.
 */
import { useEffect, useState } from "react";

import { apercuAvantDeRevenirApiV1BuilderAgentsWorkflowIdVersionsNumeroApercuGet } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const T = {
    titre: { en: "Go back to this version", fr: "Revenir à cette version" },
    info: {
        en: "Nothing is written until you confirm. The draft becomes the graph this version started from; going back is itself saved and can be undone.",
        fr: "Rien n'est écrit tant que vous ne confirmez pas. Le brouillon redevient le graphe dont cette version est partie ; ce retour est lui-même enregistré et peut être défait.",
    },
    perdu: { en: "Will be lost", fr: "Sera perdu" },
    retrouve: { en: "Will come back", fr: "Sera retrouvé" },
    rien: { en: "Nothing: the draft already is this version.", fr: "Rien : le brouillon est déjà cette version." },
    plus: { en: "and others not shown", fr: "et d'autres non montrés" },
    annuler: { en: "Cancel", fr: "Annuler" },
    confirmer: { en: "Confirm and go back", fr: "Confirmer le retour" },
    enCours: { en: "Going back...", fr: "Retour en cours..." },
    champs: { en: "field(s)", fr: "champ(s)" },
} satisfies Record<string, Texte>;

// Le serveur envoie le genre de chaque ligne en français (clé stable) ; l'écran le dit dans la langue choisie.
const GENRES: Record<string, Texte> = {
    "noeud ajouté": { en: "node added", fr: "noeud ajouté" },
    "noeud modifié": { en: "node changed", fr: "noeud modifié" },
    "noeud retiré": { en: "node removed", fr: "noeud retiré" },
    "liaison ajoutée": { en: "link added", fr: "liaison ajoutée" },
    "liaison modifiée": { en: "link changed", fr: "liaison modifiée" },
    "liaison retirée": { en: "link removed", fr: "liaison retirée" },
};

type Ligne = { genre: string; cible: string; nom: string; champs?: string[] };
type Apercu = { numero: number; cause: string | null; sera_perdu: Ligne[]; sera_retrouve: Ligne[]; total_perdu: number; total_retrouve: number; inchanges: number };

function Liste({ titre, lignes, total, plus, champs }: { titre: string; lignes: Ligne[]; total: number; plus: string; champs: string }) {
    const { t } = useLangue();
    if (lignes.length === 0) return null;
    return (
        <section className="space-y-1" data-liste={titre}>
            <h4 className="text-sm font-semibold">
                {titre} ({total})
            </h4>
            <ul className="space-y-1 text-sm">
                {lignes.map((l) => (
                    <li key={`${l.genre}-${l.cible}`} className="flex flex-wrap gap-x-2">
                        <span className="text-muted-foreground">{GENRES[l.genre] ? t(GENRES[l.genre]) : l.genre}</span>
                        <span>{l.nom}</span>
                        {l.champs && l.champs.length > 0 && (
                            <span className="text-xs text-muted-foreground">
                                ({l.champs.length} {champs} : {l.champs.join(", ")})
                            </span>
                        )}
                    </li>
                ))}
            </ul>
            {total > lignes.length && <p className="text-xs text-muted-foreground">{plus}</p>}
        </section>
    );
}

export function FenetreRestauration({
    workflowId,
    numero,
    confirmer,
    fermer,
}: {
    workflowId: number;
    numero: number;
    confirmer: () => Promise<void>;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const [apercu, setApercu] = useState<Apercu | null>(null);
    const [erreur, setErreur] = useState(false);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        let vivant = true;
        void apercuAvantDeRevenirApiV1BuilderAgentsWorkflowIdVersionsNumeroApercuGet({ path: { workflow_id: workflowId, numero } }).then((r) => {
            if (!vivant) return;
            if (r.error || !r.data) return setErreur(true);
            setApercu(r.data as Apercu);
        });
        return () => {
            vivant = false;
        };
    }, [workflowId, numero]);

    const rien = apercu !== null && apercu.total_perdu === 0 && apercu.total_retrouve === 0;
    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent className="sm:max-w-2xl" data-modale="revenir-a-une-version">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {t(T.titre)} #{numero}
                        <Info>{t(T.info)}</Info>
                    </DialogTitle>
                </DialogHeader>
                <div className="max-h-[60vh] space-y-4 overflow-auto">
                    {erreur && <EtatVide cas="erreur" />}
                    {!erreur && !apercu && <EtatVide cas="chargement" />}
                    {apercu && (
                        <>
                            <Liste titre={t(T.perdu)} lignes={apercu.sera_perdu} total={apercu.total_perdu} plus={t(T.plus)} champs={t(T.champs)} />
                            <Liste titre={t(T.retrouve)} lignes={apercu.sera_retrouve} total={apercu.total_retrouve} plus={t(T.plus)} champs={t(T.champs)} />
                            {rien && <p className="text-sm text-muted-foreground">{t(T.rien)}</p>}
                        </>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={fermer}>
                        {t(T.annuler)}
                    </Button>
                    <Button
                        disabled={!apercu || enCours}
                        onClick={() => {
                            setEnCours(true);
                            void confirmer().finally(() => setEnCours(false));
                        }}
                    >
                        {enCours ? t(T.enCours) : t(T.confirmer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
