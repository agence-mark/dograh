"use client";

/**
 * [.mark] U3 sexies point 1 (E73, E74) : la fenêtre d'un outil, à onglets selon son type.
 *
 *  - Requête HTTP : Général · Requête · Paramètres · Réponse · Comportement · Essai · Activité ;
 *  - Action d'un logiciel : Général · Comportement · Essai · Activité ;
 *  - Outil MCP : Général · Comportement · Essai · Activité ;
 *  - Calculatrice : Général · Essai · Activité ;
 *  - Fin d'appel : Général · Fin d'appel · Activité ; transferts : Général · Destination · Activité ;
  - les autres types (rappel) : Général · Activité.
 *
 * N2 : tous les réglages d'un type sont ici (l'ancienne page d'un outil est retirée) : corps et valeurs fixes d'une
 * requête (onglet Paramètres), serveur MCP, action d'un logiciel et ses règles, fin d'appel, transferts
 * (``OngletsDeType.tsx``). Un enregistrement envoie la définition complète, la configuration fusionnée avec les modifications.
 */
import { useCallback, useState } from "react";

import {
    deleteToolApiV1ToolsToolUuidDelete,
    getToolApiV1ToolsToolUuidGet,
    unarchiveToolApiV1ToolsToolUuidUnarchivePost,
    updateToolApiV1ToolsToolUuidPut,
} from "@/client/sdk.gen";
import type { ResumeOutil, ToolResponse, UpdateToolRequest } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
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
import { BlocCorpsEtValeursFixes, OngletActionLogiciel, OngletFinAppel, OngletServeurMcp, OngletTransfertAgent, OngletTransfertAppel, validerConfig } from "./OngletsDeType";
import { OngletVersions } from "./versions/OngletVersions";
import { type AnnexeDeLOutil, TransfertGaranti } from "./TransfertGaranti";
import { notifier } from "@/components/mark/notifications";

