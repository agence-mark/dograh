"use client";

/**
 * [.mark] U10 / S2 : le widget d'un agent de SITE dans l'écran « Intégrer » de Dograh (EmbedDialog).
 *
 * Tout vient de `/organizations/sites` et `/organizations/agents-site/{id}/*` : rien n'est affiché qui n'existe pas côté
 * serveur. Le canal (téléphone ou site), le site et ses chemins, l'apparence (une couleur de base, l'accroche, un retour
 * au bleu .mark, « Couleur de mon site »), les réglages .mark (plafonds du mois, durée maximale, limite par adresse, domaines)
 * et l'aperçu de l'emblème et de l'accroche. Le script à copier est celui du SITE : un seul, quelle que soit la page.
 */
import { Check, Copy, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { notifier } from "@/components/mark/notifications";

import {
    creerUnSiteApiV1OrganizationsSitesPost,
    lireLaCouleurDuSiteApiV1OrganizationsAgentsSiteWorkflowIdLireSitePost,
    lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet,
    lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet,
    lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet,
    listerLesSitesApiV1OrganizationsSitesGet,
    poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut,
    reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut,
    reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut,
    reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut,
} from "@/client/sdk.gen";
import type { ApparenceLue, EmplacementLu, ReglagesMarkLus, SiteLu } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";

interface Props {
    workflowId: number;
}

function Champ({ etiquette, children }: { etiquette: string; children: React.ReactNode }) {
    return (
        <div className="grid gap-1.5">
            <Label>{etiquette}</Label>
            {children}
        </div>
    );
}

/** L'aperçu : l'emblème (orbe ou disque de la couleur) et l'accroche, tels que le visiteur les voit repliés. */
export function ApercuEmbleme({ couleur, accroche }: { couleur: string; accroche: string }) {
    return (
        <div className="flex items-center gap-3" data-testid="apercu-widget">
            <span
                aria-hidden
                className="h-12 w-12 shrink-0 rounded-full"
                style={{ background: couleur, boxShadow: `0 0 0 4px ${couleur}22` }}
            />
            <p className="max-w-xs whitespace-pre-line rounded-lg bg-muted px-3 py-2 text-sm">{accroche}</p>
        </div>
    );
}

export function PanneauSite({ workflowId }: Props) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [emplacement, setEmplacement] = useState<EmplacementLu | null>(null);
    const [sites, setSites] = useState<SiteLu[]>([]);
    const [apparence, setApparence] = useState<ApparenceLue | null>(null);
    const [reglages, setReglages] = useState<ReglagesMarkLus | null>(null);
    const [chargement, setChargement] = useState(true);
    const [occupe, setOccupe] = useState(false);
    const [siteChoisi, setSiteChoisi] = useState<number | null>(null);
    const [chemins, setChemins] = useState("/");
    const [nouveauNom, setNouveauNom] = useState("");
    const [nouveauxDomaines, setNouveauxDomaines] = useState("");
    const [couleur, setCouleur] = useState("");
    const [accroche, setAccroche] = useState("");
    const [copie, setCopie] = useState(false);

    const path = { workflow_id: workflowId };

    const charger = useCallback(async () => {
        setChargement(true);
        const [e, s] = await Promise.all([
            lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path }),
            listerLesSitesApiV1OrganizationsSitesGet(),
        ]);
        const lu = e.data ?? null;
        setEmplacement(lu);
        setSites(s.data ?? []);
        if (lu?.site_id) {
            setSiteChoisi(lu.site_id);
            setChemins((lu.chemins ?? []).join("\n") || "/");
        }
        if (lu?.embed_token_id) {
            const [a, r] = await Promise.all([
                lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet({ path }),
                lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet({ path }),
            ]);
            setApparence(a.data ?? null);
            setReglages(r.data ?? null);
            setCouleur(a.data?.apparence.couleur_base ?? "");
            setAccroche(a.data?.apparence.textes?.accroche ?? "");
        }
        setChargement(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [workflowId]);

    useEffect(() => {
        if (authLoading || !user) return;
        void charger();
    }, [authLoading, user, charger]);

    const agir = async (action: () => Promise<{ error?: unknown } | undefined>, ok: string) => {
        setOccupe(true);
        try {
            const res = await action();
            if (res?.error) {
                notifier.echec({ fr: "Couleurs non importées. Vérifiez l'adresse du site.", en: "Colors not imported. Check the site address." }, { erreur: res.error });
                return false;
            }
            notifier.succes({ fr: "Couleurs importées.", en: "Colors imported." });
            await charger();
            return true;
        } finally {
            setOccupe(false);
        }
    };

    // K7 : une saisie non enregistrée (nom ou domaines d'un nouveau site, chemins, couleur, accroche) est gardée si l'agent change ailleurs.
    const saisieNonEnregistree =
        nouveauNom !== "" ||
        nouveauxDomaines !== "" ||
        (emplacement?.site_id ? chemins !== ((emplacement.chemins ?? []).join("\n") || "/") : false) ||
        (apparence ? couleur !== (apparence.apparence.couleur_base ?? "") || accroche !== (apparence.apparence.textes?.accroche ?? "") : false);
    useBrouillonLocal(saisieNonEnregistree);

    if (chargement && !emplacement) return <Loader2 className="h-4 w-4 animate-spin" aria-label="loading" />;
    if (!emplacement) return null;

    const estSite = emplacement.canal === "site";
    const siteLu = sites.find((s) => s.id === siteChoisi);

    return (
        <section className="grid gap-4" data-testid="panneau-site">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="canal-site" className="cursor-pointer">
                    {t({ en: "Site agent (widget on a website)", fr: "Agent de site (widget sur un site internet)" })}
                </Label>
                <Switch
                    id="canal-site"
                    checked={estSite}
                    disabled={occupe}
                    onCheckedChange={(valeur) =>
                        agir(
                            () =>
                                reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut({
                                    path,
                                    body: { canal: valeur ? "site" : "telephone" },
                                }),
                            t({ en: "Channel saved", fr: "Canal enregistré" }),
                        )
                    }
                />
            </div>

            {estSite && (
                <>
                    <Champ etiquette={t({ en: "Site", fr: "Site" })}>
                        <div className="flex flex-wrap gap-2">
                            {sites.map((s) => (
                                <Button
                                    key={s.id}
                                    type="button"
                                    size="sm"
                                    variant={s.id === siteChoisi ? "default" : "outline"}
                                    onClick={() => setSiteChoisi(s.id)}
                                >
                                    {s.nom || s.cle.slice(0, 12)}
                                </Button>
                            ))}
                        </div>
                        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                            <Input
                                aria-label={t({ en: "Site name", fr: "Nom du site" })}
                                placeholder={t({ en: "Site name", fr: "Nom du site" })}
                                value={nouveauNom}
                                onChange={(e) => setNouveauNom(e.target.value)}
                            />
                            <Input
                                aria-label={t({ en: "Allowed domains", fr: "Domaines autorisés" })}
                                placeholder={t({ en: "domain.com, www.domain.com", fr: "domaine.fr, www.domaine.fr" })}
                                value={nouveauxDomaines}
                                onChange={(e) => setNouveauxDomaines(e.target.value)}
                            />
                            <Button
                                type="button"
                                size="sm"
                                disabled={occupe || !nouveauNom.trim()}
                                onClick={() =>
                                    agir(
                                        () =>
                                            creerUnSiteApiV1OrganizationsSitesPost({
                                                body: {
                                                    nom: nouveauNom.trim(),
                                                    allowed_domains: nouveauxDomaines
                                                        .split(",")
                                                        .map((d) => d.trim())
                                                        .filter(Boolean),
                                                },
                                            }),
                                        t({ en: "Site created", fr: "Site créé" }),
                                    ).then(() => {
                                        setNouveauNom("");
                                        setNouveauxDomaines("");
                                    })
                                }
                            >
                                {t({ en: "Add a site", fr: "Ajouter un site" })}
                            </Button>
                        </div>
                    </Champ>

                    <Champ etiquette={t({ en: "Pages served (one path per line, / = whole site)", fr: "Pages servies (un chemin par ligne, / = tout le site)" })}>
                        <textarea
                            className="min-h-20 rounded-md border bg-background px-3 py-2 text-sm"
                            value={chemins}
                            onChange={(e) => setChemins(e.target.value)}
                        />
                        <Button
                            type="button"
                            size="sm"
                            className="w-fit"
                            disabled={occupe || siteChoisi === null}
                            onClick={() =>
                                agir(
                                    () =>
                                        poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut({
                                            path,
                                            body: {
                                                site_id: siteChoisi as number,
                                                chemins: chemins
                                                    .split("\n")
                                                    .map((c) => c.trim())
                                                    .filter(Boolean),
                                            },
                                        }),
                                    t({ en: "Placement saved", fr: "Emplacement enregistré" }),
                                )
                            }
                        >
                            {t({ en: "Place the agent", fr: "Poser l'agent" })}
                        </Button>
                    </Champ>

                    {siteLu && emplacement.embed_token_id && (
                        <Champ etiquette={t({ en: "Script to copy (one per site)", fr: "Script à copier (un seul par site)" })}>
                            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{siteLu.script}</pre>
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="w-fit"
                                onClick={async () => {
                                    await copyTextToClipboard(siteLu.script);
                                    setCopie(true);
                                    setTimeout(() => setCopie(false), 1500);
                                }}
                            >
                                {copie ? <Check className="mr-1 h-3.5 w-3.5" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
                                {t({ en: "Copy", fr: "Copier" })}
                            </Button>
                        </Champ>
                    )}

                    {apparence && (
                        <>
                            <Champ etiquette={t({ en: "Base colour", fr: "Couleur de base" })}>
                                <div className="flex flex-wrap items-center gap-2">
                                    <input
                                        type="color"
                                        aria-label={t({ en: "Base colour", fr: "Couleur de base" })}
                                        className="h-9 w-12 cursor-pointer rounded border"
                                        value={couleur || apparence.apparence.couleur_base}
                                        onChange={(e) => setCouleur(e.target.value)}
                                    />
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={occupe}
                                        onClick={async () => {
                                            const res = await lireLaCouleurDuSiteApiV1OrganizationsAgentsSiteWorkflowIdLireSitePost({
                                                path,
                                                body: {},
                                            });
                                            if (res.error) notifier.echec({ fr: "Couleurs non importées. Réessayez.", en: "Colors not imported. Try again." }, { erreur: res.error });
                                            else if (res.data?.couleur) setCouleur(res.data.couleur);
                                            else notifier.information({ fr: "Aucune couleur trouvée sur le site.", en: "No color found on the site." });
                                        }}
                                    >
                                        {t({ en: "My site's colour", fr: "Couleur de mon site" })}
                                    </Button>
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        disabled={occupe}
                                        onClick={() =>
                                            agir(
                                                () => reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut({ path, body: {} }),
                                                t({ en: "Back to .mark blue", fr: "Retour au bleu .mark" }),
                                            )
                                        }
                                    >
                                        {t({ en: "Back to .mark blue", fr: "Revenir au bleu .mark" })}
                                    </Button>
                                </div>
                            </Champ>
                            <Champ etiquette={t({ en: "Hook (3 lines at most)", fr: "Accroche (3 lignes au plus)" })}>
                                <textarea
                                    className="min-h-16 rounded-md border bg-background px-3 py-2 text-sm"
                                    value={accroche}
                                    onChange={(e) => setAccroche(e.target.value)}
                                />
                            </Champ>
                            <ApercuEmbleme couleur={couleur || (apparence.apparence.couleur_base ?? "")} accroche={accroche} />
                            <Button
                                type="button"
                                size="sm"
                                className="w-fit"
                                disabled={occupe}
                                onClick={() =>
                                    agir(
                                        () =>
                                            reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut({
                                                path,
                                                body: {
                                                    ...apparence.apparence,
                                                    couleur_base: couleur || apparence.apparence.couleur_base,
                                                    textes: { ...apparence.apparence.textes, accroche },
                                                },
                                            }),
                                        t({ en: "Appearance saved", fr: "Apparence enregistrée" }),
                                    )
                                }
                            >
                                {t({ en: "Save the appearance", fr: "Enregistrer l'apparence" })}
                            </Button>
                        </>
                    )}

                    {reglages && <ReglagesMark workflowId={workflowId} reglages={reglages} occupe={occupe} agir={agir} />}
                </>
            )}
        </section>
    );
}

function ReglagesMark({
    workflowId,
    reglages,
    occupe,
    agir,
}: {
    workflowId: number;
    reglages: ReglagesMarkLus;
    occupe: boolean;
    agir: (action: () => Promise<{ error?: unknown } | undefined>, ok: string) => Promise<boolean>;
}) {
    const { t } = useLangue();
    const [valeurs, setValeurs] = useState({
        plafond_conversations_mois: reglages.plafond_conversations_mois,
        plafond_minutes_mois: reglages.plafond_minutes_mois,
        duree_max_s: reglages.duree_max_s,
        sessions_par_heure_et_ip: reglages.sessions_par_heure_et_ip,
    });
    const [domaines, setDomaines] = useState(reglages.allowed_domains.join(", "));
    useBrouillonLocal(
        domaines !== reglages.allowed_domains.join(", ") ||
            (Object.keys(valeurs) as (keyof typeof valeurs)[]).some((cle) => valeurs[cle] !== reglages[cle]),
    );
    const champ = (cle: keyof typeof valeurs, etiquette: string, min: number, max: number) => (
        <Champ etiquette={etiquette}>
            <Input
                type="number"
                min={min}
                max={max}
                value={valeurs[cle]}
                onChange={(e) => setValeurs({ ...valeurs, [cle]: Number(e.target.value) })}
            />
        </Champ>
    );
    return (
        <div className="grid gap-3" data-testid="reglages-mark">
            <p className="text-sm font-medium">
                {t({ en: ".mark settings", fr: "Réglages .mark" })}
                {" · "}
                <span className="text-muted-foreground">
                    {t({
                        en: `${reglages.conversations_ce_mois} conversations, ${reglages.minutes_ce_mois} min this month`,
                        fr: `${reglages.conversations_ce_mois} conversations, ${reglages.minutes_ce_mois} min ce mois-ci`,
                    })}
                </span>
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
                {champ("plafond_conversations_mois", t({ en: "Conversations per month", fr: "Conversations par mois" }), 1, 1000000)}
                {champ("plafond_minutes_mois", t({ en: "Minutes per month", fr: "Minutes par mois" }), 1, 1000000)}
                {champ("duree_max_s", t({ en: "Maximum duration (s)", fr: "Durée maximale (s)" }), 60, 3600)}
                {champ("sessions_par_heure_et_ip", t({ en: "Sessions per hour and address", fr: "Sessions par heure et par adresse" }), 1, 1000)}
            </div>
            <Champ etiquette={t({ en: "Allowed domains", fr: "Domaines autorisés" })}>
                <Input value={domaines} onChange={(e) => setDomaines(e.target.value)} />
            </Champ>
            <Button
                type="button"
                size="sm"
                className="w-fit"
                disabled={occupe}
                onClick={() =>
                    agir(
                        () =>
                            reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut({
                                path: { workflow_id: workflowId },
                                body: {
                                    ...valeurs,
                                    allowed_domains: domaines
                                        .split(",")
                                        .map((d) => d.trim())
                                        .filter(Boolean),
                                },
                            }),
                        t({ en: "Settings saved", fr: "Réglages enregistrés" }),
                    )
                }
            >
                {t({ en: "Save the settings", fr: "Enregistrer les réglages" })}
            </Button>
        </div>
    );
}
