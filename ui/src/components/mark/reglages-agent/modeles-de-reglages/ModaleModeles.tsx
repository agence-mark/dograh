"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot 5 (plan modeles-de-reglages, M1 a M11) : les MODELES DE
 * REGLAGES, depuis l'en-tete fixe de la page des reglages de l'agent (M11), dans une MODALE centree (jamais un
 * panneau lateral).
 *
 * Un modele fige, sous un nom, les reglages de comportement d'un agent (pas les prompts, le graphe, les variables,
 * les outils, les numeros, les donnees du client, ni jamais une cle d'acces : M3, M6). L'appliquer est une COPIE sur
 * le BROUILLON de l'agent (M4, M5), par section cochee (toutes cochees d'office, M2). Un modele passe d'un client a
 * l'autre par un fichier exporte puis importe (M1).
 *
 * ⛔ Aucun texte sans champ reel : tout ce qui s'affiche vient de la reponse du serveur (noms, dates, origine,
 * sections, comptes, fournisseurs sans cle) ou de l'etat de la page (changements non enregistres).
 * ⛔ Les sections sont celles que le serveur envoie, nommees comme les themes de l'ecran : une section nouvelle cote
 * serveur sans titre ici s'affiche sous son identifiant (le test le releve).
 */
import { Download, FileUp, LayoutTemplate, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
    appliquerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdAppliquerPost,
    creerUnModeleApiV1OrganizationsModelesDeReglagesPost,
    exporterUnModeleApiV1OrganizationsModelesDeReglagesModeleIdExportGet,
    importerUnModeleApiV1OrganizationsModelesDeReglagesImportPost,
    listerLesModelesApiV1OrganizationsModelesDeReglagesGet,
    mentionDeLagentApiV1OrganizationsModelesDeReglagesAgentWorkflowIdGet,
    renommerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdPatch,
    supprimerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdDelete,
} from "@/client/sdk.gen";
import type {
    ListeDesModeles,
    MentionApplication,
    ResultatApplication,
    ResumeDuModele,
} from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../../langue/langue";
import { CadreModale } from "../phrases/cadre";
import { TITRE_AGENT } from "../ThemeAgent";
import { TITRE_BRIQUES } from "../ThemeBriques";
import { TITRE_DONNEES } from "../ThemeDonnees";
import { TITRE_ECOUTE } from "../ThemeEcoute";
import { TITRE_ETABLISSEMENT } from "../ThemeEtablissement";
import { TITRE_MODULES } from "../ThemeModules";
import { TITRE_RYTHME } from "../ThemeRythme";
import { TITRE_TOUR } from "../ThemeTourDeParole";
import { TITRE_VOIX } from "../ThemeVoix";

/** Les sections d'un modele : l'identifiant du theme de l'ecran et son titre (`classement.py`, `SECTIONS`). */
export const TITRES_DES_SECTIONS: Record<string, Texte> = {
    agent: TITRE_AGENT,
    briques: TITRE_BRIQUES,
    ecoute: TITRE_ECOUTE,
    // cloture-code, F8 (M4): the modules' keys, a section of their own like their theme.
    modules: TITRE_MODULES,
    tour: TITRE_TOUR,
    voix: TITRE_VOIX,
    rythme: TITRE_RYTHME,
    donnees: TITRE_DONNEES,
    etablissement: TITRE_ETABLISSEMENT,
};

const TITRE: Texte = { en: "Settings templates", fr: "Modèles de réglages" };

type Vue = { type: "liste" } | { type: "appliquer"; modele: ResumeDuModele };

/** Le fichier exporte, tel que le serveur le rend ; relu sans le transformer a l'import. */
const lireFichier = (fichier: File): Promise<string> =>
    typeof fichier.text === "function"
        ? fichier.text()
        : new Promise((resolve, reject) => {
              const lecteur = new FileReader();
              lecteur.onload = () => resolve(String(lecteur.result));
              lecteur.onerror = () => reject(lecteur.error);
              lecteur.readAsText(fichier);
          });

