"use client";

/**
 * [.mark] Clôture D2 (É11, É68) : la page « Téléphonie » rangée au design du fork, comme la maquette (`EcranTelephonie`) : un titre court,
 * un tableau sans cadre (configuration, opérateur, numéros, état), une ligne mène à ses numéros, les gestes rares (par défaut, modifier,
 * réactiver, supprimer) sur la ligne. Aucun paragraphe écrit dans la page (une précision passe par « ! »), aucun texte anglais : l'étape
 * qui bloque un appel sortant se dit par son identifiant (`outbound_blocked_step`), traduit ici ; le texte du fournisseur n'est que le repli.
 * Mêmes routes, mêmes gestes que la page d'amont : aucune fonction en moins.
 */
import { AlertTriangle, Copy, ExternalLink, Pencil, Phone, Plus, RotateCcw, Star, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
    deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete,
    getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
    reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost,
    setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost,
} from "@/client/sdk.gen";
import type { TelephonyConfigurationDetail, TelephonyConfigurationListItem } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info, Marque, PointEtat } from "@/components/mark/studio/marques";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { ConfigFormDialog } from "@/components/telephony/ConfigFormDialog";
import { ConfigurationPrincipale, configurationPrincipale } from "./ConfigurationPrincipale";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useTelephonyConfigWarnings } from "@/context/TelephonyConfigWarningsContext";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";

/** Les étapes d'installation qui bloquent un appel sortant, par identifiant (`opérateur.étape`) : le serveur envoie la clé, l'écran la dit. */
export const ETAPES_BLOQUANTES: Record<string, Texte> = {
    "cloudonix.sip_domain": {
        en: "The SIP domain is not ready yet: save the Cloudonix credentials of this configuration.",
        fr: "Le domaine SIP n'est pas encore prêt : enregistrez les identifiants Cloudonix de cette configuration.",
    },
    "cloudonix.outbound_trunk": {
        en: "Under Outbound trunks, add a trunk pointing at your SIP carrier or PBX and allow its origin IP on your side. Without one there is nowhere to send outbound calls.",
        fr: "Dans « Lignes sortantes », ajoutez une ligne vers votre opérateur SIP ou votre standard et autorisez son adresse IP d'origine de votre côté. Sans elle, aucun appel sortant ne peut partir.",
    },
    "cloudonix.caller_id": {
        en: "Add at least one number your carrier delivers to you: Cloudonix requires a caller ID on every outbound call.",
        fr: "Ajoutez au moins un numéro que votre opérateur vous livre : Cloudonix exige un numéro appelant sur chaque appel sortant.",
    },
    "cloudonix.trunk_assignment": {
        en: "Tell which trunk each number dials out on.",
        fr: "Dites sur quelle ligne sortante chaque numéro appelle.",
    },
};

const T = {
    titre: { en: "Telephony", fr: "Téléphonie" },
    info: {
        en: "Connect one or more telephony provider accounts. Each campaign uses one configuration; inbound calls are routed to the right one by account ID.",
        fr: "Branchez un ou plusieurs comptes d'opérateur de téléphonie. Chaque campagne utilise une configuration ; les appels entrants sont dirigés vers la bonne par l'identifiant du compte.",
    },
    aide: { en: "Documentation", fr: "Documentation" },
    ajouter: { en: "New configuration", fr: "Nouvelle configuration" },
    config: { en: "Configuration", fr: "Configuration" },
    operateur: { en: "Provider", fr: "Opérateur" },
    numeros: { en: "Numbers", fr: "Numéros" },
    etat: { en: "State", fr: "État" },
    parDefaut: { en: "Default", fr: "Par défaut" },
    inactive: { en: "Inactive", fr: "Inactive" },
    incomplete: { en: "Setup incomplete", fr: "Configuration incomplète" },
    prete: { en: "Ready", fr: "Prête" },
    aucune: { en: "No telephony configuration yet", fr: "Aucune configuration de téléphonie" },
    identifiant: { en: "Configuration ID", fr: "Identifiant de la configuration" },
    coupee: { en: "Disabled after repeated connection failures.", fr: "Coupée après des échecs de connexion répétés." },
    sortantParDefaut: { en: "Make default for outbound calls", fr: "Rendre par défaut pour les appels sortants" },
    modifier: { en: "Edit", fr: "Modifier" },
    supprimer: { en: "Delete", fr: "Supprimer" },
    reactiver: { en: "Reactivate", fr: "Réactiver" },
    annuler: { en: "Cancel", fr: "Annuler" },
    titreSuppression: { en: "Delete this configuration?", fr: "Supprimer cette configuration ?" },
    telnyxTitre: { en: "Webhook public key not configured", fr: "Clé publique du webhook non renseignée" },
    vonageTitre: { en: "Signature secret not configured", fr: "Secret de signature non renseigné" },
} satisfies Record<string, Texte>;

