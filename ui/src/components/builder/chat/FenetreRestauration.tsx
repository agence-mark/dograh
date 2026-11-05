"use client";

/**
 * [.mark] builder partie 2, lot M (pièce 4 de Cognigy) : la fenêtre « Revenir à cette version ». Avant d'écrire quoi que ce soit, elle
 * montre ce qui sera perdu et ce qui sera retrouvé (lecture seule, `GET .../versions/{n}/apercu`), puis demande la confirmation.
 * Conçue sans maquette : composants de la maquette (`Section`, `EtatVide`, `Info`), fenêtre centrée à corps blanc, jetons seulement.
 *
 * Partie 3, sous-lot 7 (SE-15) : « Revenir avant » restaure TOUT. La fenêtre de la maquette (`FenetreRevenir`, `branches-versions.tsx`) :
 * une case par famille (schéma, phrases, réglages, vocabulaire, objets), toutes cochées au départ ; une famille que la version n'a pas
 * gardée est grisée et le dit ; le vocabulaire et les objets sont partagés par l'organisation et le disent. Les noms de ce qui change
 * sont montrés, jamais une valeur. La confirmation envoie les familles cochées.
 */
import { useEffect, useState } from "react";

import { apercuAvantDeRevenirApiV1BuilderAgentsWorkflowIdVersionsNumeroApercuGet } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
    familles: { en: "What to restore", fr: "Ce qui revient" },
    aucune: { en: "Tick at least one family.", fr: "Cochez au moins une famille." },
    nonGardee: { en: "not kept in this version", fr: "non gardé dans cette version" },
    inchangee: { en: "no change", fr: "aucun changement" },
    partagee: { en: "shared by the whole organization", fr: "partagé par toute l'organisation" },
    objetsSeulement: { en: "rewrites the objects that existed; never deletes one added since", fr: "réécrit les objets qui existaient ; n'en supprime jamais un ajouté depuis" },
    ajoutes: { en: "added since, kept:", fr: "ajoutés depuis, gardés :" },
} satisfies Record<string, Texte>;

const FAMILLES: Record<string, Texte> = {
    schema: { en: "Flow (steps and links)", fr: "Schéma (étapes et liaisons)" },
    phrases: { en: "Code phrases", fr: "Phrases du code" },
    reglages: { en: "Agent settings", fr: "Réglages de l'agent" },
    vocabulaire: { en: "Trade vocabulary", fr: "Vocabulaire du métier" },
    objets: { en: "Agent objects", fr: "Objets de l'agent" },
};

// Le serveur envoie un identifiant neutre pour le genre de chaque ligne ; l'écran le dit dans la langue choisie.
const GENRES: Record<string, Texte> = {
    node_added: { en: "node added", fr: "noeud ajouté" },
    node_changed: { en: "node changed", fr: "noeud modifié" },
    node_removed: { en: "node removed", fr: "noeud retiré" },
    link_added: { en: "link added", fr: "liaison ajoutée" },
    link_changed: { en: "link changed", fr: "liaison modifiée" },
    link_removed: { en: "link removed", fr: "liaison retirée" },
};

type Ligne = { genre: string; cible: string; nom: string; champs?: string[] };
export type FamilleApercue = { famille: string; disponible: boolean; partagee: boolean; change: boolean | null; details: string[]; ajoutes_depuis?: string[] };
type Apercu = {
    numero: number;
    cause: string | null;
    sera_perdu: Ligne[];
    sera_retrouve: Ligne[];
    total_perdu: number;
    total_retrouve: number;
    inchanges: number;
    familles?: FamilleApercue[];
};
const SCHEMA_SEUL: FamilleApercue[] = [{ famille: "schema", disponible: true, partagee: false, change: null, details: [] }];

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
    confirmer: (familles: string[]) => Promise<void>;
    fermer: () => void;
}) {
    const { t } = useLangue();
    const [apercu, setApercu] = useState<Apercu | null>(null);
    const [cochees, setCochees] = useState<string[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        let vivant = true;
        void apercuAvantDeRevenirApiV1BuilderAgentsWorkflowIdVersionsNumeroApercuGet({ path: { workflow_id: workflowId, numero } }).then((r) => {
            if (!vivant) return;
            if (r.error || !r.data) return setErreur(true);
            const lu = r.data as Apercu;
            setApercu(lu);
            // Toutes les familles que la version a gardées sont cochées au départ ; un serveur qui n'en dit rien ne rend que le schéma.
            setCochees((lu.familles ?? SCHEMA_SEUL).filter((f) => f.disponible).map((f) => f.famille));
        });
        return () => {
            vivant = false;
        };
    }, [workflowId, numero]);

    const rien = apercu !== null && apercu.total_perdu === 0 && apercu.total_retrouve === 0 && !(apercu.familles ?? []).some((f) => f.change === true);
    const familles = apercu?.familles ?? (apercu ? SCHEMA_SEUL : []);
    const bascule = (famille: string, v: boolean) => setCochees((c) => (v ? [...(c ?? []), famille] : (c ?? []).filter((x) => x !== famille)));
    return (
        <Dialog centree open onOpenChange={(ouvert) => !ouvert && fermer()}>
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
                            <section className="space-y-2" data-testid="familles-a-restaurer">
                                <h4 className="text-sm font-semibold">{t(T.familles)}</h4>
                                <ul className="space-y-2 text-sm">
                                    {familles.map((f) => (
                                        <li key={f.famille}>
                                            <label className={`flex items-start gap-2 ${f.disponible ? "cursor-pointer" : "cursor-default text-muted-foreground"}`}>
                                                <Checkbox
                                                    className="mt-0.5"
                                                    disabled={!f.disponible}
                                                    checked={f.disponible && (cochees ?? []).includes(f.famille)}
                                                    onCheckedChange={(v) => bascule(f.famille, v === true)}
                                                    aria-label={t(FAMILLES[f.famille] ?? { en: f.famille, fr: f.famille })}
                                                />
                                                <span className="flex-1">
                                                    {t(FAMILLES[f.famille] ?? { en: f.famille, fr: f.famille })}
                                                    <span className="block text-xs text-muted-foreground">
                                                        {!f.disponible
                                                            ? t(T.nonGardee)
                                                            : [
                                                                  f.change === false ? t(T.inchangee) : f.details.length > 0 ? f.details.join(", ") : "",
                                                                  f.partagee ? t(T.partagee) : "",
                                                                  f.famille === "objets" ? t(T.objetsSeulement) : "",
                                                              ]
                                                                  .filter(Boolean)
                                                                  .join(" · ")}
                                                        {f.ajoutes_depuis && f.ajoutes_depuis.length > 0 ? ` · ${t(T.ajoutes)} ${f.ajoutes_depuis.join(", ")}` : ""}
                                                    </span>
                                                </span>
                                            </label>
                                        </li>
                                    ))}
                                </ul>
                            </section>
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
                        disabled={!apercu || enCours || (cochees ?? []).length === 0}
                        title={apercu && (cochees ?? []).length === 0 ? t(T.aucune) : undefined}
                        onClick={() => {
                            setEnCours(true);
                            void confirmer(cochees ?? []).finally(() => setEnCours(false));
                        }}
                    >
                        {enCours ? t(T.enCours) : t(T.confirmer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
