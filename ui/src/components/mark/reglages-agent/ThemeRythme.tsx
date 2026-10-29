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
import { MOTIF_SILENCE } from "./phrases/modele";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_RYTHME = "rythme";
export const TITRE_RYTHME = { en: "Call pacing", fr: "Rythme de l'appel" };

export const CLES_RYTHME_MARK = [
    "user_idle_prompt",
    "user_idle_max_prompts",
    "user_idle_goodbye_prompt",
    "raccrochage_silence_agent_s",
    "laisser_la_parole",
] as const satisfies readonly CleCatalogue[];

const extraireTout = (resolue: ProprietesThemeAgent["resolue"]) => ({
    max_user_idle_timeout: resolue.max_user_idle_timeout,
    max_call_duration: resolue.max_call_duration,
    ...extraire(resolue, CLES_RYTHME_MARK),
});

export const ThemeRythme = ({ resolue, workflowName, onSave, ouvert, onBasculer, ouvrir, versTheme }: ProprietesThemeAgent) => {
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

    // [.mark] correctifs-apres-banc-v4, lot 5 (décision 1): the number of prompts and the goodbye are read from the rule
    // « The caller is silent » when it sets them (one place); otherwise from here, as before. Nothing disappears.
    const regleDuSilence = (resolue.phrases_regles ?? []).find(
        (r) => r.motif === MOTIF_SILENCE && r.portee !== "etape" && r.active !== false,
    );
    const silencePoseLesRelances = regleDuSilence?.max_par_attente != null;
    const silencePoseLAuRevoir = Boolean(regleDuSilence && ((regleDuSilence.ensuite?.phrases?.length ?? 0) > 0 || regleDuSilence.ensuite?.action));
    const lienSilence = (pose: boolean, valeur: string) => (
        <p className="text-xs text-muted-foreground" data-note="rythme-lien-silence" data-pose={pose ? "oui" : "non"}>
            {pose
                ? t({
                      en: `No effect here: the rule « The caller is silent » of the Phrases theme sets it (${valeur}).`,
                      fr: `Sans effet ici : la règle « L'appelant se tait » du thème Phrases le règle (${valeur}).`,
                  })
                : t({
                      en: "Used while the rule « The caller is silent » of the Phrases theme does not set its own.",
                      fr: "Utilisé tant que la règle « L'appelant se tait » du thème Phrases ne pose pas la sienne.",
                  })}{" "}
            {versTheme && (
                <button type="button" className="underline" onClick={() => versTheme("phrases")}>
                    {t({ en: "Open the Phrases theme", fr: "Ouvrir le thème Phrases" })}
                </button>
            )}
        </p>
    );

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
                    en: "What the agent does when the caller goes quiet, past the idle timeout. The reminder is a fixed sentence said by the voice, set in the Phrases theme (cause « The caller is silent »), and its delay there replaces the one below when it is set. If that sentence is switched off, the instructions below are given to the model instead (⚠️ instructions, not sentences said word for word: the model answers in the caller's language). The last one, before hanging up, is always an instruction.",
                    fr: "Ce que fait l'agent quand l'appelant se tait, passé le délai ci-dessous. La relance est une phrase fixe dite par la voix, qui se règle dans le thème Phrases (motif « L'appelant se tait »), et son délai y remplace celui-ci quand il est réglé. Si cette phrase est éteinte, les consignes ci-dessous sont données au modèle à la place (⚠️ des consignes, pas des phrases dites mot pour mot : le modèle répond dans la langue de l'appelant). La dernière, avant de raccrocher, reste toujours une consigne.",
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
                {lienSilence(silencePoseLesRelances, String(regleDuSilence?.max_par_attente ?? ""))}
                <Reglage cle="user_idle_goodbye_prompt" valeur={brouillon.user_idle_goodbye_prompt} onChange={maj("user_idle_goodbye_prompt")} />
                {lienSilence(silencePoseLAuRevoir, regleDuSilence?.ensuite?.phrases?.[0] ?? regleDuSilence?.ensuite?.action ?? "")}
                <Reglage cle="laisser_la_parole" valeur={brouillon.laisser_la_parole} onChange={maj("laisser_la_parole")} />
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
