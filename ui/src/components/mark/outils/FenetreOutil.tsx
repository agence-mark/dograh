"use client";

/**
 * [.mark] U3 sexies point 1 (E73, E74) : la fenêtre d'un outil, à onglets selon son type.
 *
 *  - Requête HTTP : Général · Requête · Paramètres · Réponse · Comportement · Essai · Activité ;
 *  - Action d'un logiciel : Général · Comportement · Essai · Activité ;
 *  - Outil MCP : Général · Comportement · Essai · Activité ;
 *  - Calculatrice : Général · Essai · Activité ;
 *  - les autres types (fin d'appel, transferts, rappel) : Général · Activité.
 *
 * Les champs propres à un type que cette fenêtre ne dessine pas (corps de la requête, valeurs préréglées, règles
 * d'une action de logiciel, destination d'un transfert…) restent dans l'éditeur du type (lien « Éditeur complet »),
 * qui les garde tous : rien n'est retiré. Un enregistrement envoie la définition complète, la configuration
 * fusionnée avec les modifications.
 */
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
    deleteToolApiV1ToolsToolUuidDelete,
    getToolApiV1ToolsToolUuidGet,
    unarchiveToolApiV1ToolsToolUuidUnarchivePost,
    updateToolApiV1ToolsToolUuidPut,
} from "@/client/sdk.gen";
import type { ResumeOutil, ToolResponse, UpdateToolRequest } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { comptesDuLogiciel } from "../connecteurs/ConfigOutilIntegration";
import { useConnecteurs } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { BlocChamp, Champs, FenetreOnglets, LigneChamp } from "../studio/fenetre-onglets";
import { Liste } from "../studio/liste";
import { Marque } from "../studio/marques";
import { type Config, configDe, definitionAvec, ecritHttp, LIBELLES_TYPE, premierEssaiValide, texte, type TypeOutil } from "./modele";
import { OngletActivite } from "./OngletActivite";
import { OngletComportement } from "./OngletComportement";
import { OngletEssai } from "./OngletEssai";
import { OngletParametres, OngletReponse, OngletRequete } from "./OngletsHttp";
import { notifier } from "@/components/mark/notifications";

type IdOnglet = "general" | "requete" | "parametres" | "reponse" | "comportement" | "essai" | "activite";
const ONGLETS: Record<string, IdOnglet[]> = {
    http_api: ["general", "requete", "parametres", "reponse", "comportement", "essai", "activite"],
    integration: ["general", "comportement", "essai", "activite"],
    mcp: ["general", "comportement", "essai", "activite"],
    calculator: ["general", "essai", "activite"],
};
const PAR_DEFAUT: IdOnglet[] = ["general", "activite"];

