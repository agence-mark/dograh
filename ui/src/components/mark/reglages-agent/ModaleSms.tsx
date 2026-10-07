"use client";

/**
 * [.mark] The SMS of an agent (chantier l-agent-travaille, L6; plan sms-recapitulatif D1 to D11).
 *
 * Opened from the module « SMS » of « After the call » (theme « Call data »). Two switches, off by
 * default: the summary to the caller (on a French mobile only) and the alert to the team. Each
 * text is written with blanks filled by the record ({{nom}}…), never by the model; the preview
 * fills it with this agent's last call that holds a record, and says its length and how many SMS
 * the operator bills. The counter shows the SMS this agent has sent (the price is the reason a
 * client switches it off). The texts are sent with the agent's « Save », like the rest of the theme.
 */
import { MessageSquare } from "lucide-react";
import { useEffect, useState } from "react";

import { getCompteurSmsApiV1WorkflowWorkflowIdSmsGet, postApercuSmsApiV1WorkflowWorkflowIdSmsApercuPost } from "@/client/sdk.gen";
import type { ApercuSms } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import type { SmsAgent } from "@/types/workflow-configurations";

import { ChampEtiquettes } from "../ChampEtiquettes";
import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";

export const SMS_ETEINT: SmsAgent = {
    expediteur: null,
    appelant: { actif: false, texte: null },
    equipe: { actif: false, texte: null, numeros: [] },
};

export const LONGUEUR_SMS = 160;
const EXPEDITEUR = /^(?=.*[A-Za-z])[A-Za-z0-9 ]{1,11}$/;
const MOBILE = /^(?:\+33|0033|0)\s*[67](?:[\s.-]*\d){8}$/;

/** What would block the save, said where it is (the server refuses the same). */
export const erreursSms = (sms: SmsAgent): Texte[] => {
    const erreurs: Texte[] = [];
    if (sms.expediteur && !EXPEDITEUR.test(sms.expediteur.trim()))
        erreurs.push({ en: "Sender name: 1 to 11 letters, digits or spaces.", fr: "Nom d'expéditeur : 1 à 11 lettres, chiffres ou espaces." });
    if (sms.appelant.actif && !(sms.appelant.texte ?? "").trim())
        erreurs.push({ en: "The caller's SMS needs its text.", fr: "Le SMS à l'appelant demande son texte." });
    if (sms.equipe.actif && !(sms.equipe.texte ?? "").trim())
        erreurs.push({ en: "The team SMS needs its text.", fr: "Le SMS à l'équipe demande son texte." });
    if (sms.equipe.actif && sms.equipe.numeros.length === 0)
        erreurs.push({ en: "The team SMS needs one number at least.", fr: "Le SMS à l'équipe demande au moins un numéro." });
    if (sms.equipe.numeros.some((n) => !MOBILE.test(n.trim())))
        erreurs.push({ en: "The team's numbers are French mobiles (06, 07).", fr: "Les numéros de l'équipe sont des mobiles français (06, 07)." });
    return erreurs;
};

