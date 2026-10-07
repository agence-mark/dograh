"use client";

/**
 * [.mark] What THIS agent does after the call (chantier l-agent-travaille, L4, A6), in the
 * theme « Call data ». Off by default (X2): an agent that switches nothing on is not touched.
 *
 * On: each call is written in the client's database, then (each switchable) summarised and its
 * request mailed; the organization's modules this agent uses run after them. The settings
 * themselves (summary key, mail server, webhook address) are the organization's, in « After the
 * call » of the Platform Settings. Which record field holds the name, the reason, the urgency…
 * is set here: empty, the field of the same name.
 *
 * Shown only when on: the server reads the steps and the fields only when on (E8, same rule).
 */
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { ApresAppelAgent, SmsAgent } from "@/types/workflow-configurations";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";
import { BoutonSms, erreursSms, SMS_ETEINT } from "./ModaleSms";

/** What the screen holds; ``sms`` stays absent until it is stored or edited (a frozen payload never gains it). */
export type EtatApresAppel = Required<Omit<ApresAppelAgent, "sms">> & { sms?: SmsAgent };

export const APRES_APPEL_ETEINT: EtatApresAppel = { actif: false, synthese: true, mail: true, modules: [], champs: {} };

export const smsInvalides = (valeur: EtatApresAppel) => (valeur.actif && valeur.modules.includes("sms") && valeur.sms ? erreursSms(valeur.sms) : []);

export const MODULES_APRES_APPEL: Array<{ nom: string; libelle: Texte }> = [
    { nom: "webhook", libelle: { en: "Custom webhook (n8n)", fr: "Webhook sur mesure (n8n)" } },
    {
        nom: "connecteurs",
        libelle: {
            en: "Redo the software actions put aside during the call (an appointment the calendar did not take in time)",
            fr: "Refaire les actions mises de côté pendant l'appel (un rendez-vous que l'agenda n'a pas pris à temps)",
        },
    },
    { nom: "sms", libelle: { en: "SMS to the caller and the team (the client's Twilio)", fr: "SMS à l'appelant et à l'équipe (Twilio du client)" } },
];

const ROLES: Array<{ role: string; libelle: Texte }> = [
    { role: "nom", libelle: { en: "Name", fr: "Nom" } },
    { role: "prenom", libelle: { en: "First name", fr: "Prénom" } },
    { role: "mail", libelle: { en: "Mail", fr: "Mail" } },
    { role: "motif", libelle: { en: "Reason", fr: "Motif" } },
    { role: "degre_urgence", libelle: { en: "Urgency", fr: "Urgence" } },
    { role: "type_demande", libelle: { en: "Request type", fr: "Type de demande" } },
    { role: "numero_rappel", libelle: { en: "Call-back number", fr: "Numéro de rappel" } },
];

export const NOM_DE_CHAMP = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

/** What the screen holds, completed with the defaults; compared and sent as such. */
export const lireApresAppel = (brut: ApresAppelAgent | null | undefined): EtatApresAppel => ({
    ...APRES_APPEL_ETEINT,
    ...(brut ?? {}),
    modules: [...(brut?.modules ?? [])],
    champs: { ...(brut?.champs ?? {}) },
});

/** The fields typed, without the empty ones and those equal to their role (the default). */
export const pourEnvoyer = (valeur: EtatApresAppel): EtatApresAppel => ({
    ...valeur,
    champs: Object.fromEntries(
        Object.entries(valeur.champs)
            .map(([role, champ]) => [role, (champ ?? "").trim()] as const)
            .filter(([role, champ]) => champ !== "" && champ !== role),
    ),
});

export const champsInvalides = (valeur: EtatApresAppel) =>
    Object.values(valeur.champs).filter((champ) => (champ ?? "").trim() !== "" && !NOM_DE_CHAMP.test((champ ?? "").trim()));

