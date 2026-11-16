"use client";

/**
 * [.mark] Theme « Modules » (cloture-code, F8, M4; decided by Evan on 16/10 and 22/10): the agent's modules,
 * one drop-down sub-menu each -- its switch, its own settings, and « plugs into: <translator> » for each
 * need. The cards MOVED here from « Listening » (numbers, town and street, spelling, trade vocabulary,
 * field recognition) and « Call data » (team, caller verification): same controls, same help, same
 * conditions (E8), same payload (`charges-utiles-agent.test.tsx`); they no longer exist where they were.
 *
 * The sub-menus are the decided exception to E1, like a provider's (E2). A sub-menu holding a value to fix
 * opens on « show » (E7). What depends on the organization comes from `GET /agents/{id}/modules`; without
 * it the settings stay as they are, only those lines are missing.
 */
import { Puzzle } from "lucide-react";
import { useEffect, useState } from "react";

import { getModulesDeLAgentApiV1AgentsAgentIdModulesGet } from "@/client/sdk.gen";
import type { ModuleDeLAgent } from "@/client/types.gen";
import { Switch } from "@/components/ui/switch";

import { GroupeModuleRestauration } from "../restauration/modules-restauration";
import { ChampReglage } from "../ecran/ChampReglage";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { CATALOGUE, type CleCatalogue, erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { CLES_MODULES, moduleDeLaCle, MODULES_AGENT } from "./modules-agent";
import { Besoins, SousMenuModule } from "./sous-menu-module";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_MODULES = "modules";
export const TITRE_MODULES = { en: "Modules", fr: "Modules" };

// Chantier l-agent-collegue, L1 (C4 to C6): what the switch gives the agent and the summary (moved from « Call data »).
export const AIDES_EQUIPE_CONNUE: Texte[] = [
    {
        en: "At pick-up the agent receives {{equipe}}: one line per active person of the establishment called and of the whole company, with the role and what the person takes care of. Place {{equipe}} in the prompt.",
        fr: "Au décroché, l'agent reçoit {{equipe}} : une ligne par personne active de l'établissement appelé et de toute l'entreprise, avec son poste et ce dont elle s'occupe. Placez {{equipe}} dans le prompt.",
    },
    {
        en: "A phone number or an e-mail appears only for a person whose disclosure is allowed (theme « Team and routing » of the organization).",
        fr: "Un téléphone ou un e-mail n'apparaît que pour une personne dont la divulgation est autorisée (thème « Équipe et routage » de l'organisation).",
    },
    {
        en: "The summary after the call also receives the names, to spell them right. Needs a client database: without one, the agent knows no one.",
        fr: "La synthèse d'après l'appel reçoit aussi les noms, pour les écrire correctement. Demande une base du client : sans elle, l'agent ne connaît personne.",
    },
    {
        // cloture-code, F8 (M4): what the call now does with the switch off.
        en: "Off: the tool « direct to a person » (connector « Team » in Tools) is not offered to the model.",
        fr: "Éteint : l'outil « diriger vers une personne » (connecteur « Équipe » dans Outils) n'est pas proposé au modèle.",
    },
];

// Chantier l-agent-collegue, L6 (V1, V7): what the switch lets the agent do (moved from « Call data »).
export const AIDES_VERIFICATION_APPELANT: Texte[] = [
    {
        en: "Lets the tools « verify the caller » and « read the record » (connector « Record » in Tools) run for this agent. The code checks the caller with the factors of the organization (theme « Caller verification »); the agent receives a record only after that.",
        fr: "Laisse les outils « vérifier l'appelant » et « lire le dossier » (connecteur « Dossier » dans Outils) tourner pour cet agent. Le code vérifie l'appelant avec les facteurs de l'organisation (thème « Vérification de l'appelant ») ; l'agent ne reçoit un dossier qu'après.",
    },
    {
        // cloture-code, F8 (M4): before, the tools were offered and answered « unavailable ».
        en: "Off: the two tools are not offered to the model, nothing of a record is ever read. To switch on at a client only after the legal check.",
        fr: "Éteint : les deux outils ne sont pas proposés au modèle, rien d'un dossier n'est jamais lu. À allumer chez un client seulement après la vérification juridique.",
    },
];

const SPECIAUX: Record<string, { libelle: Texte; aides: Texte[] }> = {
    equipe_connue: { libelle: { en: "Team known to the agent", fr: "Équipe connue de l'agent" }, aides: AIDES_EQUIPE_CONNUE },
    verification_appelant: { libelle: { en: "Caller verification", fr: "Vérification de l'appelant" }, aides: AIDES_VERIFICATION_APPELANT },
};

const CLES_DU_CATALOGUE = CLES_MODULES.filter((cle) => cle in CATALOGUE) as CleCatalogue[];
const extraireModules = (resolue: ProprietesThemeAgent["resolue"]) => extraire(resolue, CLES_DU_CATALOGUE);

export const ThemeModules = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    workflowId,
}: ProprietesThemeAgent & { workflowId: number }) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireModules);
    const revelation = useRevelation(ouvrir);
    const [ouverts, setOuverts] = useState<Set<string>>(() => new Set());
    const basculer = (code: string) =>
        setOuverts((avant) => {
            const apres = new Set(avant);
            if (apres.has(code)) apres.delete(code);
            else apres.add(code);
            return apres;
        });
    // E7: « show » opens the theme AND the sub-menu that holds the setting.
    const afficher = (cle: string) => {
        const porteur = moduleDeLaCle(cle);
        if (porteur) setOuverts((avant) => new Set(avant).add(porteur.code));
        revelation.afficher(cle);
    };

    // The two switches that came from « Call data », each sent only when changed (as there, E6).
    const equipeEnregistree = resolue.equipe_connue ?? false;
    const [equipe, setEquipe] = useState(equipeEnregistree);
    useEffect(() => setEquipe(equipeEnregistree), [equipeEnregistree]);
    const verificationEnregistree = resolue.verification_appelant ?? false;
    const [verification, setVerification] = useState(verificationEnregistree);
    useEffect(() => setVerification(verificationEnregistree), [verificationEnregistree]);
    const speciaux: Record<string, [boolean, (v: boolean) => void]> = {
        equipe_connue: [equipe, setEquipe],
        verification_appelant: [verification, setVerification],
    };

    // What depends on the organization: the translators, a module switched on by its tools.
    const [duServeur, setDuServeur] = useState<ModuleDeLAgent[]>([]);
    useEffect(() => {
        let annule = false;
        (async () => {
            try {
                const reponse = await getModulesDeLAgentApiV1AgentsAgentIdModulesGet({ path: { agent_id: workflowId } });
                if (!annule && reponse.data) setDuServeur(reponse.data.modules);
            } catch {
                // The settings do not depend on it: only the « plugs into » lines are missing.
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId]);

    const reglagesModifies = differe(brouillon, enregistre);
    const equipeModifiee = equipe !== equipeEnregistree;
    const verificationModifiee = verification !== verificationEnregistree;
    const modifie = reglagesModifies || equipeModifiee || verificationModifiee;
    const erreurs = erreursDuCatalogue(
        ["variables_commune", "variables_reference", "variables_telephone", "variables_code_postal", "variables_courriel", "variables_date"],
        brouillon,
    );
    useEtatTheme(ID_THEME_MODULES, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_MODULES,
        resolue,
        workflowName,
        onSave,
        parties: [
            { nom: { en: "Module settings", fr: "Réglages des modules" }, modifie: reglagesModifies, config: () => brouillon, apres: resynchroniser },
            { nom: SPECIAUX.equipe_connue.libelle, modifie: equipeModifiee, config: () => ({ equipe_connue: equipe }) },
            { nom: SPECIAUX.verification_appelant.libelle, modifie: verificationModifiee, config: () => ({ verification_appelant: verification }) },
        ],
    });

    const valeur = (cle: string): unknown => (cle in speciaux ? speciaux[cle][0] : (brouillon as Record<string, unknown>)[cle]);
    const champ = (cle: string, condition = true) => {
        if (cle in speciaux) {
            const [coche, poser] = speciaux[cle];
            return (
                <ChampReglage
                    key={cle}
                    cle={cle}
                    idControle={cle}
                    libelle={SPECIAUX[cle].libelle}
                    aides={SPECIAUX[cle].aides}
                    bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                    disposition="ligne"
                >
                    <Switch id={cle} checked={coche} onCheckedChange={poser} />
                </ChampReglage>
            );
        }
        const { affiche, note } = revelation.visible(cle, condition);
        return affiche ? (
            <Reglage
                key={cle}
                cle={cle as CleCatalogue}
                valeur={valeur(cle)}
                onChange={(v) => setBrouillon((avant) => ({ ...avant, [cle]: v }))}
                note={note}
            />
        ) : null;
    };

    const allumes = MODULES_AGENT.filter((m) =>
        m.interrupteur ? Boolean(valeur(m.interrupteur)) : Boolean(duServeur.find((s) => s.code === m.code)?.actif),
    );

    return (
        <Theme
            id={ID_THEME_MODULES}
            icone={Puzzle}
            titre={TITRE_MODULES}
            description={{
                en: "The agent's modules: each one switched on or off, its own settings, and what it plugs into.",
                fr: "Les modules de l'agent : chacun allumé ou coupé, ses réglages propres, et ce sur quoi il se branche.",
            }}
            resume={[`${allumes.length} / ${MODULES_AGENT.length} ${t({ en: "on", fr: "allumés" })}`]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <div className="space-y-3">
                <GroupeModuleRestauration module={duServeur.find((s) => s.code === "restauration")} />
                {MODULES_AGENT.map((module) => {
                    const serveur = duServeur.find((s) => s.code === module.code);
                    const allume = module.interrupteur ? Boolean(valeur(module.interrupteur)) : serveur ? serveur.actif ?? false : null;
                    return (
                        <SousMenuModule
                            key={module.code}
                            module={module}
                            allume={allume}
                            ouvert={ouverts.has(module.code)}
                            onBasculer={() => basculer(module.code)}
                        >
                            {module.interrupteur ? (
                                champ(module.interrupteur)
                            ) : (
                                <p className="text-xs text-muted-foreground" data-allume-par-ses-outils={module.code}>
                                    {t({
                                        en: "Switched on by its tools: on as soon as a published step carries one of them (Tools, connector « Planner »). Its settings: organization settings, theme « Appointments ».",
                                        fr: "Allumé par ses outils : dès qu'une étape publiée en porte un (Outils, connecteur « Planificateur »). Ses réglages : paramètres de l'organisation, thème « Rendez-vous ».",
                                    })}
                                </p>
                            )}
                            {module.reglages.map((cle) => champ(cle, Boolean(module.interrupteur && valeur(module.interrupteur))))}
                            <Besoins module={serveur} />
                        </SousMenuModule>
                    );
                })}
            </div>
        </Theme>
    );
};
