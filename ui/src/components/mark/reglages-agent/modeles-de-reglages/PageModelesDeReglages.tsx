"use client";

/**
 * [.mark] builder partie 2, D1 (U4, E45 B) : Bibliothèque › Modèles de réglages.
 *
 * Un tableau au standard (modèle, statut, réglages, origine, créé), une fiche par modèle (renommer dans le titre, les
 * réglages par section, Exporter, Supprimer avec confirmation) et « Importer un fichier ». Les modèles sont des éléments de
 * la bibliothèque (famille `modeles-reglages`) : cette page lit et écrit par les routes `/organizations/modeles-de-reglages`.
 * L'application à un agent se fait depuis l'agent (menu « Modèle ▾ » de son onglet Réglages), où l'on choisit les sections.
 */
import { FileUp, LayoutTemplate } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    exporterUnModeleApiV1OrganizationsModelesDeReglagesModeleIdExportGet,
    importerUnModeleApiV1OrganizationsModelesDeReglagesImportPost,
    listerLesModelesApiV1OrganizationsModelesDeReglagesGet,
    renommerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdPatch,
    supprimerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdDelete,
} from "@/client/sdk.gen";
import type { FichierDeModele, ListeDesModeles, ResumeDuModele } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { useLangue } from "../../langue/langue";
import { EtatVide } from "../../studio/etat-vide";
import { Info } from "../../studio/marques";
import { Paginee } from "../../studio/pagination";
import { Cellule, Ligne, Tableau } from "../../studio/tableau";
import { TitrePage } from "../../studio/titre-page";
import { MarqueStatut } from "./marque-statut";
import { TITRES_DES_SECTIONS } from "./ModaleModeles";

const nomDeFichier = (nom: string) => `modele-${nom.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "reglages"}.json`;

const telecharger = (fichier: FichierDeModele, nom: string) => {
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(new Blob([JSON.stringify(fichier, null, 2)], { type: "application/json" }));
    lien.download = nomDeFichier(nom);
    lien.click();
    URL.revokeObjectURL(lien.href);
};