function Apercu({ workflowId, texte }: { workflowId?: number; texte: string | null }) {
    const { t } = useLangue();
    const [apercu, setApercu] = useState<ApercuSms | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    useEffect(() => {
        if (!workflowId || !(texte ?? "").trim()) {
            setApercu(null);
            return;
        }
        const minuterie = setTimeout(async () => {
            const r = await postApercuSmsApiV1WorkflowWorkflowIdSmsApercuPost({ path: { workflow_id: workflowId }, body: { texte: texte ?? "" } });
            if (r.error || !r.data) {
                setErreur(detailFromError(r.error, "No preview"));
                return;
            }
            setErreur(null);
            setApercu(r.data);
        }, 400);
        return () => clearTimeout(minuterie);
    }, [workflowId, texte]);
    if (erreur) return <p className="text-xs text-destructive">{erreur}</p>;
    if (!apercu) return null;
    return (
        <div className="space-y-1 rounded-md border bg-(--surface) p-2 text-xs" data-testid="apercu-sms">
            <p className="whitespace-pre-wrap">{apercu.texte}</p>
            <p className="text-muted-foreground">
                {apercu.longueur} / {LONGUEUR_SMS} · {t({ en: `${apercu.parties} SMS`, fr: `${apercu.parties} SMS` })}
                {apercu.encodage === "ucs2" ? t({ en: " (accents outside the SMS alphabet: 70 characters a part)", fr: " (accents hors alphabet SMS : 70 caractères par SMS)" }) : ""}
                {apercu.coupe ? t({ en: " · cut to 160 characters", fr: " · coupé à 160 caractères" }) : ""}
                {apercu.run_id
                    ? t({ en: ` · filled with the call n° ${apercu.run_id}`, fr: ` · rempli avec l'appel n° ${apercu.run_id}` })
                    : t({ en: " · no call with a record yet: blanks left empty", fr: " · aucun appel avec une fiche : trous laissés vides" })}
            </p>
            {(apercu.parties > 1 || apercu.coupe) && (
                <p className="text-(--signal-warn)">{t({ en: "Billed more than one SMS: shorten the text.", fr: "Facturé plus d'un SMS : raccourcissez le texte." })}</p>
            )}
        </div>
    );
}