export function FenetreOutil({
    outil,
    resume,
    fermer,
    apresEcriture,
}: {
    outil: ToolResponse;
    resume?: ResumeOutil;
    fermer: () => void;
    apresEcriture: () => void;
}) {
    const { t } = useLangue();
    const connecteurs = useConnecteurs();
    const [courant, setCourant] = useState<ToolResponse>(outil);
    const [onglet, setOnglet] = useState<IdOnglet>("general");
    const [nom, setNom] = useState(outil.name);
    const [description, setDescription] = useState(outil.description ?? "");
    const [modifs, setModifs] = useState<Config>({});
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    const ids = ONGLETS[courant.category] ?? PAR_DEFAUT;
    const libelles: Record<IdOnglet, string> = {
        general: t({ en: "General", fr: "Général" }),
        requete: t({ en: "Request", fr: "Requête" }),
        parametres: t({ en: "Parameters", fr: "Paramètres" }),
        reponse: t({ en: "Response", fr: "Réponse" }),
        comportement: t({ en: "Behaviour", fr: "Comportement" }),
        essai: t({ en: "Trial", fr: "Essai" }),
        activite: t({ en: "Activity", fr: "Activité" }),
    };
    const config: Config = { ...configDe(courant), ...modifs };
    const modifie = Object.keys(modifs).length > 0 || nom !== courant.name || description !== (courant.description ?? "");
    const pose = (m: Config) => setModifs((x) => ({ ...x, ...m }));

    let ecrit = false;
    if (courant.category === "http_api") ecrit = ecritHttp(config);
    else if (courant.category === "mcp") ecrit = true;
    else if (courant.category === "integration") {
        ecrit = Boolean(connecteurs.catalogue?.find((c) => c.nom === texte(config, "connecteur"))?.actions.find((a) => a.nom === texte(config, "action"))?.ecrit);
    }

    const comptesBranches = courant.category === "integration" ? comptesDuLogiciel(connecteurs, texte(config, "connecteur")) : [];

    const enregistrer = async () => {
        if (!nom.trim()) return setErreur(t({ en: "Give the tool a name.", fr: "Donnez un nom à l'outil." }));
        setEnCours(true);
        const corps: UpdateToolRequest = {
            name: nom.trim(),
            description: description.trim() || undefined,
            definition: definitionAvec(courant, modifs) as UpdateToolRequest["definition"],
        };
        const r = await updateToolApiV1ToolsToolUuidPut({ path: { tool_uuid: courant.tool_uuid }, body: corps });
        setEnCours(false);
        if (r.error || !r.data) return setErreur(detailFromError(r.error, "Failed to save tool"));
        setErreur(null);
        setCourant(r.data);
        setModifs({});
        apresEcriture();
        notifier.succes({ fr: "Outil enregistré.", en: "Tool saved." });
    };

    const archiver = async () => {
        const archive = courant.status === "archived";
        const r = archive
            ? await unarchiveToolApiV1ToolsToolUuidUnarchivePost({ path: { tool_uuid: courant.tool_uuid } })
            : await deleteToolApiV1ToolsToolUuidDelete({ path: { tool_uuid: courant.tool_uuid } });
        if (r.error) return setErreur(detailFromError(r.error, "Failed"));
        apresEcriture();
        fermer();
        if (archive) notifier.succes({ fr: "Outil restauré.", en: "Tool restored." });
        else
            notifier.reversible({ fr: "Outil archivé.", en: "Tool archived." }, async () => {
                await unarchiveToolApiV1ToolsToolUuidUnarchivePost({ path: { tool_uuid: courant.tool_uuid } });
                apresEcriture();
            });
    };

    // Après un essai, le serveur a écrit « dernier essai » / « premier essai » : on relit l'outil sans perdre les modifications en cours.
    const relireApresEssai = async () => {
        const r = await getToolApiV1ToolsToolUuidGet({ path: { tool_uuid: courant.tool_uuid } });
        if (r.data) setCourant(r.data);
        apresEcriture();
    };

    const type = LIBELLES_TYPE[courant.category as TypeOutil];
    return (
        <FenetreOnglets
            fermer={fermer}
            titre={<span className="font-mono">{courant.name}</span>}
            sous={type ? t(type) : courant.category}
            onglets={ids.map((i) => libelles[i])}
            onglet={libelles[onglet]}
            changerOnglet={(l) => setOnglet(ids.find((i) => libelles[i] === l) ?? "general")}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            desactiver={!modifie || enCours}
            onValider={() => void enregistrer()}
            pied={erreur ? <span className="text-sm text-destructive">{erreur}</span> : undefined}
        >
            {onglet === "general" && (
                <Champs>
                    <BlocChamp libelle={t({ en: "Name", fr: "Nom" })}>
                        <Input value={nom} onChange={(e) => setNom(e.target.value)} aria-label={t({ en: "Name", fr: "Nom" })} />
                    </BlocChamp>
                    <BlocChamp
                        libelle={t({ en: "Description for the model", fr: "Description pour le modèle" })}
                        info={t({ en: "States exactly when the agent should call the tool and what it gets back.", fr: "Dit exactement quand l'agent doit appeler l'outil et ce qu'il en reçoit." })}
                    >
                        <Input value={description} onChange={(e) => setDescription(e.target.value)} aria-label={t({ en: "Description", fr: "Description" })} />
                    </BlocChamp>
                    <LigneChamp libelle={t({ en: "Access", fr: "Accès" })}>
                        <Marque>{ecrit ? t({ en: "Writes", fr: "Écrit" }) : t({ en: "Reads", fr: "Lit" })}</Marque>
                    </LigneChamp>
                    {courant.category === "integration" && comptesBranches.length > 0 && (
                        <LigneChamp
                            libelle={t({ en: "Connected account", fr: "Compte branché" })}
                            info={t({ en: "The connected accounts of this software (Integrations › Software). The tool follows the one chosen here.", fr: "Les comptes branchés de ce logiciel (Intégrations › Logiciels). L'outil suit celui choisi ici." })}
                        >
                            <Liste
                                valeur={comptesBranches.includes(texte(config, "compte")) ? texte(config, "compte") : comptesBranches[0]}
                                changer={(v) => pose({ compte: v })}
                                options={comptesBranches}
                                className="w-64"
                            />
                        </LigneChamp>
                    )}
                    {["http_api", "mcp", "integration"].includes(courant.category) && (
                        <LigneChamp libelle={t({ en: "First trial", fr: "Premier essai" })}>
                            <Marque ton={premierEssaiValide(config) ? "succes" : "neutre"}>
                                {premierEssaiValide(config) ? t({ en: "Validated by a person", fr: "Validé par une personne" }) : t({ en: "Not validated", fr: "Non validé" })}
                            </Marque>
                        </LigneChamp>
                    )}
                    {resume && (
                        <LigneChamp libelle={t({ en: "Agents using it", fr: "Agents qui l'utilisent" })}>
                            <span className="text-sm tabular-nums">{resume.nb_agents}</span>
                        </LigneChamp>
                    )}
                    <LigneChamp
                        libelle={t({ en: "Full editor", fr: "Éditeur complet" })}
                        info={t({
                            en: "Every field of this type (request body, preset values, rules, destination…) in the type's own editor.",
                            fr: "Tous les champs de ce type (corps de la requête, valeurs préréglées, règles, destination…) dans l'éditeur du type.",
                        })}
                    >
                        <Link href={`/tools/${courant.tool_uuid}`} className="inline-flex cursor-pointer items-center gap-1.5 text-sm hover:font-medium">
                            {t({ en: "Open", fr: "Ouvrir" })} <ExternalLink className="size-3.5" />
                        </Link>
                    </LigneChamp>
                    <LigneChamp libelle={courant.status === "archived" ? t({ en: "Restore", fr: "Restaurer" }) : t({ en: "Archive", fr: "Archiver" })}>
                        <Button variant="outline" size="sm" onClick={() => void archiver()}>
                            {courant.status === "archived" ? t({ en: "Restore the tool", fr: "Restaurer l'outil" }) : t({ en: "Archive the tool", fr: "Archiver l'outil" })}
                        </Button>
                    </LigneChamp>
                </Champs>
            )}
            {onglet === "requete" && <OngletRequete config={config} pose={pose} />}
            {onglet === "parametres" && <OngletParametres config={config} pose={pose} />}
            {onglet === "reponse" && <OngletReponse config={config} pose={pose} />}
            {onglet === "comportement" && <OngletComportement categorie={courant.category} config={config} pose={pose} />}
            {onglet === "essai" && <OngletEssai outil={courant} config={config} ecrit={ecrit} modifie={modifie} apres={() => void relireApresEssai()} />}
            {onglet === "activite" && <OngletActivite toolUuid={courant.tool_uuid} />}
        </FenetreOnglets>
    );
}
