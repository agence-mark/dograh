"use client";

/**
 * [.mark] The outage fallback of THIS agent (chantier l-agent-travaille, L7; PN1 to PN8), in the
 * theme « Establishment ». Off by default (X2): an agent that switches nothing on is not touched.
 *
 * On: when a part of the agent fails (voice, transcription, model), Twilio speaks with its own
 * voice and hands the call to the establishment's second number if it is open, else promises a
 * call-back with the reopening date; a request « to call back » is written and an alert sent.
 * The sentences are fiches of the catalogue of sentences; the emergency address (TwiML Bin) is
 * the organization's (Platform Settings, « Integrations »).
 */
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { PanneAgent } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import type { Texte } from "../langue/langue";

export const PANNE_ETEINTE: PanneAgent = { actif: false, delai_modele_s: 4, delai_voix_s: 3, sonnerie_s: 20 };

export const BORNES_PANNE: Record<"delai_modele_s" | "delai_voix_s" | "sonnerie_s", [number, number]> = {
    delai_modele_s: [0.1, 30],
    delai_voix_s: [0.5, 30],
    sonnerie_s: [5, 60],
};

export const lirePanne = (brut: Partial<PanneAgent> | null | undefined): PanneAgent => ({ ...PANNE_ETEINTE, ...(brut ?? {}) });

export const erreursPanne = (valeur: PanneAgent): Texte[] =>
    valeur.actif
        ? (Object.keys(BORNES_PANNE) as Array<keyof typeof BORNES_PANNE>)
              .filter((cle) => !(valeur[cle] >= BORNES_PANNE[cle][0] && valeur[cle] <= BORNES_PANNE[cle][1]))
              .map((cle) => ({
                  en: `${cle}: between ${BORNES_PANNE[cle][0]} and ${BORNES_PANNE[cle][1]}.`,
                  fr: `${cle} : entre ${BORNES_PANNE[cle][0]} et ${BORNES_PANNE[cle][1]}.`,
              }))
        : [];

export function SectionPanneAgent({ valeur, onChange }: { valeur: PanneAgent; onChange: (valeur: PanneAgent) => void }) {
    const nombre = (cle: keyof typeof BORNES_PANNE, libelle: Texte, aide: Texte, unite: Texte) => (
        <ChampReglage
            cle={`panne.${cle}`}
            idControle={`panne_${cle}`}
            libelle={libelle}
            aides={[aide]}
            bornes={{
                en: `${BORNES_PANNE[cle][0]} to ${BORNES_PANNE[cle][1]} ${unite.en} · default ${PANNE_ETEINTE[cle]}`,
                fr: `${BORNES_PANNE[cle][0]} à ${BORNES_PANNE[cle][1]} ${unite.fr} · défaut ${PANNE_ETEINTE[cle]}`,
            }}
        >
            <Input
                id={`panne_${cle}`}
                type="number"
                step={cle === "sonnerie_s" ? 1 : 0.1}
                value={String(valeur[cle])}
                onChange={(e) => onChange({ ...valeur, [cle]: Number(e.target.value) })}
            />
        </ChampReglage>
    );
    return (
        <>
            <ChampReglage
                cle="panne"
                idControle="panne_actif"
                libelle={{ en: "Hand the call over when the agent fails", fr: "Passer l'appel quand l'agent tombe en panne" }}
                aides={[
                    {
                        en: "When the voice, the transcription or the model fails, Twilio says the hand-over sentence with its own voice and rings the establishment's second number if it is open; closed or no answer, it promises a call-back with the reopening date and hangs up. Always: a request « to call back » in the client's database and an alert to the notification addresses. Outbound calls: an apology, then hang up. Twilio calls only.",
                        fr: "Quand la voix, la transcription ou le modèle tombe, Twilio dit la phrase de renvoi avec sa propre voix et fait sonner le second numéro de l'établissement s'il est ouvert ; fermé ou sans réponse, il promet un rappel avec la date de réouverture et raccroche. Toujours : une demande « à rappeler » dans la base du client et une alerte aux adresses de notification. Appels sortants : une excuse, puis raccroché. Appels Twilio seulement.",
                    },
                    {
                        en: "The sentences are fiches of the catalogue of sentences (phrase_renvoi_panne, phrase_rappel_panne, phrase_excuse_panne); the emergency address used when our server is down is the organization's (« Integrations »).",
                        fr: "Les phrases sont des fiches du catalogue de phrases (phrase_renvoi_panne, phrase_rappel_panne, phrase_excuse_panne) ; l'adresse de secours, utilisée quand notre serveur est tombé, est celle de l'organisation (« Intégrations »).",
                    },
                ]}
                bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                disposition="ligne"
            >
                <Switch id="panne_actif" checked={valeur.actif} onCheckedChange={(actif) => onChange({ ...valeur, actif })} />
            </ChampReglage>
            {valeur.actif && (
                <div className="grid gap-3 sm:grid-cols-3">
                    {nombre(
                        "delai_modele_s",
                        { en: "Model answer delay", fr: "Délai de réponse du modèle" },
                        { en: "Past it, « Un instant, s'il vous plaît » and a new try; the second time in a row, the hand-over.", fr: "Au-delà, « Un instant, s'il vous plaît » et un nouvel essai ; la seconde fois de suite, le renvoi." },
                        { en: "s", fr: "s" },
                    )}
                    {nombre(
                        "delai_voix_s",
                        { en: "Voice delay", fr: "Délai de la voix" },
                        { en: "Past it between the text sent to the voice and its first sound, the hand-over.", fr: "Au-delà entre le texte envoyé à la voix et son premier son, le renvoi." },
                        { en: "s", fr: "s" },
                    )}
                    {nombre(
                        "sonnerie_s",
                        { en: "Ringing of the second number", fr: "Sonnerie du second numéro" },
                        { en: "Then the call-back promise.", fr: "Ensuite, la promesse de rappel." },
                        { en: "s", fr: "s" },
                    )}
                </div>
            )}
        </>
    );
}