type IdOnglet = "general" | "requete" | "parametres" | "reponse" | "action" | "serveur" | "fin" | "destination" | "comportement" | "essai" | "versions" | "activite";
const ONGLETS: Record<string, IdOnglet[]> = {
    http_api: ["general", "requete", "parametres", "reponse", "comportement", "essai", "versions", "activite"],
    integration: ["general", "action", "comportement", "essai", "versions", "activite"],
    mcp: ["general", "serveur", "comportement", "essai", "versions", "activite"],
    calculator: ["general", "essai", "versions", "activite"],
    end_call: ["general", "fin", "versions", "activite"],
    transfer_agent: ["general", "destination", "versions", "activite"],
    transfer_call: ["general", "destination", "versions", "activite"],
};
const PAR_DEFAUT: IdOnglet[] = ["general", "versions", "activite"];

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
    const [regleLogicielValide, setRegleLogicielValide] = useState(true);
    // D14 (clôture) : « Transfert garanti » est un réglage des agents qui utilisent l'outil de transfert : il s'enregistre avec l'outil, par le même bouton.
    const [annexe, setAnnexe] = useState<AnnexeDeLOutil | null>(null);
    const inscrireAnnexe = useCallback((a: AnnexeDeLOutil | null) => setAnnexe(a), []);

    const ids = ONGLETS[courant.category] ?? PAR_DEFAUT;
    const libelles: Record<IdOnglet, string> = {
        general: t({ en: "General", fr: "Général" }),
        requete: t({ en: "Request", fr: "Requête" }),
        parametres: t({ en: "Parameters", fr: "Paramètres" }),
        reponse: t({ en: "Response", fr: "Réponse" }),
        action: t({ en: "Action", fr: "Action" }),
        serveur: t({ en: "Server", fr: "Serveur" }),
        fin: t({ en: "End of call", fr: "Fin d'appel" }),
        destination: t({ en: "Destination", fr: "Destination" }),
        comportement: t({ en: "Behaviour", fr: "Comportement" }),
        essai: t({ en: "Trial", fr: "Essai" }),
        versions: t({ en: "Versions", fr: "Versions" }),
        activite: t({ en: "Activity", fr: "Activité" }),
    };
    const config: Config = { ...configDe(courant), ...modifs };
    const outilModifie = Object.keys(modifs).length > 0 || nom !== courant.name || description !== (courant.description ?? "");
    const modifie = outilModifie || Boolean(annexe?.modifie);
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
        const refus = validerConfig(courant.category, config, t);
        if (refus) return setErreur(refus);
        if (courant.category === "integration" && !regleLogicielValide) {
            return setErreur(t({ en: "The client's rules are not valid JSON.", fr: "Les règles du client ne sont pas du JSON valide." }));
        }
        setEnCours(true);
        if (!outilModifie) {
            // Seul le réglage des agents a changé : le pied l'enregistre, avec une notification.
            const ok = (await annexe?.enregistrer()) ?? true;
            setEnCours(false);
            if (ok) notifier.succes({ fr: "Transfert garanti enregistré.", en: "Guaranteed transfer saved." });
            return;
        }
        const corps: UpdateToolRequest = {
            name: nom.trim(),
            description: description.trim() || undefined,
            definition: definitionAvec(courant, modifs) as UpdateToolRequest["definition"],
        };
        const r = await updateToolApiV1ToolsToolUuidPut({ path: { tool_uuid: courant.tool_uuid }, body: corps });
        setEnCours(false);
        if (r.error || !r.data) return setErreur(echecAffiche(r.error, ECHECS.outilEnregistrer));
        setErreur(null);
        setCourant(r.data);
        setModifs({});
        apresEcriture();
        // Un seul geste, une seule notification : l'outil, puis les réglages des agents qui s'y attachent.
        const reglagesOk = annexe?.modifie ? await annexe.enregistrer() : true;
        if (reglagesOk) notifier.succes(annexe?.modifie ? { fr: "Outil et transfert garanti enregistrés.", en: "Tool and guaranteed transfer saved." } : { fr: "Outil enregistré.", en: "Tool saved." });
    };

    const archiver = async () => {
        const archive = courant.status === "archived";
        const r = archive
            ? await unarchiveToolApiV1ToolsToolUuidUnarchivePost({ path: { tool_uuid: courant.tool_uuid } })
            : await deleteToolApiV1ToolsToolUuidDelete({ path: { tool_uuid: courant.tool_uuid } });
        if (r.error) return setErreur(echecAffiche(r.error, ECHECS.outilArchiver));
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
            titre={<span>{courant.name}</span>}
            sous={type ? t(type) : courant.category}
            onglets={ids.map((i) => libelles[i])}
            onglet={libelles[onglet]}
            changerOnglet={(l) => setOnglet(ids.find((i) => libelles[i] === l) ?? "general")}
            valider={t({ en: "Save", fr: "Enregistrer" })}
            desactiver={!modifie || enCours}
            modifie={modifie}
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
                    <LigneChamp libelle={courant.status === "archived" ? t({ en: "Restore", fr: "Restaurer" }) : t({ en: "Archive", fr: "Archiver" })}>
                        <Button variant="outline" size="sm" onClick={() => void archiver()}>
                            {courant.status === "archived" ? t({ en: "Restore the tool", fr: "Restaurer l'outil" }) : t({ en: "Archive the tool", fr: "Archiver l'outil" })}
                        </Button>
                    </LigneChamp>
                </Champs>
            )}
            {onglet === "requete" && <OngletRequete config={config} pose={pose} />}
            {onglet === "parametres" && (
                <>
                    <OngletParametres config={config} pose={pose} />
                    <Champs>
                        <BlocCorpsEtValeursFixes config={config} pose={pose} />
                    </Champs>
                </>
            )}
            {onglet === "action" && <OngletActionLogiciel config={config} pose={pose} connecteurs={connecteurs} valide={setRegleLogicielValide} />}
            {onglet === "serveur" && <OngletServeurMcp config={config} pose={pose} />}
            {onglet === "fin" && <OngletFinAppel config={config} pose={pose} />}
            {onglet === "destination" && (courant.category === "transfer_agent" ? <OngletTransfertAgent config={config} pose={pose} /> : <OngletTransfertAppel config={config} pose={pose} />)}
            {/* Monté tant que la fenêtre est ouverte (caché hors de l'onglet) : un changement non enregistré ne se perd pas en changeant d'onglet. */}
            {courant.category === "transfer_call" && (
                <div hidden={onglet !== "destination"}>
                    <TransfertGaranti toolUuid={courant.tool_uuid} inscrire={inscrireAnnexe} />
                </div>
            )}
            {onglet === "reponse" && <OngletReponse config={config} pose={pose} />}
            {onglet === "comportement" && <OngletComportement categorie={courant.category} config={config} pose={pose} />}
            {onglet === "essai" && <OngletEssai outil={courant} config={config} ecrit={ecrit} modifie={modifie} apres={() => void relireApresEssai()} />}
            {onglet === "versions" && <OngletVersions toolUuid={courant.tool_uuid} nom={courant.name} />}
            {onglet === "activite" && <OngletActivite toolUuid={courant.tool_uuid} />}
        </FenetreOnglets>
    );
}