export function BoutonSms({
    workflowId,
    valeur,
    onChange,
    champsFiche,
}: {
    workflowId?: number;
    valeur: SmsAgent;
    onChange: (valeur: SmsAgent) => void;
    champsFiche: string[];
}) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    const [envoyes, setEnvoyes] = useState<number | null>(null);
    useEffect(() => {
        if (!ouverte || !workflowId) return;
        void getCompteurSmsApiV1WorkflowWorkflowIdSmsGet({ path: { workflow_id: workflowId } }).then((r) => setEnvoyes(r.data?.envoyes ?? null));
    }, [ouverte, workflowId]);
    const erreurs = erreursSms(valeur);
    const resume = [
        valeur.appelant.actif ? t({ en: "caller", fr: "appelant" }) : null,
        valeur.equipe.actif ? t({ en: "team", fr: "équipe" }) : null,
    ].filter(Boolean);

    const texte = (qui: "appelant" | "equipe", libelle: Texte, aide: Texte) => (
        <div className="space-y-2 rounded-md border p-3">
            <ChampReglage cle={`apres_appel.sms.${qui}.actif`} idControle={`sms-${qui}-actif`} libelle={libelle} aides={[aide]} bornes={{ en: "Default: off", fr: "Par défaut : éteint" }} disposition="ligne">
                <Switch
                    id={`sms-${qui}-actif`}
                    checked={valeur[qui].actif}
                    onCheckedChange={(actif) => onChange({ ...valeur, [qui]: { ...valeur[qui], actif } })}
                />
            </ChampReglage>
            {valeur[qui].actif && (
                <>
                    <Textarea
                        id={`sms-${qui}-texte`}
                        rows={3}
                        value={valeur[qui].texte ?? ""}
                        placeholder={
                            qui === "appelant"
                                ? t({ en: "{{nom}}, we have noted your request: {{motif}}. We call you back within 48 h.", fr: "{{nom}}, nous avons bien noté votre demande : {{motif}}. On vous rappelle sous 48 h." })
                                : t({ en: "New call: {{nom}}, {{motif}}.", fr: "Nouvel appel : {{nom}}, {{motif}}." })
                        }
                        onChange={(e) => onChange({ ...valeur, [qui]: { ...valeur[qui], texte: e.target.value === "" ? null : e.target.value } })}
                    />
                    <Apercu workflowId={workflowId} texte={valeur[qui].texte} />
                </>
            )}
        </div>
    );

    return (
        <>
            <div className="flex flex-wrap items-center gap-3" id="reglage-apres_appel.sms" data-reglage="apres_appel.sms">
                <Button type="button" variant="outline" size="sm" onClick={() => setOuverte(true)}>
                    <MessageSquare className="mr-2 h-3.5 w-3.5" />
                    {t({ en: "SMS settings", fr: "Réglages des SMS" })}
                </Button>
                <span className="text-xs text-muted-foreground">
                    {resume.length ? resume.join(" · ") : t({ en: "No SMS switched on", fr: "Aucun SMS allumé" })}
                </span>
                {erreurs.length > 0 && <span className="text-xs text-destructive">{t(erreurs[0])}</span>}
            </div>
            <Dialog open={ouverte} onOpenChange={setOuverte}>
                <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "SMS after the call", fr: "SMS après l'appel" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "Sent by the client's Twilio (« Telephony ») once the call has ended, one per call and per recipient. Never written by the model: the blanks are filled by the record.",
                                fr: "Envoyés par le Twilio du client (« Téléphonie ») une fois l'appel fini, un par appel et par destinataire. Jamais écrits par le modèle : les trous sont remplis par la fiche.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <p className="text-xs text-muted-foreground" id="sms-compteur">
                            {envoyes === null
                                ? t({ en: "SMS sent by this agent: …", fr: "SMS envoyés par cet agent : …" })
                                : t({ en: `SMS sent by this agent: ${envoyes}`, fr: `SMS envoyés par cet agent : ${envoyes}` })}
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {t({ en: "Fields of the record:", fr: "Champs de la fiche :" })}{" "}
                            {champsFiche.length ? champsFiche.map((c) => <code key={c} className="mr-1">{`{{${c}}}`}</code>) : <code>{"{{nom}} {{motif}}"}</code>}
                        </p>
                        <ChampReglage
                            cle="apres_appel.sms.expediteur"
                            idControle="sms-expediteur"
                            libelle={{ en: "Sender name", fr: "Nom d'expéditeur" }}
                            aides={[{ en: "11 letters or digits at most (accepted in France; nobody can answer it). Empty: the number of « Telephony ».", fr: "11 lettres ou chiffres au plus (accepté en France ; on ne peut pas y répondre). Vide : le numéro de « Téléphonie »." }]}
                        >
                            <Input
                                id="sms-expediteur"
                                value={valeur.expediteur ?? ""}
                                maxLength={11}
                                placeholder={t({ en: "COMPANY", fr: "ENTREPRISE" })}
                                onChange={(e) => onChange({ ...valeur, expediteur: e.target.value.trim() === "" ? null : e.target.value })}
                            />
                        </ChampReglage>
                        {texte(
                            "appelant",
                            { en: "Send a summary to the caller", fr: "Envoyer un récapitulatif à l'appelant" },
                            {
                                en: "To the number presented if it is a French mobile, else the call-back number of the record. Not sent for a call without a reason, a voicemail or a wrong number.",
                                fr: "Au numéro présenté s'il est un mobile français, sinon au numéro de rappel de la fiche. Pas d'envoi pour un appel sans motif, un répondeur ou un faux numéro.",
                            },
                        )}
                        {texte(
                            "equipe",
                            { en: "Alert the team", fr: "Prévenir l'équipe" },
                            { en: "To each number below, after each call with a reason.", fr: "À chaque numéro ci-dessous, après chaque appel avec un motif." },
                        )}
                        {valeur.equipe.actif && (
                            <ChampReglage cle="apres_appel.sms.equipe.numeros" idControle="sms-equipe-numeros" libelle={{ en: "The team's mobiles", fr: "Mobiles de l'équipe" }}>
                                <ChampEtiquettes
                                    id="sms-equipe-numeros"
                                    valeurs={valeur.equipe.numeros}
                                    maxElements={5}
                                    placeholder="06 12 34 56 78"
                                    onChange={(numeros) => onChange({ ...valeur, equipe: { ...valeur.equipe, numeros } })}
                                />
                            </ChampReglage>
                        )}
                        {erreurs.map((e) => (
                            <p key={e.en} className="text-xs text-destructive">
                                {t(e)}
                            </p>
                        ))}
                    </div>
                    <DialogFooter>
                        <Button type="button" onClick={() => setOuverte(false)}>
                            {t({ en: "Done", fr: "Terminé" })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