export const PageModelesDeReglages = () => {
    const { t, langue } = useLangue();
    const [liste, setListe] = useState<ListeDesModeles | null>(null);
    const [echec, setEchec] = useState(false);
    const [ouvert, setOuvert] = useState<ResumeDuModele | null>(null);
    const fichierImport = useRef<HTMLInputElement>(null);

    const charger = useCallback(async () => {
        try {
            const reponse = await listerLesModelesApiV1OrganizationsModelesDeReglagesGet();
            if (reponse.error || !reponse.data) {
                setEchec(true);
                return;
            }
            setEchec(false);
            setListe(reponse.data);
        } catch {
            setEchec(true);
        }
    }, []);

    useEffect(() => {
        void charger();
    }, [charger]);

    const importer = async (fichier: File | undefined) => {
        if (!fichier) return;
        let corps: unknown;
        try {
            corps = JSON.parse(await fichier.text());
        } catch {
            notifier.echec({ fr: "Ce fichier n'est pas un modèle de réglages.", en: "This file is not a settings template." });
            return;
        }
        // Le fichier part tel quel : le serveur nomme le réglage qu'il refuse.
        const reponse = await importerUnModeleApiV1OrganizationsModelesDeReglagesImportPost({ body: corps as never });
        if (fichierImport.current) fichierImport.current.value = "";
        if (reponse.error) {
            notifier.echec({ fr: "Modèle non importé. Réessayez.", en: "Template not imported. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Modèle importé.", en: "Template imported." });
        await charger();
    };

    const date = (iso: string) => new Date(iso).toLocaleDateString(langue === "fr" ? "fr-FR" : "en-GB");
    const origine = (m: ResumeDuModele) =>
        m.origine?.agent_nom
            ? `${m.origine.agent_nom}${m.origine.version_number ? ` · v${m.origine.version_number}` : ""}`
            : t({ en: "Imported file", fr: "Fichier importé" });

    return (
        <div className="mx-auto max-w-5xl space-y-6 px-6 py-6" data-page="modeles-de-reglages">
            <TitrePage
                titre={t({ en: "Settings templates", fr: "Modèles de réglages" })}
                info={t({
                    en: "A template holds behaviour settings only: never prompts, the flow, variables, tools, numbers, the client's own data, nor any API key. Applying one (an agent's Settings tab, « Template » menu) is a copy on its draft: changing or deleting it later changes no agent already set.",
                    fr: "Un modèle ne porte que des réglages de comportement : jamais les prompts, le parcours, les variables, les outils, les numéros, les données propres au client, ni aucune clé d'accès. L'appliquer (onglet Réglages d'un agent, menu « Modèle ») est une copie sur son brouillon : le modifier ou le supprimer ensuite ne change aucun agent déjà réglé.",
                })}
                action={
                    <>
                        <input
                            ref={fichierImport}
                            type="file"
                            accept="application/json,.json"
                            className="hidden"
                            data-import-modele
                            onChange={(e) => void importer(e.target.files?.[0])}
                        />
                        <Button type="button" variant="outline" size="sm" onClick={() => fichierImport.current?.click()}>
                            <FileUp className="mr-1.5 h-4 w-4" />
                            {t({ en: "Import a file", fr: "Importer un fichier" })}
                        </Button>
                    </>
                }
            />

            {echec && <EtatVide cas="erreur" reessayer={() => void charger()} />}
            {!echec && !liste && <EtatVide cas="chargement" />}
            {liste && liste.modeles.length === 0 && (
                <EtatVide cas="premier" icone={LayoutTemplate} titre={t({ en: "No template yet", fr: "Aucun modèle pour l'instant" })} />
            )}
            {liste && liste.modeles.length > 0 && (
                <Paginee liste={liste.modeles}>
                    {(tranche) => (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Template", fr: "Modèle" }) },
                                { titre: t({ en: "Status", fr: "Statut" }) },
                                { titre: t({ en: "Settings", fr: "Réglages" }), droite: true },
                                { titre: t({ en: "Frozen from", fr: "Figé depuis" }) },
                                { titre: t({ en: "Created", fr: "Créé" }) },
                            ]}
                        >
                            {tranche.map((m) => (
                                <Ligne key={m.id} onClick={() => setOuvert(m)}>
                                    <Cellule principale sous={m.sections.map((s) => t(TITRES_DES_SECTIONS[s] ?? { en: s, fr: s })).join(", ")}>
                                        <span data-modele={m.id}>{m.nom}</span>
                                    </Cellule>
                                    <Cellule>
                                        <MarqueStatut statut={m.statut ?? "candidat"} />
                                    </Cellule>
                                    <Cellule droite>{m.nombre_de_reglages}</Cellule>
                                    <Cellule>{origine(m)}</Cellule>
                                    <Cellule>{date(m.cree_le)}</Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    )}
                </Paginee>
            )}
            {ouvert && (
                <FicheDuModele
                    modele={ouvert}
                    onFermer={() => setOuvert(null)}
                    onChange={async () => {
                        await charger();
                    }}
                    onSupprime={async () => {
                        setOuvert(null);
                        await charger();
                    }}
                />
            )}
        </div>
    );
};

const FicheDuModele = ({
    modele,
    onFermer,
    onChange,
    onSupprime,
}: {
    modele: ResumeDuModele;
    onFermer: () => void;
    onChange: () => Promise<void>;
    onSupprime: () => Promise<void>;
}) => {
    const { t } = useLangue();
    const [fichier, setFichier] = useState<FichierDeModele | null>(null);
    const [nom, setNom] = useState(modele.nom);
    const [confirmer, setConfirmer] = useState(false);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        let annule = false;
        (async () => {
            try {
                const reponse = await exporterUnModeleApiV1OrganizationsModelesDeReglagesModeleIdExportGet({ path: { modele_id: modele.id } });
                if (!annule && reponse.data) setFichier(reponse.data);
            } catch {
                // La fiche s'ouvre sans le détail : jamais un détail inventé.
            }
        })();
        return () => {
            annule = true;
        };
    }, [modele.id]);

    const renommer = async () => {
        setEnCours(true);
        const reponse = await renommerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdPatch({ path: { modele_id: modele.id }, body: { nom } });
        setEnCours(false);
        if (reponse.error) {
            notifier.echec({ fr: "Modèle non modifié. Réessayez.", en: "Template not changed. Try again." }, { erreur: reponse.error });
            return;
        }
        await onChange();
    };

    const supprimer = async () => {
        setEnCours(true);
        const reponse = await supprimerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdDelete({ path: { modele_id: modele.id } });
        setEnCours(false);
        if (reponse.error) {
            notifier.echec({ fr: "Modèle non supprimé. Réessayez.", en: "Template not deleted. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Modèle supprimé. Les agents déjà réglés gardent leurs réglages.", en: "Template deleted. Agents already set keep their settings." });
        await onSupprime();
    };

    // Les réglages par section : la section de chaque clé, lue de la liste des sections du modèle (les clés d'une section
    // sont celles que le serveur a rangées ; ici on montre le nombre et les noms techniques posés).
    const cles = Object.keys(fichier?.valeurs ?? {}).sort();

    return (
        <Dialog open onOpenChange={(ouvre) => !ouvre && onFermer()}>
            <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl" aria-describedby={undefined} data-fiche-modele={modele.id}>
                <div className="space-y-2 border-b px-6 py-4 pr-12">
                    <DialogTitle className="sr-only">{modele.nom}</DialogTitle>
                    <div className="flex items-center gap-2">
                        <Input
                            value={nom}
                            maxLength={80}
                            aria-label={t({ en: "Name of the template", fr: "Nom du modèle" })}
                            onChange={(e) => setNom(e.target.value)}
                            className="h-9 text-base font-semibold"
                        />
                        <Button type="button" size="sm" disabled={enCours || nom.trim() === "" || nom.trim() === modele.nom} onClick={renommer}>
                            {t({ en: "Rename", fr: "Renommer" })}
                        </Button>
                    </div>
                    <DialogDescription className="flex items-center gap-2">
                        <MarqueStatut statut={modele.statut ?? "candidat"} />
                        <span>v{modele.version ?? 1}</span>
                        <Info>
                            {t({
                                en: "The status and the versions are the library's: a person proves a template on a bench, or rejects it, from the library of the Lab.",
                                fr: "Le statut et les versions sont ceux de la bibliothèque : une personne prouve un modèle au banc, ou le rejette, depuis la bibliothèque du Labo.",
                            })}
                        </Info>
                    </DialogDescription>
                </div>
                <div className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-background px-6 py-5">
                    <p className="text-sm font-semibold">
                        {t({ en: "Settings by section", fr: "Réglages par section" })} · {modele.nombre_de_reglages}
                    </p>
                    <p className="text-xs text-muted-foreground">{modele.sections.map((s) => t(TITRES_DES_SECTIONS[s] ?? { en: s, fr: s })).join(", ")}</p>
                    <ul className="divide-y" data-reglages-du-modele>
                        {cles.map((c) => (
                            <li key={c} className="py-1.5">
                                <code className="text-[11px] text-muted-foreground">{c}</code>
                            </li>
                        ))}
                    </ul>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2 border-t px-6 py-3">
                    {confirmer ? (
                        <>
                            <span className="mr-auto text-sm">{t({ en: "Delete this template?", fr: "Supprimer ce modèle ?" })}</span>
                            <Button type="button" variant="destructive" size="sm" disabled={enCours} data-confirmer-suppression onClick={supprimer}>
                                {t({ en: "Confirm", fr: "Confirmer" })}
                            </Button>
                            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmer(false)}>
                                {t({ en: "Cancel", fr: "Annuler" })}
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmer(true)}>
                                {t({ en: "Delete", fr: "Supprimer" })}
                            </Button>
                            <Button type="button" variant="outline" size="sm" disabled={!fichier} onClick={() => fichier && telecharger(fichier, modele.nom)}>
                                {t({ en: "Export", fr: "Exporter" })}
                            </Button>
                            <Button type="button" size="sm" onClick={onFermer}>
                                {t({ en: "Close", fr: "Fermer" })}
                            </Button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};