export function SectionApresAppelAgent({
    valeur,
    onChange,
    workflowId,
    champsFiche = [],
}: {
    valeur: EtatApresAppel;
    onChange: (valeur: EtatApresAppel) => void;
    workflowId?: number;
    champsFiche?: string[];
}) {
    const { t } = useLangue();
    const poser = (partiel: Partial<ApresAppelAgent>) => onChange({ ...valeur, ...partiel } as EtatApresAppel);
    return (
        <>
            <ChampReglage
                cle="apres_appel"
                idControle="apres_appel_actif"
                libelle={{ en: "Work after the call", fr: "Travailler après l'appel" }}
                aides={[
                    {
                        en: "After each call, in the background: write it in the client's database (call, contact, request, record), summarise it, mail the request to the people of its routing, then run the modules ticked below. Failures show in « After the call » of the run window and go to the notification addresses.",
                        fr: "Après chaque appel, en tâche de fond : l'écrire dans la base du client (appel, contact, demande, fiche), le résumer, envoyer la demande par mail aux personnes de son routage, puis lancer les modules cochés dessous. Les échecs s'affichent dans « Après l'appel » de la fenêtre du run et partent aux adresses de notification.",
                    },
                    {
                        en: "The summary key, the mail server and the modules' settings are the organization's (Platform Settings, « After the call »).",
                        fr: "La clé de la synthèse, le serveur de mail et les réglages des modules sont ceux de l'organisation (Paramètres, « Après l'appel »).",
                    },
                ]}
                bornes={{ en: "Default: off", fr: "Par défaut : éteint" }}
                disposition="ligne"
            >
                <Switch id="apres_appel_actif" checked={valeur.actif} onCheckedChange={(actif) => poser({ actif })} />
            </ChampReglage>
            {valeur.actif && (
                <>
                    <ChampReglage
                        cle="apres_appel.synthese"
                        idControle="apres_appel_synthese"
                        libelle={{ en: "Summarise the call", fr: "Résumer l'appel" }}
                        aides={[{ en: "A few lines next to the record, on the client's Mistral key.", fr: "Quelques lignes à côté de la fiche, sur la clé Mistral du client." }]}
                        bornes={{ en: "Default: on", fr: "Par défaut : allumé" }}
                        disposition="ligne"
                    >
                        <Switch id="apres_appel_synthese" checked={valeur.synthese} onCheckedChange={(synthese) => poser({ synthese })} />
                    </ChampReglage>
                    <ChampReglage
                        cle="apres_appel.mail"
                        idControle="apres_appel_mail"
                        libelle={{ en: "Mail the request", fr: "Envoyer la demande par mail" }}
                        aides={[{ en: "One mail per request, to the people its subject is routed to.", fr: "Un mail par demande, aux personnes de son sujet." }]}
                        bornes={{ en: "Default: on", fr: "Par défaut : allumé" }}
                        disposition="ligne"
                    >
                        <Switch id="apres_appel_mail" checked={valeur.mail} onCheckedChange={(mail) => poser({ mail })} />
                    </ChampReglage>
                    <ChampReglage
                        cle="apres_appel.modules"
                        libelle={{ en: "Modules of this agent", fr: "Modules de cet agent" }}
                        aides={[{ en: "Set in the organization's « After the call »; off by default.", fr: "Réglés dans « Après l'appel » de l'organisation ; éteints par défaut." }]}
                    >
                        <div className="space-y-1">
                            {MODULES_APRES_APPEL.map((module) => (
                                <label key={module.nom} className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        id={`apres_appel_module_${module.nom}`}
                                        checked={valeur.modules.includes(module.nom)}
                                        onChange={(e) =>
                                            poser({
                                                modules: e.target.checked
                                                    ? [...valeur.modules, module.nom]
                                                    : valeur.modules.filter((m) => m !== module.nom),
                                            })
                                        }
                                    />
                                    {t(module.libelle)}
                                </label>
                            ))}
                        </div>
                    </ChampReglage>
                    {valeur.modules.includes("sms") && (
                        <BoutonSms
                            workflowId={workflowId}
                            valeur={valeur.sms ?? SMS_ETEINT}
                            onChange={(sms) => poser({ sms } as Partial<EtatApresAppel>)}
                            champsFiche={champsFiche}
                        />
                    )}
                    <ChampReglage
                        cle="apres_appel.champs"
                        libelle={{ en: "Record fields read after the call", fr: "Champs de la fiche lus après l'appel" }}
                        aides={[
                            {
                                en: "Which field of the record holds each of these. Empty: the field of the same name (« nom », « motif »…). The reason and the request type route the mail.",
                                fr: "Quel champ de la fiche porte chacun de ces éléments. Vide : le champ du même nom (« nom », « motif »…). Le motif et le type de demande routent le mail.",
                            },
                        ]}
                    >
                        <div className="grid gap-2 sm:grid-cols-2">
                            {ROLES.map(({ role, libelle }) => (
                                <label key={role} className="space-y-0.5 text-xs text-muted-foreground">
                                    <span>{t(libelle)}</span>
                                    <Input
                                        id={`apres_appel_champ_${role}`}
                                        value={valeur.champs[role] ?? ""}
                                        placeholder={role}
                                        onChange={(e) => poser({ champs: { ...valeur.champs, [role]: e.target.value } })}
                                    />
                                </label>
                            ))}
                        </div>
                    </ChampReglage>
                </>
            )}
        </>
    );
}
