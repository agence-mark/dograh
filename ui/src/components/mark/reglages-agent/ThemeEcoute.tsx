"use client";

/**
 * [.mark] Theme « Écoute »: what happens to the caller's words before the
 * model reads them (convention § 2). From the Speech Tuning card: numbers,
 * towns and streets, spelling, the trade vocabulary switch, the input noise
 * filter. From Dograh's Dictionary card: the words this agent listens for,
 * saved by the dictionary's own function.
 */
import { Ear } from "lucide-react";
import { useState } from "react";

import { Textarea } from "@/components/ui/textarea";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_ECOUTE = "ecoute";

export const CLES_ECOUTE = [
    "conversion_nombres_transcription",
    "variables_reference",
    "verification_communes",
    "variables_commune",
    "sons_communes",
    "verification_voies",
    "lecture_epellation",
    "lexique_metier",
    "sons_lexique",
    "audio_in_noise_filter",
] as const;

const extraireEcoute = (resolue: ProprietesThemeAgent["resolue"]) => extraire(resolue, CLES_ECOUTE);

export const TITRE_ECOUTE = { en: "Listening", fr: "Écoute" };

export const ThemeEcoute = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    ouvrir,
    dictionnaire,
    enregistrerDictionnaire,
}: ProprietesThemeAgent & { dictionnaire: string; enregistrerDictionnaire: (dictionnaire: string) => Promise<void> }) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireEcoute);
    const [dico, setDico] = useState(dictionnaire);
    const { afficher, visible } = useRevelation(ouvrir);

    const maj = (cle: (typeof CLES_ECOUTE)[number]) => (valeur: unknown) =>
        setBrouillon((avant) => ({ ...avant, [cle]: valeur }));

    const reglagesModifies = differe(brouillon, enregistre);
    const dicoModifie = dico !== dictionnaire;
    const modifie = reglagesModifies || dicoModifie;

    const erreurs = erreursDuCatalogue(["variables_commune", "variables_reference"], brouillon);

    useEtatTheme(ID_THEME_ECOUTE, modifie, erreurs.length > 0);

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

    const r = (cle: (typeof CLES_ECOUTE)[number], condition = true) => {
        const { affiche, note } = visible(cle, condition);
        return affiche ? <Reglage key={cle} cle={cle} valeur={brouillon[cle]} onChange={maj(cle)} note={note} /> : null;
    };

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
                brouillon.verification_communes ? t({ en: "Towns recognised", fr: "Communes reconnues" }) : t({ en: "Towns off", fr: "Communes éteintes" }),
                Boolean(brouillon.lecture_epellation) && t({ en: "Spelling read", fr: "Épellation lue" }),
                brouillon.lexique_metier ? t({ en: "Vocabulary on", fr: "Lexique actif" }) : t({ en: "Vocabulary off", fr: "Lexique éteint" }),
                Boolean(brouillon.conversion_nombres_transcription) && t({ en: "Numbers as digits", fr: "Nombres en chiffres" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="ecoute-nombres" titre={{ en: "Numbers and references", fr: "Nombres et références" }}>
                {r("conversion_nombres_transcription")}
                {r("variables_reference", Boolean(brouillon.conversion_nombres_transcription))}
            </Intertitre>
            <Intertitre id="ecoute-communes" titre={{ en: "Town and street", fr: "Commune et rue" }}>
                {r("verification_communes")}
                {r("variables_commune", Boolean(brouillon.verification_communes))}
                {r("sons_communes", Boolean(brouillon.verification_communes))}
                {r("verification_voies", Boolean(brouillon.verification_communes))}
            </Intertitre>
            <Intertitre id="ecoute-epellation" titre={{ en: "Spelling", fr: "Épellation" }}>
                {r("lecture_epellation")}
            </Intertitre>
            <Intertitre id="ecoute-lexique" titre={{ en: "Trade vocabulary", fr: "Lexique métier" }}>
                {r("lexique_metier")}
                {r("sons_lexique", Boolean(brouillon.lexique_metier))}
            </Intertitre>
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
                {r("audio_in_noise_filter")}
            </Intertitre>
        </Theme>
    );
};