const nomDeFichier = (nom: string) => `modele-${nom.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "reglages"}.json`;

export const BoutonModeles = ({
    workflowId,
    modifie,
    apresApplication = () => window.location.reload(),
}: {
    workflowId: number;
    /** Des changements de la page ne sont pas enregistres : creer ou appliquer demande de les enregistrer d'abord (M11). */
    modifie: boolean;
    /** Une fois un modele applique, la page se recharge pour montrer les nouvelles valeurs (M11). */
    apresApplication?: () => void;
}) => {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    return (
        <>
            <Button type="button" variant="outline" size="sm" data-bouton-modeles onClick={() => setOuvert(true)}>
                <LayoutTemplate className="mr-1.5 h-4 w-4" />
                {t(TITRE)}
            </Button>
            {ouvert && (
                <ModaleModeles
                    workflowId={workflowId}
                    modifie={modifie}
                    apresApplication={apresApplication}
                    onFermer={() => setOuvert(false)}
                />
            )}
        </>
    );
};

export const ModaleModeles = ({
    workflowId,
    modifie,
    apresApplication,
    onFermer,
}: {
    workflowId: number;
    modifie: boolean;
    apresApplication: () => void;
    onFermer: () => void;
}) => {
    const { t, langue } = useLangue();
    const [liste, setListe] = useState<ListeDesModeles | null>(null);
    const [mention, setMention] = useState<MentionApplication | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [vue, setVue] = useState<Vue>({ type: "liste" });
    const [nouveauNom, setNouveauNom] = useState("");
    const [renommage, setRenommage] = useState<{ id: string; nom: string } | null>(null);
    const [aSupprimer, setASupprimer] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const fichierImport = useRef<HTMLInputElement>(null);

    const charger = useCallback(async () => {
        const [modeles, derniere] = await Promise.all([
            listerLesModelesApiV1OrganizationsModelesDeReglagesGet(),
            mentionDeLagentApiV1OrganizationsModelesDeReglagesAgentWorkflowIdGet({ path: { workflow_id: workflowId } }),
        ]);
        if (modeles.error || !modeles.data) {
            setErreur(detailFromError(modeles.error, t({ en: "The templates could not be read.", fr: "Les modèles n'ont pas pu être lus." })));
            return;
        }
        setErreur(null);
        setListe(modeles.data);
        setMention(derniere.data?.mention ?? null);
    }, [workflowId, t]);

    useEffect(() => {
        void charger();
        // Une lecture a l'ouverture ; les gestes rechargent eux-memes.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /** Un geste du serveur : le message du serveur s'il refuse, la liste relue s'il accepte. */
    const geste = async (action: () => Promise<{ error?: unknown } | undefined>, succes?: string) => {
        if (enCours) return false;
        setEnCours(true);
        try {
            const reponse = await action();
            if (reponse?.error) {
                toast.error(detailFromError(reponse.error, t({ en: "The server refused.", fr: "Le serveur a refusé." })));
                return false;
            }
            if (succes) toast.success(succes);
            await charger();
            return true;
        } catch {
            toast.error(t({ en: "The server did not answer.", fr: "Le serveur n'a pas répondu." }));
            return false;
        } finally {
            setEnCours(false);
        }
    };

    const creer = async () => {
        const fait = await geste(
            () => creerUnModeleApiV1OrganizationsModelesDeReglagesPost({ body: { nom: nouveauNom, workflow_id: workflowId } }),
            t({ en: "Template created.", fr: "Modèle créé." }),
        );
        if (fait) setNouveauNom("");
    };

    const renommer = async () => {
        if (!renommage) return;
        const fait = await geste(() =>
            renommerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdPatch({ path: { modele_id: renommage.id }, body: { nom: renommage.nom } }),
        );
        if (fait) setRenommage(null);
    };

    const supprimer = async (id: string) => {
        const fait = await geste(
            () => supprimerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdDelete({ path: { modele_id: id } }),
            t({ en: "Template deleted. The agents already set keep their settings.", fr: "Modèle supprimé. Les agents déjà réglés gardent leurs réglages." }),
        );
        if (fait) setASupprimer(null);
    };

    const exporter = async (modele: ResumeDuModele) => {
        await geste(async () => {
            const reponse = await exporterUnModeleApiV1OrganizationsModelesDeReglagesModeleIdExportGet({ path: { modele_id: modele.id } });
            if (reponse.error || !reponse.data) return { error: reponse.error ?? "x" };
            const lien = document.createElement("a");
            lien.href = URL.createObjectURL(new Blob([JSON.stringify(reponse.data, null, 2)], { type: "application/json" }));
            lien.download = nomDeFichier(modele.nom);
            lien.click();
            URL.revokeObjectURL(lien.href);
            return undefined;
        });
    };

    const importer = async (fichier: File | undefined) => {
        if (!fichier) return;
        let corps: unknown;
        try {
            corps = JSON.parse(await lireFichier(fichier));
        } catch {
            toast.error(t({ en: "This file is not a settings template.", fr: "Ce fichier n'est pas un modèle de réglages." }));
            return;
        }
        await geste(
            // Le fichier part tel quel : le serveur nomme le reglage qu'il refuse.
            () => importerUnModeleApiV1OrganizationsModelesDeReglagesImportPost({ body: corps as never }),
            t({ en: "Template imported.", fr: "Modèle importé." }),
        );
        if (fichierImport.current) fichierImport.current.value = "";
    };

    const date = (iso: string) => new Date(iso).toLocaleDateString(langue === "fr" ? "fr-FR" : "en-GB");
    const titreSection = (id: string) => t(TITRES_DES_SECTIONS[id] ?? { en: id, fr: id });

    if (vue.type === "appliquer") {
        return (
            <VueApplication
                modele={vue.modele}
                sections={liste?.sections ?? []}
                workflowId={workflowId}
                modifie={modifie}
                date={date}
                titreSection={titreSection}
                onRetour={() => setVue({ type: "liste" })}
                onFait={apresApplication}
                onFermer={onFermer}
            />
        );
    }

    return (
        <CadreModale
            identifiant="modeles-de-reglages"
            titre={t(TITRE)}
            description={t({
                en: "Freeze the active settings of this agent under a name, and apply them to another agent in one gesture.",
                fr: "Figer sous un nom les réglages actifs de cet agent, et les appliquer à un autre agent en un geste.",
            })}
            onFermer={onFermer}
            pied={
                <>
                    <code className="text-[11px] text-muted-foreground">MODELES_REGLAGES</code>
                    <Button type="button" variant="outline" onClick={onFermer}>
                        {t({ en: "Close", fr: "Fermer" })}
                    </Button>
                </>
            }
        >
            <div className="space-y-5">
                <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground" data-notice-modeles>
                    {t({
                        en: "A template holds behaviour settings only: never prompts, the flow, variables, tools, numbers, the client's own data, nor any API key. Applying a template is a copy on the draft: changing or deleting it later changes no agent already set.",
                        fr: "Un modèle ne porte que des réglages de comportement : jamais les prompts, le parcours, les variables, les outils, les numéros, les données propres au client, ni aucune clé d'accès. Appliquer un modèle est une copie sur le brouillon : le modifier ou le supprimer ensuite ne change aucun agent déjà réglé.",
                    })}
                </p>

                {erreur && (
                    <p role="alert" className="text-sm text-destructive" data-erreur-modeles>
                        {erreur}
                    </p>
                )}

                {modifie && (
                    <p role="alert" className="rounded-lg border border-orange-500/50 bg-orange-500/10 p-3 text-sm" data-non-enregistre>
                        {t({
                            en: "This page has unsaved changes. Save them first: a template is frozen from, and applied to, what is saved.",
                            fr: "Cette page a des changements non enregistrés. Enregistrez-les d'abord : un modèle est figé depuis, et appliqué sur, ce qui est enregistré.",
                        })}
                    </p>
                )}

                {mention && (
                    <p className="text-sm" data-mention-modele>
                        {t({ en: "Last template applied to this agent:", fr: "Dernier modèle appliqué à cet agent :" })}{" "}
                        <strong>{mention.nom}</strong> · {date(mention.applique_le)} · {(mention.sections ?? []).map(titreSection).join(", ")}
                    </p>
                )}

                <section className="space-y-2">
                    <h3 className="text-sm font-semibold">{t({ en: "Create from the active settings", fr: "Créer depuis les réglages actifs" })}</h3>
                    <div className="flex gap-2">
                        <Input
                            value={nouveauNom}
                            maxLength={80}
                            placeholder={t({ en: "Name of the template", fr: "Nom du modèle" })}
                            aria-label={t({ en: "Name of the template", fr: "Nom du modèle" })}
                            onChange={(e) => setNouveauNom(e.target.value)}
                        />
                        <Button type="button" data-creer-modele disabled={modifie || enCours || nouveauNom.trim() === ""} onClick={creer}>
                            {t({ en: "Create", fr: "Créer" })}
                        </Button>
                    </div>
                </section>

                <section className="space-y-2">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold">{t({ en: "Templates of this organization", fr: "Modèles de cette organisation" })}</h3>
                        <div>
                            <input
                                ref={fichierImport}
                                type="file"
                                accept="application/json,.json"
                                className="hidden"
                                data-import-modele
                                onChange={(e) => void importer(e.target.files?.[0])}
                            />
                            <Button type="button" variant="outline" size="sm" disabled={enCours} onClick={() => fichierImport.current?.click()}>
                                <FileUp className="mr-1.5 h-4 w-4" />
                                {t({ en: "Import a file", fr: "Importer un fichier" })}
                            </Button>
                        </div>
                    </div>
                    {liste && liste.modeles.length === 0 && (
                        <p className="text-sm text-muted-foreground" data-aucun-modele>
                            {t({ en: "No template yet.", fr: "Aucun modèle pour l'instant." })}
                        </p>
                    )}
                    <ul className="space-y-2">
                        {(liste?.modeles ?? []).map((modele) => (
                            <li key={modele.id} data-modele={modele.id} className="rounded-lg border p-3">
                                {renommage?.id === modele.id ? (
                                    <div className="flex gap-2">
                                        <Input
                                            value={renommage.nom}
                                            maxLength={80}
                                            aria-label={t({ en: "New name", fr: "Nouveau nom" })}
                                            onChange={(e) => setRenommage({ id: modele.id, nom: e.target.value })}
                                        />
                                        <Button type="button" size="sm" disabled={enCours || renommage.nom.trim() === ""} onClick={renommer}>
                                            {t({ en: "Rename", fr: "Renommer" })}
                                        </Button>
                                        <Button type="button" size="sm" variant="ghost" onClick={() => setRenommage(null)}>
                                            {t({ en: "Cancel", fr: "Annuler" })}
                                        </Button>
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                        <div className="min-w-0 space-y-0.5">
                                            <p className="truncate text-sm font-medium">{modele.nom}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {date(modele.cree_le)} · {origine(modele, t)} · {modele.nombre_de_reglages}{" "}
                                                {t({ en: "settings", fr: "réglages" })}
                                            </p>
                                            <p className="text-xs text-muted-foreground">{modele.sections.map(titreSection).join(", ")}</p>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-1.5">
                                            <Button type="button" size="sm" data-appliquer-modele disabled={enCours} onClick={() => setVue({ type: "appliquer", modele })}>
                                                {t({ en: "Apply", fr: "Appliquer" })}
                                            </Button>
                                            <Button
                                                type="button"
                                                size="icon"
                                                variant="ghost"
                                                aria-label={t({ en: "Rename", fr: "Renommer" })}
                                                disabled={enCours}
                                                onClick={() => setRenommage({ id: modele.id, nom: modele.nom })}
                                            >
                                                <Pencil className="h-4 w-4" />
                                            </Button>
                                            <Button
                                                type="button"
                                                size="icon"
                                                variant="ghost"
                                                aria-label={t({ en: "Export", fr: "Exporter" })}
                                                disabled={enCours}
                                                onClick={() => void exporter(modele)}
                                            >
                                                <Download className="h-4 w-4" />
                                            </Button>
                                            {aSupprimer === modele.id ? (
                                                <>
                                                    <Button type="button" size="sm" variant="destructive" data-confirmer-suppression disabled={enCours} onClick={() => void supprimer(modele.id)}>
                                                        {t({ en: "Confirm", fr: "Confirmer" })}
                                                    </Button>
                                                    <Button type="button" size="sm" variant="ghost" onClick={() => setASupprimer(null)}>
                                                        {t({ en: "Cancel", fr: "Annuler" })}
                                                    </Button>
                                                </>
                                            ) : (
                                                <Button
                                                    type="button"
                                                    size="icon"
                                                    variant="ghost"
                                                    aria-label={t({ en: "Delete", fr: "Supprimer" })}
                                                    disabled={enCours}
                                                    onClick={() => setASupprimer(modele.id)}
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                </section>
            </div>
        </CadreModale>
    );
};

const origine = (modele: ResumeDuModele, t: (texte: Texte) => string): string => {
    const o = modele.origine;
    if (!o?.agent_nom) return t({ en: "imported file", fr: "fichier importé" });
    const statut =
        o.version_status === "draft" ? t({ en: "draft", fr: "brouillon" }) : o.version_status === "published" ? t({ en: "published", fr: "publiée" }) : null;
    return `${o.agent_nom}${o.version_number != null ? ` · v${o.version_number}` : ""}${statut ? ` (${statut})` : ""}`;
};

const VueApplication = ({
    modele,
    sections,
    workflowId,
    modifie,
    date,
    titreSection,
    onRetour,
    onFait,
    onFermer,
}: {
    modele: ResumeDuModele;
    sections: string[];
    workflowId: number;
    modifie: boolean;
    date: (iso: string) => string;
    titreSection: (id: string) => string;
    onRetour: () => void;
    onFait: () => void;
    onFermer: () => void;
}) => {
    const { t } = useLangue();
    // M2 : toutes les sections que le modele porte sont cochees d'office.
    const [cochees, setCochees] = useState<string[]>(() => sections.filter((s) => modele.sections.includes(s)));
    const [apercu, setApercu] = useState<ResultatApplication | null>(null);
    const [refus, setRefus] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    // Avant d'appliquer, la modale DIT ce qui va se passer, dont les fournisseurs sans cle (M3), sans rien ecrire.
    useEffect(() => {
        let annule = false;
        setApercu(null);
        setRefus(null);
        if (cochees.length === 0) return;
        (async () => {
            const reponse = await appliquerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdAppliquerPost({
                path: { modele_id: modele.id },
                body: { workflow_id: workflowId, sections: cochees, a_blanc: true },
            });
            if (annule) return;
            if (reponse.error || !reponse.data) setRefus(detailFromError(reponse.error, t({ en: "The server refused.", fr: "Le serveur a refusé." })));
            else setApercu(reponse.data);
        })();
        return () => {
            annule = true;
        };
        // `t` change avec la langue seulement.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cochees, modele.id, workflowId]);

    const appliquer = async () => {
        if (enCours) return;
        setEnCours(true);
        try {
            const reponse = await appliquerUnModeleApiV1OrganizationsModelesDeReglagesModeleIdAppliquerPost({
                path: { modele_id: modele.id },
                body: { workflow_id: workflowId, sections: cochees, a_blanc: false },
            });
            if (reponse.error || !reponse.data) {
                toast.error(detailFromError(reponse.error, t({ en: "The server refused.", fr: "Le serveur a refusé." })));
                return;
            }
            toast.success(t({ en: "Template applied to the draft.", fr: "Modèle appliqué au brouillon." }));
            onFait();
        } catch {
            toast.error(t({ en: "The server did not answer.", fr: "Le serveur n'a pas répondu." }));
        } finally {
            setEnCours(false);
        }
    };

    return (
        <CadreModale
            identifiant="appliquer-modele"
            titre={`${t({ en: "Apply", fr: "Appliquer" })} · ${modele.nom}`}
            description={t({
                en: "The ticked sections take the template's values on the draft of this agent. Everything else is kept. Publish afterwards, as for any change.",
                fr: "Les sections cochées prennent les valeurs du modèle sur le brouillon de cet agent. Tout le reste est gardé. Publiez ensuite, comme pour tout changement.",
            })}
            onFermer={onFermer}
            pied={
                <>
                    <Button type="button" variant="outline" onClick={onRetour}>
                        {t({ en: "Back", fr: "Retour" })}
                    </Button>
                    <Button type="button" data-valider-application disabled={modifie || enCours || cochees.length === 0 || refus !== null} onClick={appliquer}>
                        {t({ en: "Apply to the draft", fr: "Appliquer au brouillon" })}
                    </Button>
                </>
            }
        >
            <div className="space-y-4">
                <p className="text-xs text-muted-foreground">
                    {date(modele.cree_le)} · {origine(modele, t)}
                </p>
                {modifie && (
                    <p role="alert" className="rounded-lg border border-orange-500/50 bg-orange-500/10 p-3 text-sm" data-non-enregistre>
                        {t({
                            en: "This page has unsaved changes. Save them first, then apply.",
                            fr: "Cette page a des changements non enregistrés. Enregistrez-les d'abord, puis appliquez.",
                        })}
                    </p>
                )}
                <ul className="space-y-2">
                    {sections.map((section) => {
                        const portee = modele.sections.includes(section);
                        return (
                            <li key={section} className="flex items-center gap-2">
                                <Checkbox
                                    id={`section-${section}`}
                                    data-section={section}
                                    checked={cochees.includes(section)}
                                    disabled={!portee}
                                    onCheckedChange={(coche) =>
                                        setCochees((avant) => (coche === true ? [...avant, section] : avant.filter((s) => s !== section)))
                                    }
                                />
                                <label htmlFor={`section-${section}`} className={`text-sm ${portee ? "" : "text-muted-foreground"}`}>
                                    {titreSection(section)}
                                    {!portee && ` · ${t({ en: "not in this template", fr: "absente de ce modèle" })}`}
                                </label>
                            </li>
                        );
                    })}
                </ul>

                {refus && (
                    <p role="alert" className="text-sm text-destructive" data-refus-application>
                        {refus}
                    </p>
                )}
                {apercu && (
                    <div className="space-y-2 text-sm" data-apercu-application>
                        <p>
                            {apercu.posees.length} {t({ en: "settings take the template's value", fr: "réglages prennent la valeur du modèle" })}
                            {apercu.retirees.length > 0 && (
                                <>
                                    {" · "}
                                    {apercu.retirees.length} {t({ en: "go back to their default", fr: "reviennent à leur valeur par défaut" })}
                                </>
                            )}
                        </p>
                        {apercu.fournisseurs_sans_cle.map((fournisseur) => (
                            <p key={fournisseur} className="text-orange-600" data-sans-cle={fournisseur}>
                                {t({ en: "No key for", fr: "Aucune clé pour" })} {fournisseur}{" "}
                                {t({ en: "in this agent or its organization.", fr: "dans cet agent ni dans son organisation." })}
                            </p>
                        ))}
                        {apercu.non_appliquees.map((r) => (
                            <p key={r.cle} className="text-orange-600" data-non-appliquee={r.cle}>
                                <code className="text-xs">{r.cle}</code>{" "}
                                {t({
                                    en: "will not be applied: the agent keeps its own (a brick without its key would stop the calls).",
                                    fr: "ne sera pas appliqué : l'agent garde le sien (une brique sans sa clé couperait les appels).",
                                })}
                            </p>
                        ))}
                    </div>
                )}
            </div>
        </CadreModale>
    );
};
