"use client";

/**
 * [.mark] Theme « Rythme de l'appel »: the caller's silences, the idle
 * prompts, hanging up, the length of a call (convention § 2). Dograh's « Call
 * Management » (General, rebuilt, D6 option B) and our idle prompts and
 * silent-agent hang-up (Speech Tuning), which were two cards for one subject.
 */
import { Clock } from "lucide-react";

import { Input } from "@/components/ui/input";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { type CleCatalogue, erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_RYTHME = "rythme";
export const TITRE_RYTHME = { en: "Call pacing", fr: "Rythme de l'appel" };

export const CLES_RYTHME_MARK = [
    "user_idle_prompt",
    "user_idle_max_prompts",
    "user_idle_goodbye_prompt",
    "raccrochage_silence_agent_s",
] as const satisfies readonly CleCatalogue[];

const extraireTout = (resolue: ProprietesThemeAgent["resolue"]) => ({
    max_user_idle_timeout: resolue.max_user_idle_timeout,
    max_call_duration: resolue.max_call_duration,
    ...extraire(resolue, CLES_RYTHME_MARK),
});

export const ThemeRythme = ({ resolue, workflowName, onSave, ouvert, onBasculer, ouvrir }: ProprietesThemeAgent) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireTout);
    const { afficher } = useRevelation(ouvrir);
    const maj = (cle: keyof typeof brouillon) => (valeur: unknown) => setBrouillon((avant) => ({ ...avant, [cle]: valeur }));

    const modifie = differe(brouillon, enregistre);
    const erreurs = erreursDuCatalogue(CLES_RYTHME_MARK, brouillon);
    useEtatTheme(ID_THEME_RYTHME, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_RYTHME,
        resolue,
        workflowName,
        onSave,
        parties: [{ nom: { en: "Call pacing settings", fr: "Réglages du rythme de l'appel" }, modifie, config: () => brouillon, apres: resynchroniser }],
    });

    const entierPositif = (cle: "max_user_idle_timeout" | "max_call_duration") => (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = parseInt(e.target.value);
        if (!isNaN(value) && value > 0) maj(cle)(value);
    };

    return (
        <Theme
            id={ID_THEME_RYTHME}
            icone={Clock}
            titre={TITRE_RYTHME}
            description={{ en: "Caller silences, idle prompts, hang-up and duration.", fr: "Silences de l'appelant, relances, raccrochage et durée." }}
            resume={[
                `${t({ en: "Prompt after", fr: "Relance après" })} ${brouillon.max_user_idle_timeout} s`,
                `${brouillon.user_idle_max_prompts} ${t({ en: "prompt(s)", fr: "relance(s)" })}`,
                `${t({ en: "Max duration", fr: "Durée max" })} ${Math.round(brouillon.max_call_duration / 60)} min`,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre
                id="rythme-silence"
                titre={{ en: "Caller silence", fr: "Silence de l'appelant" }}
                description={{
                    en: "What the agent does when the caller goes quiet, past the idle timeout. ⚠️ These are instructions given to the model, not sentences spoken word for word: the model answers in the caller's language.",
                    fr: "Ce que fait l'agent quand l'appelant se tait, passé le délai ci-dessous. ⚠️ Les textes sont des consignes données au modèle, pas des phrases dites mot pour mot : le modèle répond dans la langue de l'appelant.",
                }}
            >
                <ChampReglage
                    cle="max_user_idle_timeout"
                    idControle="max_user_idle_timeout"
                    libelle={{ en: "Max User Idle Timeout (seconds)", fr: "Silence avant de relancer (secondes)" }}
                    aides={[{ en: "Default: 10 seconds", fr: "Défaut : 10 secondes." }]}
                    bornes={bornesDe(1)}
                >
                    <Input
                        id="max_user_idle_timeout"
                        type="number"
                        min="1"
                        value={brouillon.max_user_idle_timeout}
                        onChange={entierPositif("max_user_idle_timeout")}
                    />
                </ChampReglage>
                <Reglage cle="user_idle_prompt" valeur={brouillon.user_idle_prompt} onChange={maj("user_idle_prompt")} />
                <Reglage cle="user_idle_max_prompts" valeur={brouillon.user_idle_max_prompts} onChange={maj("user_idle_max_prompts")} />
                <Reglage cle="user_idle_goodbye_prompt" valeur={brouillon.user_idle_goodbye_prompt} onChange={maj("user_idle_goodbye_prompt")} />
            </Intertitre>

            <Intertitre id="rythme-fin" titre={{ en: "End of call", fr: "Fin d'appel" }}>
                <Reglage cle="raccrochage_silence_agent_s" valeur={brouillon.raccrochage_silence_agent_s} onChange={maj("raccrochage_silence_agent_s")} />
                <ChampReglage
                    cle="max_call_duration"
                    idControle="max_call_duration"
                    libelle={{ en: "Max Call Duration (seconds)", fr: "Durée maximale de l'appel (secondes)" }}
                    aides={[{ en: "Default: 600 (10 minutes)", fr: "Défaut : 600 (10 minutes)." }]}
                    bornes={bornesDe(1)}
                >
                    <Input
                        id="max_call_duration"
                        type="number"
                        min="1"
                        value={brouillon.max_call_duration}
                        onChange={entierPositif("max_call_duration")}
                    />
                </ChampReglage>
            </Intertitre>
        </Theme>
    );
};
