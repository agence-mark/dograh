"use client";

/**
 * [.mark] The installation's settings (decision of Evan, 07/10, n° 319, option A), at the
 * end of the theme « After the call »: the .mark notification addresses (they receive
 * every organization's alerts) and the backup mail server (for an organization without
 * its own). Superusers only: the server answers 403 to anyone else and the block stays
 * hidden. Kept in .mark's organization, the one that holds them (by its id): the first
 * save fixes it, any other organization is refused. Acts at once (its own button),
 * nothing of the theme's « Save ».
 */
import { ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getInstallationApiV1OrganizationsApresAppelInstallationGet, putInstallationApiV1OrganizationsApresAppelInstallationPut } from "@/client/sdk.gen";
import type { EcranInstallation, ReglagesInstallation, ReglagesSmtp } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampEtiquettes } from "../ChampEtiquettes";
import { PREFIXE_REFERENCE } from "../cles/ChampCleModele";
import { SelecteurCle } from "../cles/FenetreCles";
import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { useLangue } from "../langue/langue";

const SMTP_VIDE: ReglagesSmtp = { hote: null, port: 587, securite: "starttls", utilisateur: null, mot_de_passe: null, expediteur: null, nom_expediteur: null };
const vide = (v: string) => (v.trim() === "" ? null : v.trim());
const versUuid = (reference: string | null | undefined) =>
    reference && reference.startsWith(PREFIXE_REFERENCE) ? reference.slice(PREFIXE_REFERENCE.length) : null;
const versReference = (uuid: string | null) => (uuid ? `${PREFIXE_REFERENCE}${uuid}` : null);

