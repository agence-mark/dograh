"use client";

/**
 * [.mark] Theme « Engine interventions »: what OUR code does in the conversation (lot 8 of builder-agent-vocal).
 *
 * It gathers, in one place, the switches of the interventions that change the request sent to the conversation
 * model, read or rewrite its answer, decide or speak in its place. The ten new switches are ON by default (an agent
 * without the key behaves exactly as before); two older settings moved in (« Let the caller take their time » from
 * Call pacing, « Always reply after a tool » from Turn taking): one setting, one place (convention § 1).
 *
 * Why it exists: the « bare engine against complete engine » bench compares an agent with and without each
 * intervention, to keep what improves it and switch off what harms it.
 *
 * ⚠️ The settings that need a whole block of their own screen (the call record and its note-taking mode, the
 * background brain, the sentence rules) stay in their theme; the last section points to them.
 */
import { Cog } from "lucide-react";

import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { type CleCatalogue, erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_INTERVENTIONS = "interventions";
export const TITRE_INTERVENTIONS = { en: "Engine interventions", fr: "Interventions du moteur" };

/** The new switches (on by default) and the two settings moved in, in screen order. */
export const CLES_INTERVENTIONS_MARK = [
    "moteur_sorties_de_l_etape",
    "moteur_notes_de_passation",
    "moteur_sortie_d_impasse",
    "laisser_la_parole",
    "moteur_parole_avant_outil",
    "moteur_main_passee",
    "relance_apres_outil",
    "moteur_ordre_outil_puis_parole",
    "moteur_compte_rendu_de_phrase",
    "moteur_phrases_coupees",
    "moteur_replique_inachevee",
    "moteur_reponse_muette",
] as const satisfies readonly CleCatalogue[];

const extraireTout = (resolue: ProprietesThemeAgent["resolue"]) => extraire(resolue, CLES_INTERVENTIONS_MARK);

export const ThemeInterventions = ({ resolue, workflowName, onSave, ouvert, onBasculer, ouvrir, versTheme }: ProprietesThemeAgent) => {
    const { t } = useLangue();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireTout);
    const { afficher } = useRevelation(ouvrir);
    const maj = (cle: keyof typeof brouillon) => (valeur: unknown) => setBrouillon((avant) => ({ ...avant, [cle]: valeur }));

    const modifie = differe(brouillon, enregistre);
    const erreurs = erreursDuCatalogue(CLES_INTERVENTIONS_MARK, brouillon);
    useEtatTheme(ID_THEME_INTERVENTIONS, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_INTERVENTIONS,
        resolue,
        workflowName,
        onSave,
        parties: [{ nom: { en: "Engine interventions settings", fr: "Réglages des interventions du moteur" }, modifie, config: () => brouillon, apres: resynchroniser }],
    });

    const reglage = (cle: (typeof CLES_INTERVENTIONS_MARK)[number]) => (
        <Reglage cle={cle} valeur={brouillon[cle]} onChange={maj(cle)} />
    );
    const eteintes = CLES_INTERVENTIONS_MARK.filter((cle) => cle.startsWith("moteur_") && brouillon[cle] === false).length;

    const lien = (theme: string, titre: { en: string; fr: string }) =>
        versTheme ? (
            <button type="button" className="underline" onClick={() => versTheme(theme)}>
                {t(titre)}
            </button>
        ) : (
            t(titre)
        );

    return (
        <Theme
            id={ID_THEME_INTERVENTIONS}
            icone={Cog}
            titre={TITRE_INTERVENTIONS}
            description={{
                en: "What our code does in the conversation, switch by switch. All on by default: nothing changes until you switch one off.",
                fr: "Ce que notre code fait dans la conversation, interrupteur par interrupteur. Tout est allumé par défaut : rien ne change tant que vous n'en éteignez pas un.",
            }}
            resume={[
                eteintes === 0
                    ? t({ en: "All interventions on", fr: "Toutes les interventions allumées" })
                    : `${eteintes} ${t({ en: "switched off", fr: "éteinte(s)" })}`,
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre
                id="interventions-parcours"
                titre={{ en: "Steps and handovers", fr: "Étapes et passations" }}
                description={{
                    en: "Lines and notes the code writes into the prompt to guide the model from one step or agent to the next.",
                    fr: "Lignes et notes que le code écrit dans le prompt pour guider le modèle d'une étape ou d'un agent à l'autre.",
                }}
            >
                {reglage("moteur_sorties_de_l_etape")}
                {reglage("moteur_notes_de_passation")}
            </Intertitre>

            <Intertitre
                id="interventions-conduite"
                titre={{ en: "Conduct guards", fr: "Garde-fous de conduite" }}
                description={{
                    en: "What the code decides or holds back while the model talks.",
                    fr: "Ce que le code décide ou retient pendant que le modèle parle.",
                }}
            >
                {reglage("moteur_sortie_d_impasse")}
                {reglage("laisser_la_parole")}
                {reglage("moteur_parole_avant_outil")}
                {reglage("moteur_main_passee")}
                {reglage("relance_apres_outil")}
                {reglage("moteur_ordre_outil_puis_parole")}
            </Intertitre>

            <Intertitre
                id="interventions-phrases"
                titre={{ en: "Sentences and rewrites", fr: "Phrases et réécritures" }}
                description={{
                    en: "What the code says in the model's place, and what it rewrites in the model's reply or in the request.",
                    fr: "Ce que le code dit à la place du modèle, et ce qu'il réécrit dans sa réponse ou dans la requête.",
                }}
            >
                {reglage("moteur_compte_rendu_de_phrase")}
                {reglage("moteur_phrases_coupees")}
                {reglage("moteur_replique_inachevee")}
                {reglage("moteur_reponse_muette")}
            </Intertitre>

            <Intertitre id="interventions-ailleurs" titre={{ en: "Set elsewhere", fr: "Réglé ailleurs" }}>
                <p className="text-xs text-muted-foreground" data-note="interventions-ailleurs">
                    {t({
                        en: "The other interventions have a block of their own and stay in their theme: ",
                        fr: "Les autres interventions ont un bloc à elles et restent dans leur thème : ",
                    })}
                    {lien("donnees", { en: "Call data", fr: "Données de l'appel" })}
                    {t({
                        en: " (call record, note-taking mode, transitions in the reply, module hints, known and expected, record in the system instruction, guaranteed transfer, redundant question), ",
                        fr: " (fiche, mode de prise de notes, portes dans la réponse, indices des modules, connu et attendu, fiche dans l'instruction système, transfert garanti, question redemandée), ",
                    })}
                    {lien("briques", { en: "Services", fr: "Briques" })}
                    {t({ en: " (background brain), ", fr: " (cerveau de fond), " })}
                    {lien("phrases", { en: "Phrases", fr: "Phrases" })}
                    {t({ en: " (the sentences said by the code), ", fr: " (les phrases dites par le code), " })}
                    {lien("agent", { en: "Agent", fr: "Agent" })}
                    {t({
                        en: " (flow map, safety net for a colleague, unfinished-reply effort). The arbiter, the switch on the record and the triggering of the action are set on each step.",
                        fr: " (schéma du parcours, filet de fin d'un collègue, réflexion de la relance). L'arbitre, le passage sur la fiche et le déclenchement de l'action se règlent sur chaque étape.",
                    })}
                </p>
            </Intertitre>
        </Theme>
    );
};