/** L'étape bloquante, dite dans la langue de l'écran ; le texte du fournisseur n'est que le repli d'une clé inconnue. */
export const etapeDite = (item: TelephonyConfigurationListItem, t: (x: Texte) => string): string | null => {
    const cle = (item as { outbound_blocked_step?: string | null }).outbound_blocked_step;
    const connue = cle ? ETAPES_BLOQUANTES[`${item.provider}.${cle}`] : undefined;
    return connue ? t(connue) : (item.outbound_blocked_reason ?? null);
};

const nombreDe = (n: number, un: Texte, plusieurs: Texte): Texte => (n === 1 ? un : plusieurs);

export function PageTelephonie() {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const searchParams = useSearchParams();
    const { telnyxMissingWebhookPublicKeyCount, vonageMissingSignatureSecretCount, refresh: refreshWarnings } = useTelephonyConfigWarnings();
    const [items, setItems] = useState<TelephonyConfigurationListItem[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [createOpen, setCreateOpen] = useState(false);
    const [editTarget, setEditTarget] = useState<TelephonyConfigurationDetail | null>(null);
    const [editOpen, setEditOpen] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<TelephonyConfigurationListItem | null>(null);

    const lire = useCallback(async () => {
        if (authLoading || !user) return;
        const res = await listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet();
        if (res.error) {
            setErreur(true);
            notifier.echec({ fr: "Liste illisible. Rechargez la page.", en: "Could not load the list. Reload the page." }, { erreur: res.error });
            return;
        }
        setErreur(false);
        setItems(res.data?.configurations ?? []);
    }, [authLoading, user]);

    // Après un enregistrement, l'état d'avertissement du webhook a pu changer : on rafraîchit la bannière et le badge du menu.
    const apresEnregistrement = useCallback(async () => {
        await lire();
        await refreshWarnings();
    }, [lire, refreshWarnings]);

    useEffect(() => {
        void lire();
    }, [lire]);

    // ?add=1 mène droit au formulaire d'un opérateur (action « Ajouter un opérateur » de la fenêtre d'appel) : le choix n'est pas redemandé.
    useEffect(() => {
        if (searchParams.get("add") === "1") setCreateOpen(true);
    }, [searchParams]);

    const modifier = async (item: TelephonyConfigurationListItem) => {
        const res = await getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet({ path: { config_id: item.id } });
        if (res.error) return notifier.echec({ fr: "Configuration illisible. Rechargez la page.", en: "Could not load the configuration. Reload the page." }, { erreur: res.error });
        setEditTarget(res.data ?? null);
        setEditOpen(true);
    };
    const rendreParDefaut = async (item: TelephonyConfigurationListItem) => {
        const res = await setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost({ path: { config_id: item.id } });
        if (res.error) return notifier.echec({ fr: "Changement impossible. Réessayez.", en: "Could not change the default. Try again." }, { erreur: res.error });
        notifier.succes({ fr: `« ${item.name} » devient la configuration par défaut pour les appels sortants.`, en: `"${item.name}" is now the default for outbound calls.` });
        void lire();
    };
    const reactiver = async (item: TelephonyConfigurationListItem) => {
        const res = await reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost({ path: { config_id: item.id } });
        if (res.error) return notifier.echec({ fr: "Réactivation impossible. Réessayez.", en: "Could not reactivate. Try again." }, { erreur: res.error });
        notifier.succes({ fr: `« ${item.name} » réactivée. Reconnexion en cours, moins d'une minute.`, en: `"${item.name}" reactivated. Reconnecting, under a minute.` });
        void lire();
    };
    const supprimer = async () => {
        if (!deleteTarget) return;
        // suppression-confirmee : la fenêtre « Supprimer cette configuration ? » précède `supprimer`.
        const res = await deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete({ path: { config_id: deleteTarget.id } });
        setDeleteTarget(null);
        if (res.error) return notifier.echec({ fr: "Suppression impossible. Réessayez.", en: "Could not delete. Try again." }, { erreur: res.error });
        notifier.succes({ fr: "Configuration supprimée.", en: "Configuration deleted." });
        void lire();
    };
    const copier = (id: number) =>
        copyTextToClipboard(String(id))
            .then(() => notifier.succes({ fr: "Identifiant copié.", en: "ID copied." }))
            .catch(() => notifier.echec({ fr: "Copie impossible.", en: "Could not copy." }));

    const etapeBloquante = (item: TelephonyConfigurationListItem) => etapeDite(item, t);

    const avertissement = (titre: Texte, n: number, fournisseur: "Telnyx" | "Vonage") => (
        <p className="flex items-center gap-2 text-sm" role="status">
            <AlertTriangle className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="font-medium">{t(titre)}</span>
            <Info>
                {t(
                    fournisseur === "Telnyx"
                        ? {
                              en: `${n} Telnyx configuration(s) missing a webhook public key: Telnyx call status updates and inbound calls are rejected. Copy the public key from Mission Control Portal › Keys & Credentials › Public Key and paste it into the configuration.`,
                              fr: `${n} configuration(s) Telnyx sans clé publique de webhook : les mises à jour d'état des appels Telnyx et les appels entrants sont rejetés. Copiez la clé publique depuis Mission Control Portal › Keys & Credentials › Public Key et collez-la dans la configuration.`,
                          }
                        : {
                              en: `${n} Vonage configuration(s) missing a signature secret: signed webhooks are rejected, so inbound calls and call status updates will not work. Copy the signature secret from your Vonage account and paste it into the configuration.`,
                              fr: `${n} configuration(s) Vonage sans secret de signature : les webhooks signés sont rejetés, donc les appels entrants et les mises à jour d'état ne fonctionnent pas. Copiez le secret de signature depuis votre compte Vonage et collez-le dans la configuration.`,
                          },
                )}
            </Info>
        </p>
    );

    return (
        <PageStudio>
            <TitrePage
                titre={t(T.titre)}
                info={
                    <>
                        {t(T.info)}{" "}
                        <a href="https://docs.dograh.com/integrations/telephony/overview" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-medium hover:font-semibold">
                            {t(T.aide)} <ExternalLink className="size-3" aria-hidden />
                        </a>
                    </>
                }
                action={
                    <Button className="cursor-pointer" onClick={() => setCreateOpen(true)}>
                        <Plus className="size-4" /> {t(T.ajouter)}
                    </Button>
                }
            />
            {telnyxMissingWebhookPublicKeyCount > 0 && avertissement(T.telnyxTitre, telnyxMissingWebhookPublicKeyCount, "Telnyx")}
            {vonageMissingSignatureSecretCount > 0 && avertissement(T.vonageTitre, vonageMissingSignatureSecretCount, "Vonage")}
            {erreur ? (
                <EtatVide cas="erreur" reessayer={() => void lire()} />
            ) : items === null ? (
                <EtatVide cas="chargement" lignes={3} />
            ) : items.length === 0 ? (
                <EtatVide cas="premier" icone={Phone} titre={t(T.aucune)} />
            ) : (
                <Tableau colonnes={[{ titre: t(T.config) }, { titre: t(T.operateur) }, { titre: t(T.numeros), droite: true }, { titre: t(T.etat) }, { titre: "" }]}>
                    {items.map((item) => {
                        const bloque = etapeBloquante(item);
                        return (
                            <Ligne key={item.id} href={`/telephony-configurations/${item.id}`}>
                                <Cellule principale sous={`${t(T.identifiant)} : ${item.id}`}>
                                    <span className="inline-flex items-center gap-2">
                                        {item.name}
                                        {item.is_default_outbound && (
                                            <Marque ton="neutre">
                                                <Star className="mr-1 size-3 fill-current" aria-hidden />
                                                {t(T.parDefaut)}
                                            </Marque>
                                        )}
                                    </span>
                                </Cellule>
                                <Cellule>{item.provider}</Cellule>
                                <Cellule droite>
                                    {item.phone_number_count ?? 0}{" "}
                                    <span className="text-xs">{t(nombreDe(item.phone_number_count ?? 0, { en: "number", fr: "numéro" }, { en: "numbers", fr: "numéros" }))}</span>
                                </Cellule>
                                <Cellule>
                                    {item.inactive ? (
                                        <span className="inline-flex items-center gap-1.5">
                                            <PointEtat etat="panne">{t(T.inactive)}</PointEtat>
                                            <Info>
                                                {t(T.coupee)}
                                                {item.inactive_reason ? ` (${item.inactive_reason})` : ""}
                                            </Info>
                                        </span>
                                    ) : item.is_ready_for_outbound === false ? (
                                        <span className="inline-flex items-center gap-1.5">
                                            <PointEtat etat="attente">{t(T.incomplete)}</PointEtat>
                                            {bloque && <Info>{bloque}</Info>}
                                        </span>
                                    ) : (
                                        <PointEtat etat="publie">{t(T.prete)}</PointEtat>
                                    )}
                                </Cellule>
                                <td className="text-right" onClick={(e) => e.stopPropagation()}>
                                    <span className="inline-flex items-center gap-0.5">
                                        {item.inactive && (
                                            <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={t(T.reactiver)} title={t(T.reactiver)} onClick={() => void reactiver(item)}>
                                                <RotateCcw className="size-4" />
                                            </Button>
                                        )}
                                        {!item.is_default_outbound && (
                                            <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={t(T.sortantParDefaut)} title={t(T.sortantParDefaut)} onClick={() => void rendreParDefaut(item)}>
                                                <Star className="size-4" />
                                            </Button>
                                        )}
                                        <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={`${t(T.identifiant)} : ${item.id}`} title={t(T.identifiant)} onClick={() => void copier(item.id)}>
                                            <Copy className="size-4" />
                                        </Button>
                                        <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={t(T.modifier)} title={t(T.modifier)} onClick={() => void modifier(item)}>
                                            <Pencil className="size-4" />
                                        </Button>
                                        <Button variant="ghost" size="icon" className="size-7 cursor-pointer" aria-label={t(T.supprimer)} title={t(T.supprimer)} onClick={() => setDeleteTarget(item)}>
                                            <Trash2 className="size-4 text-(--marque-danger-texte)" />
                                        </Button>
                                    </span>
                                </td>
                            </Ligne>
                        );
                    })}
                </Tableau>
            )}

            {/* Clôture SA-5 (É11) : tout sur une page : la configuration principale, ses numéros et ses lignes SIP. */}
            {items !== null && items.length > 0 && !erreur && (
                <ConfigurationPrincipale key={configurationPrincipale(items).id} item={configurationPrincipale(items)} apres={apresEnregistrement} />
            )}

            <ConfigFormDialog open={createOpen} onOpenChange={setCreateOpen} existing={null} suggestDefaultOutbound={!(items ?? []).some((i) => i.is_default_outbound)} onSaved={apresEnregistrement} />
            <ConfigFormDialog open={editOpen} onOpenChange={setEditOpen} existing={editTarget} onSaved={apresEnregistrement} />

            <Dialog centree open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{t(T.titreSuppression)}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: `${deleteTarget?.name ?? ""} and all of its phone numbers will be removed. Any campaign that references this configuration blocks the deletion until it is reassigned.`,
                                fr: `« ${deleteTarget?.name ?? ""} » et tous ses numéros seront retirés. Une campagne qui utilise cette configuration bloque la suppression tant qu'elle n'est pas réaffectée.`,
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" className="cursor-pointer" onClick={() => setDeleteTarget(null)}>
                            {t(T.annuler)}
                        </Button>
                        <Button variant="destructive" className="cursor-pointer" onClick={() => void supprimer()}>
                            {t(T.supprimer)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </PageStudio>
    );
}