export function BlocInstallationMark() {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [ecran, setEcran] = useState<EcranInstallation | null>(null);
    const [brouillon, setBrouillon] = useState<ReglagesInstallation | null>(null);
    const [enCours, setEnCours] = useState(false);
    const dejaLu = useRef(false);

    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void (async () => {
            try {
                const r = await getInstallationApiV1OrganizationsApresAppelInstallationGet();
                if (r.data) {
                    setEcran(r.data);
                    setBrouillon(r.data.reglages);
                }
            } catch {
                // Not a superuser, or unreachable: the block stays hidden.
            }
        })();
    }, [loading, user]);

    if (!ecran || !brouillon) return null;
    const smtp = { ...SMTP_VIDE, ...(brouillon.smtp ?? {}) };
    const poserSmtp = (champ: keyof ReglagesSmtp, valeur: unknown) => setBrouillon({ ...brouillon, smtp: { ...smtp, [champ]: valeur } });
    const modifie = JSON.stringify(brouillon) !== JSON.stringify(ecran.reglages);
    const ailleurs = ecran.organisation_mark !== null && ecran.organisation_mark !== undefined && !ecran.ici;

    const enregistrer = async () => {
        setEnCours(true);
        const r = await putInstallationApiV1OrganizationsApresAppelInstallationPut({ body: { ...brouillon, smtp } });
        setEnCours(false);
        if (r.error || !r.data) {
            toast.error(detailFromError(r.error, "Installation settings not saved"));
            return;
        }
        setEcran(r.data);
        setBrouillon(r.data.reglages);
        toast.success(t({ en: "Installation settings saved", fr: "Réglages de l'installation enregistrés" }));
    };

    return (
        <Intertitre
            id="apres-appel-installation"
            titre={{ en: "Installation (.mark, superusers only)", fr: "Installation (.mark, superutilisateurs seulement)" }}
            description={{
                en: "Kept in .mark's organization and seen by superusers only. The .mark addresses receive every organization's alerts; the backup mail server sends them for an organization without its own.",
                fr: "Rangés dans l'organisation de .mark et vus des seuls superutilisateurs. Les adresses .mark reçoivent les alertes de toutes les organisations ; le serveur de secours les envoie pour une organisation qui n'a pas le sien.",
            }}
        >
            <p className="text-sm" data-testid="installation-porteur">
                {ecran.organisation_mark === null || ecran.organisation_mark === undefined
                    ? t({
                          en: "Not set yet: the first save makes this organization .mark's.",
                          fr: "Pas encore réglés : le premier enregistrement fait de cette organisation celle de .mark.",
                      })
                    : ecran.ici
                      ? t({
                            en: `This organization (n° ${ecran.organisation_mark}) is .mark's.`,
                            fr: `Cette organisation (n° ${ecran.organisation_mark}) est celle de .mark.`,
                        })
                      : t({
                            en: `Held by organization n° ${ecran.organisation_mark}, .mark's: change them from there.`,
                            fr: `Tenus par l'organisation n° ${ecran.organisation_mark}, celle de .mark : les modifier depuis celle-ci.`,
                        })}
            </p>
            <ChampReglage
                cle="installation.adresses_notification"
                idControle="installation-adresses"
                libelle={{ en: ".mark notification addresses", fr: "Adresses de notification .mark" }}
            >
                <ChampEtiquettes
                    id="installation-adresses"
                    valeurs={brouillon.adresses_notification ?? []}
                    onChange={(valeurs) => setBrouillon({ ...brouillon, adresses_notification: valeurs })}
                    placeholder={t({ en: "team@example.org", fr: "equipe@example.org" })}
                />
            </ChampReglage>
            <ChampReglage cle="installation.smtp_hote" idControle="installation-smtp-hote" libelle={{ en: "Backup mail server", fr: "Serveur de mail de secours" }}>
                <Input id="installation-smtp-hote" value={smtp.hote ?? ""} placeholder={t({ en: "smtp.example.org", fr: "smtp.example.org" })} onChange={(e) => poserSmtp("hote", vide(e.target.value))} />
            </ChampReglage>
            <ChampReglage cle="installation.smtp_port" idControle="installation-smtp-port" libelle={{ en: "Port", fr: "Port" }} bornes={{ en: "1 to 65535, default 587", fr: "1 à 65535, 587 par défaut" }}>
                <Input id="installation-smtp-port" type="number" min={1} max={65535} value={smtp.port ?? 587} onChange={(e) => poserSmtp("port", Number(e.target.value))} />
            </ChampReglage>
            <ChampReglage cle="installation.smtp_securite" idControle="installation-smtp-securite" libelle={{ en: "Security", fr: "Sécurité" }}>
                <select
                    id="installation-smtp-securite"
                    className="rounded border border-border bg-background px-2 py-1 text-sm"
                    value={smtp.securite ?? "starttls"}
                    onChange={(e) => poserSmtp("securite", e.target.value)}
                >
                    <option value="starttls">{t({ en: "STARTTLS", fr: "STARTTLS" })}</option>
                    <option value="ssl">{t({ en: "SSL/TLS", fr: "SSL/TLS" })}</option>
                    <option value="aucune">{t({ en: "None (local network only)", fr: "Aucune (réseau local seulement)" })}</option>
                </select>
            </ChampReglage>
            <ChampReglage cle="installation.smtp_utilisateur" idControle="installation-smtp-utilisateur" libelle={{ en: "User", fr: "Utilisateur" }}>
                <Input id="installation-smtp-utilisateur" value={smtp.utilisateur ?? ""} onChange={(e) => poserSmtp("utilisateur", vide(e.target.value))} />
            </ChampReglage>
            <ChampReglage cle="installation.smtp_mot_de_passe" libelle={{ en: "Password", fr: "Mot de passe" }}>
                <SelecteurCle
                    fournisseur="smtp"
                    valeur={versUuid(smtp.mot_de_passe)}
                    libelle={{ en: "A key of .mark's « Keys », provider SMTP", fr: "Une clé des « Clés » de .mark, fournisseur SMTP" }}
                    onChange={(uuid) => poserSmtp("mot_de_passe", versReference(uuid))}
                />
            </ChampReglage>
            <ChampReglage cle="installation.smtp_expediteur" idControle="installation-smtp-expediteur" libelle={{ en: "Sender", fr: "Expéditeur" }}>
                <Input id="installation-smtp-expediteur" value={smtp.expediteur ?? ""} placeholder={t({ en: "alerts@example.org", fr: "alertes@example.org" })} onChange={(e) => poserSmtp("expediteur", vide(e.target.value))} />
            </ChampReglage>
            <Button type="button" size="sm" disabled={!modifie || enCours || ailleurs} data-testid="installation-enregistrer" onClick={() => void enregistrer()}>
                <ShieldCheck className="mr-2 h-3.5 w-3.5" />
                {t({ en: "Save the installation settings", fr: "Enregistrer les réglages de l'installation" })}
            </Button>
        </Intertitre>
    );
}
