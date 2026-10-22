"use client";

/**
 * [.mark] Theme « Écoute »: what happens to the caller's words before the
 * model reads them (convention § 2). From Dograh's Dictionary card: the words
 * this agent listens for, saved by the dictionary's own function; from the
 * Speech Tuning card: the input noise filter.
 *
 * cloture-code, F8 (M4): numbers, town and street, spelling, the trade
 * vocabulary switch and field recognition MOVED to the theme « Modules »
 * (`ThemeModules.tsx`), one sub-menu each; they are no longer drawn here.
 */
import { Ear } from "lucide-react";
import { useState } from "react";

import { Textarea } from "@/components/ui/textarea";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, type ProprietesThemeAgent, useBrouillon, useEtatTheme } from "./theme-commun";

export const ID_THEME_ECOUTE = "ecoute";

export const CLES_ECOUTE = ["audio_in_noise_filter"] as const;

const extraireEcoute = (resolue: ProprietesThemeAgent["resolue"]) => extraire(resolue, CLES_ECOUTE);

export const TITRE_ECOUTE = { en: "Listening", fr: "Écoute" };

export const ThemeEcoute = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    dictionnaire,
    enregistrerDictionnaire,
}: ProprietesThemeAgent & { dictionnaire: string; enregistrerDictionnaire: (dictionnaire: string) => Promise<void> }) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireEcoute);
    const [dico, setDico] = useState(dictionnaire);

    const maj = (cle: (typeof CLES_ECOUTE)[number]) => (valeur: unknown) =>
        setBrouillon((avant) => ({ ...avant, [cle]: valeur }));

    const reglagesModifies = differe(brouillon, enregistre);
    const dicoModifie = dico !== dictionnaire;
    const modifie = reglagesModifies || dicoModifie;

    useEtatTheme(ID_THEME_ECOUTE, modifie, false);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_ECOUTE,
        resolue,
        workflowName,
        onSave,
        parties: [
            {
                nom: { en: "Listening settings", fr: "Réglages d'écoute" },
                modifie: reglagesModifies,
                config: () => brouillon,
                apres: resynchroniser,
            },
            {
                nom: { en: "Dictionary", fr: "Dictionnaire" },
                modifie: dicoModifie,
                enregistrerAutrement: () => enregistrerDictionnaire(dico),
            },
        ],
    });

    return (
        <Theme
            id={ID_THEME_ECOUTE}
            icone={Ear}
            titre={TITRE_ECOUTE}
            description={{
                en: "What happens to the caller's words before the model reads them.",
                fr: "Ce qui arrive aux mots de l'appelant avant que le modèle ne les lise.",
            }}
            resume={[
                dictionnaire.trim() ? t({ en: "Dictionary set", fr: "Dictionnaire rempli" }) : t({ en: "No dictionary", fr: "Aucun dictionnaire" }),
                brouillon.audio_in_noise_filter === "rnnoise" && t({ en: "Noise filter", fr: "Filtre de bruit" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={[]}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="ecoute-dictionnaire" titre={{ en: "Agent dictionary", fr: "Dictionnaire de l'agent" }}>
                <ChampReglage
                    cle="dictionary"
                    idControle="dictionary"
                    libelle={{ en: "Dictionary", fr: "Mots à écouter, propres à cet agent" }}
                    aides={[
                        {
                            en: "Add words the agent should actively listen for — company jargon, names, industry terms. May incur extra cost depending on provider.",
                            fr: "Mots que l'agent doit écouter en priorité : jargon, noms, termes du métier. Peut coûter plus cher selon le fournisseur.",
                        },
                    ]}
                >
                    <Textarea
                        id="dictionary"
                        placeholder={t({
                            en: "Enter words separated by comma (e.g. billing department, tretinoin)",
                            fr: "Mots séparés par des virgules (ex. service facturation, trétinoïne)",
                        })}
                        value={dico}
                        onChange={(e) => setDico(e.target.value)}
                        rows={4}
                        className="resize-none"
                    />
                </ChampReglage>
            </Intertitre>
            <Intertitre id="ecoute-bruit" titre={{ en: "Input noise", fr: "Bruit à l'entrée" }}>
                <Reglage cle="audio_in_noise_filter" valeur={brouillon.audio_in_noise_filter} onChange={maj("audio_in_noise_filter")} />
            </Intertitre>
        </Theme>
    );
};
