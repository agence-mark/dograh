"use client";

/**
 * [.mark] La fenêtre « Étiquettes » d'un agent (U3, E30) : cocher les étiquettes existantes de l'organisation, en
 * taper une nouvelle (elle est créée pour toute l'organisation). Modale centrée, corps blanc, aucune carte dedans.
 * Enregistrer remplace les étiquettes de l'agent (`PUT /etiquettes/agents/{id}`) ; le serveur contrôle l'agent.
 */
import { useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { poserLesEtiquettesApiV1EtiquettesAgentsWorkflowIdPut } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { ajouter, basculer, NOM_MAX } from "./logique";
import { useEtiquettes } from "./useEtiquettes";

const T = {
    titre: { en: "Labels", fr: "Étiquettes" },
    nouvelle: { en: "New label", fr: "Nouvelle étiquette" },
    ajouter: { en: "Add", fr: "Ajouter" },
    aucune: { en: "No label yet. Type one above.", fr: "Aucune étiquette pour l'instant. Tapez-en une ci-dessus." },
    trop: { en: "A label has 40 characters at most.", fr: "Une étiquette fait 40 caractères au plus." },
    annuler: { en: "Cancel", fr: "Annuler" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    enCours: { en: "Saving...", fr: "Enregistrement..." },
    echec: { en: "The labels could not be saved.", fr: "Les étiquettes n'ont pas pu être enregistrées." },
} satisfies Record<string, Texte>;

export function FenetreEtiquettes({
    agentId,
    ouvert,
    onOuvertChange,
    onEnregistre,
}: {
    agentId: number;
    ouvert: boolean;
    onOuvertChange: (ouvert: boolean) => void;
    /** Appelée après une pose réussie (la liste relit ses étiquettes). */
    onEnregistre?: () => void;
}) {
    const { t } = useLangue();
    const { donnees } = useEtiquettes();
    const [selection, setSelection] = useState<string[]>([]);
    const [connues, setConnues] = useState<string[]>([]);
    const [saisie, setSaisie] = useState("");
    const [trop, setTrop] = useState(false);
    const [enCours, setEnCours] = useState(false);

    // À l'ouverture : les étiquettes de l'organisation, et celles que porte déjà cet agent.
    useEffect(() => {
        if (!ouvert || !donnees) return;
        setConnues(donnees.etiquettes.map((e) => e.nom));
        setSelection(donnees.par_agent[String(agentId)] ?? []);
        setSaisie("");
        setTrop(false);
    }, [ouvert, donnees, agentId]);

    const ajouterLaSaisie = () => {
        const resultat = ajouter(saisie, selection, connues);
        if (resultat === "vide") return;
        if (resultat === "trop-long") {
            setTrop(true);
            return;
        }
        setTrop(false);
        setSelection(resultat.selection);
        setConnues(resultat.connues);
        setSaisie("");
    };

    const enregistrer = async () => {
        setEnCours(true);
        try {
            const reponse = await poserLesEtiquettesApiV1EtiquettesAgentsWorkflowIdPut({
                path: { workflow_id: agentId },
                body: { etiquettes: selection },
            });
            if (reponse.error) {
                notifier.echec({ fr: "Étiquettes non enregistrées. Réessayez.", en: "Labels not saved. Try again." }, { erreur: reponse.error });
                return;
            }
            onEnregistre?.();
            onOuvertChange(false);
        } catch {
            notifier.echec({ fr: "Étiquettes non enregistrées. Réessayez.", en: "Labels not saved. Try again." });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Dialog open={ouvert} onOpenChange={onOuvertChange}>
            <DialogContent className="sm:max-w-md" data-fenetre="etiquettes">
                <DialogHeader>
                    <DialogTitle>{t(T.titre)}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 py-2">
                    <div className="flex items-center gap-2">
                        <Input
                            aria-label={t(T.nouvelle)}
                            placeholder={t(T.nouvelle)}
                            value={saisie}
                            maxLength={NOM_MAX + 10}
                            onChange={(e) => setSaisie(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                    e.preventDefault();
                                    ajouterLaSaisie();
                                }
                            }}
                        />
                        <Button type="button" variant="outline" className="cursor-pointer" disabled={!saisie.trim()} onClick={ajouterLaSaisie}>
                            {t(T.ajouter)}
                        </Button>
                    </div>
                    {trop && (
                        <p className="text-sm text-destructive" role="alert">
                            {t(T.trop)}
                        </p>
                    )}
                    {connues.length === 0 ? (
                        <p className="text-sm text-muted-foreground">{t(T.aucune)}</p>
                    ) : (
                        <ul className="max-h-64 divide-y overflow-auto" data-liste-etiquettes>
                            {connues.map((nom) => {
                                const coche = selection.some((s) => s.toLocaleLowerCase() === nom.toLocaleLowerCase());
                                return (
                                    <li key={nom}>
                                        <label className="flex cursor-pointer items-center gap-3 py-2.5 text-sm hover:font-medium">
                                            <Checkbox checked={coche} onCheckedChange={() => setSelection(basculer(selection, nom))} aria-label={nom} />
                                            {nom}
                                        </label>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" className="cursor-pointer" onClick={() => onOuvertChange(false)}>
                        {t(T.annuler)}
                    </Button>
                    <Button type="button" className="cursor-pointer" onClick={() => void enregistrer()} disabled={enCours}>
                        {enCours ? t(T.enCours) : t(T.enregistrer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
