"use client";

/**
 * [.mark] V5 : l'éditeur du widget du site, à la maquette (`components/portail/agent-vocal/editeur-widget.tsx`).
 *
 * Quatre onglets (Apparence, Comportement, Pose sur le site, Réglages .mark), l'aperçu cliquable du VRAI widget, les
 * étapes du visiteur, l'écran ordinateur / téléphone. Chaque champ lit et écrit une vraie donnée :
 *  - apparence : `GET/PUT /organizations/agents-site/{id}/apparence` (couleurs, polices, textes, emblème, position…) ;
 *  - réglages .mark : `…/reglages` (plafonds, durée, limite par adresse, domaines, modes, expiration du jeton) ;
 *  - affiché / coupé : `…/affichage` ; emplacement : `…/emplacement` ; sites : `/organizations/sites`.
 * Saisie gardée (`useBrouillonLocal`), « quitter sans enregistrer » prévenu, notification à l'enregistrement.
 * Dans le fork l'éditeur est celui de .mark : tous les onglets se modifient.
 */
import { Check, Code2, Copy, ExternalLink, Laptop, Lock, Palette, RotateCcw, Settings2, Smartphone, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    creerUnSiteApiV1OrganizationsSitesPost,
    lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet,
    lireLaCouleurDuSiteApiV1OrganizationsAgentsSiteWorkflowIdLireSitePost,
    lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet,
    lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet,
    listerLesSitesApiV1OrganizationsSitesGet,
    poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut,
    regenererLaCleDuSiteApiV1OrganizationsSitesSiteIdRegenererClePost,
    reglerLAffichageApiV1OrganizationsAgentsSiteWorkflowIdAffichagePut,
    reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut,
    reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut,
} from "@/client/sdk.gen";
import type { EmplacementLu, ReglagesMarkLus, SiteLu } from "@/client/types.gen";
import { useBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { useLangue } from "@/components/mark/langue/langue";
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import { detailFromError } from "@/lib/apiError";
import { copyTextToClipboard } from "@/lib/clipboard";

import { type Ecran, ApercuWidget } from "./ApercuWidget";
import {
    type Apparence,
    type CleCouleur,
    type CleTexte,
    type Declenchement,
    type EtatWidget,
    DECLENCHEMENTS,
    ETAPES,
    POLICES,
    TEINTES,
    ZONES,
    adresseValide,
    auBleuMark,
    avecCouleur,
    avecTexte,
    couleursResolues,
    declenchementDe,
    erreurDeTexte,
} from "./editeur-donnees";

type Lang = { fr: string; en: string };

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;
const hexSur7 = (v: string) => (v.length === 4 ? `#${[...v.slice(1)].map((c) => c + c).join("")}` : v);

/** Les réglages .mark tels qu'on les saisit (les domaines en une ligne, l'expiration en date ou vide = jamais). */
type Saisie = {
    plafond_conversations_mois: number;
    plafond_minutes_mois: number;
    duree_max_s: number;
    sessions_par_heure_et_ip: number;
    domaines: string;
    modes: "voix_et_ecrit" | "voix";
    expire: string;
};
const saisieDe = (r: ReglagesMarkLus): Saisie => ({
    plafond_conversations_mois: r.plafond_conversations_mois,
    plafond_minutes_mois: r.plafond_minutes_mois,
    duree_max_s: r.duree_max_s,
    sessions_par_heure_et_ip: r.sessions_par_heure_et_ip,
    domaines: r.allowed_domains.join(", "),
    modes: r.modes ?? "voix_et_ecrit",
    expire: r.jeton_expire_le ?? "",
});
const BORNES = {
    plafond_conversations_mois: [1, 1_000_000],
    plafond_minutes_mois: [1, 1_000_000],
    duree_max_s: [60, 3600],
    sessions_par_heure_et_ip: [1, 1000],
} as const;
const domainesDe = (s: string) => s.split(",").map((d) => d.trim()).filter(Boolean);

export function EditeurWidget({ workflowId, onFermer }: { workflowId: number; onFermer: () => void }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const path = { workflow_id: workflowId };

    const [emplacement, setEmplacement] = useState<EmplacementLu | null>(null);
    const [sites, setSites] = useState<SiteLu[]>([]);
    const [charge, setCharge] = useState<{ ap: Apparence; saisie: Saisie; actif: boolean; consomme: ReglagesMarkLus } | null>(null);
    const [erreurChargement, setErreurChargement] = useState(false);
    const [ap, setAp] = useState<Apparence | null>(null);
    const [rm, setRm] = useState<Saisie | null>(null);
    const [actif, setActif] = useState(true);
    const [etat, setEtat] = useState<EtatWidget>("accroche");
    const [ecran, setEcran] = useState<Ecran>("ordinateur");
    const [microRefuse, setMicroRefuse] = useState(false);
    const [noteBasse, setNoteBasse] = useState(false);
    const [zone, setZone] = useState<string | null>(null);
    const [onglet, setOnglet] = useState("apparence");
    const [occupe, setOccupe] = useState(false);
    const [quitter, setQuitter] = useState(false);
    const [regenerer, setRegenerer] = useState(false);
    const [copie, setCopie] = useState(false);
    const [siteChoisi, setSiteChoisi] = useState<number | null>(null);
    const [chemins, setChemins] = useState("/");
    const [nouveauNom, setNouveauNom] = useState("");
    const [nouveauxDomaines, setNouveauxDomaines] = useState("");

    const charger = useCallback(async () => {
        try {
            // Les deux lectures partent ensemble ; l'apparence et les réglages suivent quand l'agent a son widget.
            const [e, s] = await Promise.all([
                lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path: { workflow_id: workflowId } }),
                listerLesSitesApiV1OrganizationsSitesGet(),
            ]);
            const lu = e.data ?? null;
            if (!lu) {
                setErreurChargement(true);
                return;
            }
            setEmplacement(lu);
            setSites(s.data ?? []);
            if (lu.site_id) {
                setSiteChoisi(lu.site_id);
                setChemins((lu.chemins ?? []).join("\n") || "/");
            }
            if (lu.embed_token_id) {
                const [a, r] = await Promise.all([
                    lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet({ path: { workflow_id: workflowId } }),
                    lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet({ path: { workflow_id: workflowId } }),
                ]);
                if (!a.data || !r.data) {
                    setErreurChargement(true);
                    return;
                }
                const c = { ap: a.data.apparence as Apparence, saisie: saisieDe(r.data), actif: !!lu.widget_actif, consomme: r.data };
                setCharge(c);
                setAp(c.ap);
                setRm(c.saisie);
                setActif(c.actif);
            } else {
                setOnglet("pose");
            }
            setErreurChargement(false);
        } catch {
            setErreurChargement(true);
        }
    }, [workflowId]);

    useEffect(() => {
        if (authLoading || !user) return;
        void charger();
    }, [authLoading, user, charger]);

    const modifie =
        !!charge &&
        !!ap &&
        !!rm &&
        (JSON.stringify(ap) !== JSON.stringify(charge.ap) || JSON.stringify(rm) !== JSON.stringify(charge.saisie) || actif !== charge.actif);
    // Une saisie non enregistrée (apparence, réglages, nouveau site, pages) est gardée si l'agent change ailleurs.
    const pagesModifiees = !!emplacement?.site_id && chemins !== ((emplacement.chemins ?? []).join("\n") || "/");
    useBrouillonLocal(modifie || nouveauNom !== "" || nouveauxDomaines !== "" || pagesModifiees);

    const tenterFermer = () => (modifie ? setQuitter(true) : onFermer());

    // ---- les fautes de saisie, lues sous le champ ----
    const fauteTexte = (cle: CleTexte, valeur: string): string | null => {
        const f = erreurDeTexte(cle, valeur);
        if (f === "vide") return t({ fr: "Ce texte ne peut pas être vide.", en: "This text cannot be empty." });
        if (f === "lignes") return t({ fr: "3 lignes au plus.", en: "3 lines at most." });
        if (f === "long") return t({ fr: cle === "accroche" ? "120 caractères au plus." : "200 caractères au plus.", en: cle === "accroche" ? "120 characters at most." : "200 characters at most." });
        return null;
    };
    const fauteReglage = (cle: keyof typeof BORNES): string | null => {
        if (!rm) return null;
        const [mini, maxi] = BORNES[cle];
        const v = rm[cle];
        return Number.isInteger(v) && v >= mini && v <= maxi
            ? null
            : t({ fr: `Entre ${mini} et ${maxi}.`, en: `Between ${mini} and ${maxi}.` });
    };
    const fautes = (): boolean => {
        if (!ap || !rm) return false;
        const textes = (ap.textes ?? {}) as Record<string, string>;
        return (
            Object.entries(textes).some(([cle, v]) => fauteTexte(cle as CleTexte, v) !== null) ||
            !adresseValide(ap.lien_confidentialite) ||
            !adresseValide(ap.logo_url) ||
            (Object.keys(BORNES) as (keyof typeof BORNES)[]).some((c) => fauteReglage(c) !== null) ||
            (ap.declenchement === "delai" && !((ap.delai_s ?? 0) >= 1 && (ap.delai_s ?? 0) <= 60))
        );
    };

    const enregistrer = async () => {
        if (!charge || !ap || !rm || fautes()) return;
        setOccupe(true);
        try {
            if (JSON.stringify(ap) !== JSON.stringify(charge.ap)) {
                const res = await reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut({ path, body: ap });
                if (res.error) throw new Error(detailFromError(res.error));
            }
            if (JSON.stringify(rm) !== JSON.stringify(charge.saisie)) {
                const res = await reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut({
                    path,
                    body: {
                        plafond_conversations_mois: rm.plafond_conversations_mois,
                        plafond_minutes_mois: rm.plafond_minutes_mois,
                        duree_max_s: rm.duree_max_s,
                        sessions_par_heure_et_ip: rm.sessions_par_heure_et_ip,
                        allowed_domains: domainesDe(rm.domaines),
                        modes: rm.modes,
                        // La date n'est renvoyée que si elle a changé : un jeton déjà échu ne bloque pas un autre réglage.
                        ...(rm.expire !== charge.saisie.expire ? { jeton_expire_le: rm.expire } : {}),
                    },
                });
                if (res.error) throw new Error(detailFromError(res.error));
            }
            if (actif !== charge.actif) {
                const res = await reglerLAffichageApiV1OrganizationsAgentsSiteWorkflowIdAffichagePut({ path, body: { actif } });
                if (res.error) throw new Error(detailFromError(res.error));
            }
            notifier.succes({ fr: "Widget enregistré.", en: "Widget saved." });
            onFermer();
        } catch (e) {
            notifier.echec({ fr: "Widget non enregistré. Vérifiez les champs puis réessayez.", en: "Widget not saved. Check the fields and try again." }, { erreur: e });
            await charger();
        } finally {
            setOccupe(false);
        }
    };

    /** Un geste immédiat de l'onglet « Pose » (créer un site, poser l'agent, régénérer la clé). */
    const agir = async (action: () => Promise<{ error?: unknown } | undefined>, ok: Lang, ko: Lang) => {
        setOccupe(true);
        try {
            const res = await action();
            if (res?.error) {
                notifier.echec(ko, { erreur: res.error });
                return false;
            }
            notifier.succes(ok);
            await charger();
            return true;
        } finally {
            setOccupe(false);
        }
    };

    const siteLu = sites.find((s) => s.id === siteChoisi);
    const embleme = (ap?.embleme ?? "orbe") as "orbe" | "logo";
    const modes = rm?.modes ?? "voix_et_ecrit";
    const lien = (() => {
        const domaine = (siteLu?.allowed_domains ?? []).find((d) => d && d !== "*");
        return domaine ? `https://${domaine.replace(/^\*\./, "")}${(emplacement?.chemins ?? ["/"])[0] ?? "/"}` : null;
    })();
    const emplacementEnClair = (() => {
        const cs = emplacement?.chemins ?? [];
        const domaine = siteLu?.allowed_domains?.[0] ?? siteLu?.nom ?? "";
        if (!emplacement?.site_id) return t({ fr: "Aucun site choisi", en: "No site chosen yet" });
        return cs.includes("/") ? `${t({ fr: "Tout le site", en: "Whole site" })} (${domaine})` : `${domaine}${cs.join(", ")}`;
    })();

    // ---- la bulle d'un élément choisi dans l'aperçu ----
    const z = zone ? ZONES[zone] : null;
    const k = ap ? couleursResolues(ap) : null;
    const contenuZone =
        z && ap && k ? (
            <>
                <p className="text-sm font-medium">{t(z.libelle)}</p>
                <div className="space-y-4">
                    {z.embleme && (
                        <div className="space-y-1.5">
                            <Label>{t({ fr: "Emblème", en: "Emblem" })}</Label>
                            <div className="flex gap-2">
                                {(["orbe", "logo"] as const).map((e) => (
                                    <Button key={e} type="button" size="sm" variant={embleme === e ? "default" : "outline"} onClick={() => setAp({ ...ap, embleme: e })}>
                                        {e === "orbe" ? t({ fr: "L'orbe", en: "The orb" }) : t({ fr: "Votre logo", en: "Your logo" })}
                                    </Button>
                                ))}
                            </div>
                            {embleme === "logo" && (
                                <>
                                    <Input
                                        aria-label={t({ fr: "Adresse de l'image de votre logo", en: "Address of your logo image" })}
                                        placeholder={t({ fr: "Adresse de l'image de votre logo (https://…)", en: "Address of your logo image (https://…)" })}
                                        value={ap.logo_url ?? ""}
                                        onChange={(e) => setAp({ ...ap, logo_url: e.target.value || null })}
                                    />
                                    {!adresseValide(ap.logo_url) && <ErreurChamp>{t({ fr: "Une adresse commence par https://.", en: "An address starts with https://." })}</ErreurChamp>}
                                </>
                            )}
                            {embleme === "orbe" && (
                                <label className="flex items-center justify-between gap-3 pt-2 text-sm">
                                    {t({ fr: "Orbe animée", en: "Animated orb" })}
                                    <Switch checked={ap.orbe_animee !== false} onCheckedChange={(v) => setAp({ ...ap, orbe_animee: v })} />
                                </label>
                            )}
                        </div>
                    )}
                    {z.textes?.map((tx) => {
                        const valeur = ((ap.textes ?? {}) as Record<string, string>)[tx.cle] ?? "";
                        const faute = fauteTexte(tx.cle, valeur);
                        const id = `texte-${tx.cle}`;
                        return (
                            <div key={tx.cle} className="space-y-1.5">
                                <Label htmlFor={id}>{tx.libelle ? t(tx.libelle) : t({ fr: "Texte", en: "Text" })}</Label>
                                {tx.long ? (
                                    <Textarea id={id} rows={3} value={valeur} aria-invalid={!!faute} onChange={(e) => setAp(avecTexte(ap, tx.cle, e.target.value))} />
                                ) : (
                                    <Input id={id} value={valeur} aria-invalid={!!faute} onChange={(e) => setAp(avecTexte(ap, tx.cle, e.target.value))} />
                                )}
                                <ErreurChamp>{faute}</ErreurChamp>
                                {z.aide && <p className="text-xs text-muted-foreground">{t(z.aide)}</p>}
                            </div>
                        );
                    })}
                    {z.couleurs?.map((c) => (
                        <ChoixCouleur key={c.cle} libelle={t(c.libelle)} valeur={k[c.cle]} onChange={(v) => setAp(avecCouleur(ap, c.cle as CleCouleur, v))} />
                    ))}
                    {z.lien && (
                        <div className="space-y-1.5">
                            <Label htmlFor="lien-confidentialite">{t({ fr: "Lien « Confidentialité »", en: "“Privacy” link" })}</Label>
                            <Input
                                id="lien-confidentialite"
                                value={ap.lien_confidentialite ?? ""}
                                aria-invalid={!adresseValide(ap.lien_confidentialite)}
                                onChange={(e) => setAp({ ...ap, lien_confidentialite: e.target.value || null })}
                            />
                            {!adresseValide(ap.lien_confidentialite) && <ErreurChamp>{t({ fr: "Une adresse commence par https://.", en: "An address starts with https://." })}</ErreurChamp>}
                        </div>
                    )}
                </div>
                {z.aide && !z.textes && <p className="text-xs text-muted-foreground">{t(z.aide)}</p>}
            </>
        ) : null;

    return (
        <>
            <Dialog open onOpenChange={(o) => !o && tenterFermer()}>
                <DialogContent
                    onOpenAutoFocus={(e) => e.preventDefault()}
                    className="flex h-[92vh] w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl"
                    data-testid="editeur-widget"
                >
                    <DialogHeader className="border-b px-6 pt-4 pr-12 pb-3 text-left">
                        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                            <DialogTitle className="flex items-center gap-2 text-lg">
                                {emplacement?.agent_nom || t({ fr: "Module du site", en: "Site module" })}
                                <Info>
                                    {t({
                                        fr: "Le même éditeur que le portail : une seule source, le client et .mark règlent le même module.",
                                        en: "The same editor as the client portal: one source, the client and .mark set the same module.",
                                    })}
                                </Info>
                            </DialogTitle>
                            <DialogDescription>{emplacement ? emplacementEnClair : ""}</DialogDescription>
                        </div>
                    </DialogHeader>

                    {erreurChargement ? (
                        <div className="flex-1">
                            <EtatVide cas="erreur" reessayer={() => void charger()} />
                        </div>
                    ) : !emplacement ? (
                        <div className="flex-1 px-6 py-6">
                            <EtatVide cas="chargement" lignes={4} />
                        </div>
                    ) : (
                        <Tabs value={onglet} onValueChange={(v) => { setOnglet(v); setZone(null); }} className="flex min-h-0 flex-1 flex-col gap-0">
                            <div className="flex flex-wrap items-center justify-between gap-3 px-6 pt-3">
                                <TabsList>
                                    <TabsTrigger value="apparence" className="gap-1.5" disabled={!charge}><Palette className="size-4" /> {t({ fr: "Apparence", en: "Appearance" })}</TabsTrigger>
                                    <TabsTrigger value="comportement" className="gap-1.5" disabled={!charge}><Settings2 className="size-4" /> {t({ fr: "Comportement", en: "Behaviour" })}</TabsTrigger>
                                    <TabsTrigger value="pose" className="gap-1.5"><Code2 className="size-4" /> {t({ fr: "Pose sur le site", en: "Installation" })}</TabsTrigger>
                                    <TabsTrigger value="mark" className="gap-1.5" disabled={!charge}><Lock className="size-4" /> {t({ fr: "Réglages .mark", en: ".mark settings" })}</TabsTrigger>
                                </TabsList>
                                <div className="flex items-center gap-5">
                                    {lien && (
                                        <a href={lien} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-sm text-primary hover:font-medium">
                                            {t({ fr: "Voir sur le site", en: "See on the site" })} <ExternalLink className="size-3.5" />
                                        </a>
                                    )}
                                    <label
                                        className="flex cursor-pointer items-center gap-2.5 text-sm"
                                        title={t({ fr: "Coupé, il disparaît du site au prochain chargement de page, sans toucher au script.", en: "Off, it disappears from the site on the next page load, the script stays." })}
                                    >
                                        {actif ? t({ fr: "Affiché sur le site", en: "Shown on the site" }) : t({ fr: "Coupé sur le site", en: "Off on the site" })}
                                        <Switch checked={actif} disabled={!charge} onCheckedChange={setActif} aria-label={t({ fr: "Affiché sur le site", en: "Shown on the site" })} />
                                    </label>
                                </div>
                            </div>

                            {/* L'apparence : les réglages en colonne, le widget en grand ; on clique sur ce qu'on veut changer. */}
                            <TabsContent value="apparence" className="grid min-h-0 flex-1 grid-cols-[230px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] gap-5 px-6 pt-3 pb-4">
                                {ap && rm && (
                                    <>
                                        <aside className="min-h-0 space-y-4 overflow-y-auto pr-1">
                                            <div className="space-y-1.5">
                                                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t({ fr: "Écran", en: "Screen" })}</p>
                                                <div className="flex w-full rounded-full border p-0.5" role="group" aria-label={t({ fr: "Écran", en: "Screen" })}>
                                                    {(["ordinateur", "telephone"] as const).map((e) => (
                                                        <button
                                                            key={e}
                                                            type="button"
                                                            aria-pressed={ecran === e}
                                                            onClick={() => { setEcran(e); setZone(null); }}
                                                            className={`flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-full text-xs ${ecran === e ? "bg-foreground text-background" : "text-muted-foreground hover:font-medium hover:text-foreground"}`}
                                                        >
                                                            {e === "ordinateur" ? <Laptop className="size-4" /> : <Smartphone className="size-4" />}
                                                            {e === "ordinateur" ? t({ fr: "Ordinateur", en: "Computer" }) : t({ fr: "Téléphone", en: "Phone" })}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                            <div className="space-y-2">
                                                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t({ fr: "Couleurs", en: "Colours" })}</p>
                                                <p className="text-xs text-muted-foreground">{t({ fr: "Couleur personnalisée, pour tout le widget :", en: "Custom colour, for the whole widget:" })}</p>
                                                <ChoixCouleur valeur={ap.couleur_base ?? "#1b5fb0"} onChange={(v) => setAp({ ...ap, couleur_base: v })} sansTeintes />
                                                <CouleurDuSite
                                                    workflowId={workflowId}
                                                    domaine={domainesDe(rm.domaines)[0] ?? ""}
                                                    onAppliquer={(couleur, logo) => setAp({ ...ap, couleur_base: couleur, ...(logo ? { logo_url: logo } : {}) })}
                                                />
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="sm"
                                                    className="w-full cursor-pointer justify-start px-2 hover:font-medium"
                                                    onClick={() => setAp(auBleuMark(ap))}
                                                    title={t({ fr: "Remet le bleu et l'orbe de .mark, et efface les retouches de couleur ; vos textes ne changent pas.", en: "Puts back .mark's blue and orb and clears colour tweaks; your texts stay." })}
                                                >
                                                    <RotateCcw className="size-4" /> {t({ fr: "Revenir au bleu .mark", en: "Back to .mark blue" })}
                                                </Button>
                                            </div>
                                            <div className="space-y-2">
                                                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t({ fr: "Police", en: "Font" })}</p>
                                                <Select value={ap.police ?? "switzer"} onValueChange={(v) => setAp({ ...ap, police: v as Apparence["police"] })}>
                                                    <SelectTrigger size="sm" className="w-full" aria-label={t({ fr: "Police", en: "Font" })}><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        {POLICES.map((p) => (
                                                            <SelectItem key={p.id} value={p.id}><span style={{ fontFamily: p.famille }}>{t(p)}</span></SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="space-y-1">
                                                <p className="pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t({ fr: "Étapes du visiteur", en: "Visitor steps" })}</p>
                                                {ETAPES.map((e) => (
                                                    <div key={e.id}>
                                                        <button
                                                            type="button"
                                                            aria-current={etat === e.id}
                                                            onClick={() => { setEtat(e.id); setZone(null); }}
                                                            className={`h-8 w-full cursor-pointer rounded-md px-2 text-left text-sm transition-colors hover:bg-sidebar-accent hover:font-medium hover:text-sidebar-accent-foreground ${etat === e.id ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : ""}`}
                                                        >
                                                            {t(e)}
                                                        </button>
                                                        {etat === e.id && e.id === "conversation" && (
                                                            <label className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground">
                                                                <Switch checked={microRefuse} onCheckedChange={(v) => { setMicroRefuse(v); setZone(null); }} /> {t({ fr: "Simuler : micro refusé", en: "Simulate: microphone refused" })}
                                                            </label>
                                                        )}
                                                        {etat === e.id && e.id === "avis" && (
                                                            <label className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground">
                                                                <Switch checked={noteBasse} onCheckedChange={(v) => { setNoteBasse(v); setZone(null); }} /> {t({ fr: "Simuler : note de 1 à 3", en: "Simulate: rating 1 to 3" })}
                                                            </label>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                            {!actif && <p className="text-xs text-(--marque-danger-texte)">{t({ fr: "Widget coupé : il n'apparaît plus sur votre site.", en: "Widget off: it no longer shows on your site." })}</p>}
                                        </aside>
                                        <ApercuWidget
                                            apparence={ap}
                                            modes={modes}
                                            etat={etat}
                                            ecran={ecran}
                                            microRefuse={microRefuse}
                                            noteBasse={noteBasse}
                                            zone={zone}
                                            onChoisir={setZone}
                                            contenu={contenuZone}
                                        />
                                    </>
                                )}
                            </TabsContent>

                            {/* Le comportement : des cartes à choisir plutôt que des listes. */}
                            <TabsContent value="comportement" className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                                {ap && (
                                    <div className="max-w-3xl space-y-6">
                                        <Choix
                                            titre={t({ fr: "Où se place le widget", en: "Where the widget sits" })}
                                            valeur={ap.position ?? "bas-droite"}
                                            onChange={(v) => setAp({ ...ap, position: v })}
                                            options={[
                                                { id: "bas-gauche" as const, libelle: t({ fr: "En bas à gauche", en: "Bottom left" }), schema: <Schema rond="gauche" /> },
                                                { id: "bas-droite" as const, libelle: t({ fr: "En bas à droite", en: "Bottom right" }), schema: <Schema rond="droite" /> },
                                            ]}
                                        />
                                        <Choix
                                            titre={t({ fr: "Où s'ouvre la fenêtre de conversation", en: "Where the conversation window opens" })}
                                            aide={t({ fr: "Sur téléphone mobile, elle s'ouvre en plein écran.", en: "On a mobile phone it opens full screen." })}
                                            valeur={ap.fenetre ?? "ancree"}
                                            onChange={(v) => setAp({ ...ap, fenetre: v })}
                                            options={[
                                                { id: "centree" as const, libelle: t({ fr: "Au centre de la page", en: "Centre of the page" }), schema: <Schema rond={ap.position === "bas-gauche" ? "gauche" : "droite"} fenetre="centree" /> },
                                                { id: "ancree" as const, libelle: t({ fr: "Au-dessus du widget", en: "Above the widget" }), schema: <Schema rond={ap.position === "bas-gauche" ? "gauche" : "droite"} fenetre="ancree" /> },
                                            ]}
                                        />
                                        <Choix
                                            titre={t({ fr: "Quand l'accroche s'affiche", en: "When the hook shows" })}
                                            valeur={declenchementDe(ap)}
                                            onChange={(v: Declenchement) => setAp({ ...ap, declenchement: v, ...(v === "delai" && !(ap.delai_s && ap.delai_s >= 1) ? { delai_s: 4 } : {}) })}
                                            options={DECLENCHEMENTS.map((d) => ({ id: d.id, libelle: t(d), schema: <Schema rond={ap.position === "bas-gauche" ? "gauche" : "droite"} accroche={d.id !== "jamais"} /> }))}
                                        />
                                        {ap.declenchement === "delai" && (
                                            <div className="max-w-48 space-y-1.5">
                                                <Label htmlFor="delai-accroche">{t({ fr: "Après combien de secondes", en: "After how many seconds" })}</Label>
                                                <Input
                                                    id="delai-accroche"
                                                    type="number"
                                                    min={1}
                                                    max={60}
                                                    value={ap.delai_s ?? 0}
                                                    onChange={(e) => setAp({ ...ap, delai_s: Number(e.target.value) })}
                                                />
                                                {!((ap.delai_s ?? 0) >= 1 && (ap.delai_s ?? 0) <= 60) && <ErreurChamp>{t({ fr: "Entre 1 et 60.", en: "Between 1 and 60." })}</ErreurChamp>}
                                            </div>
                                        )}
                                        <div className="flex items-center justify-between rounded-lg border px-4 py-3">
                                            <div>
                                                <p className="text-sm font-medium">{t({ fr: "Questionnaire d'avis en fin de conversation", en: "Review questionnaire at the end of the conversation" })}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {t({
                                                        fr: "Une note en étoiles, puis deux questions facultatives. Les avis et témoignages arrivent sur votre accueil.",
                                                        en: "A star rating, then two optional questions. Reviews and testimonials land on your home page.",
                                                    })}
                                                </p>
                                            </div>
                                            <Switch checked={ap.avis !== false} onCheckedChange={(v) => setAp({ ...ap, avis: v })} aria-label={t({ fr: "Questionnaire d'avis", en: "Review questionnaire" })} />
                                        </div>
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="pose" className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                                <div className="max-w-3xl space-y-5">
                                    <p className="text-sm text-muted-foreground">
                                        {t({
                                            fr: "Le script est la ligne de code qui fait apparaître le widget sur votre site. Le même pour tous vos agents : on le colle une seule fois, sur toutes les pages, juste avant la balise de fin. Il affiche l'agent de la page où se trouve le visiteur (sinon celui de « tout le site », sinon rien). Ajouter un agent ou changer un réglage ne demande aucune retouche du site.",
                                            en: "The script is the line of code that makes the widget appear on your site. The same for all your agents: paste it once, on every page, just before the closing tag. It shows the agent of the page the visitor is on (otherwise the “whole site” one, otherwise nothing). Adding an agent or changing a setting needs no change to the site.",
                                        })}
                                    </p>
                                    <div className="space-y-2" data-testid="emplacement">
                                        <Label>{t({ fr: "Site", en: "Site" })}</Label>
                                        <div className="flex flex-wrap gap-2">
                                            {sites.map((s) => (
                                                <Button key={s.id} type="button" size="sm" variant={s.id === siteChoisi ? "default" : "outline"} onClick={() => setSiteChoisi(s.id)}>
                                                    {s.nom || s.cle.slice(0, 12)}
                                                </Button>
                                            ))}
                                        </div>
                                        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                                            <Input aria-label={t({ fr: "Nom du site", en: "Site name" })} placeholder={t({ fr: "Nom du site", en: "Site name" })} value={nouveauNom} onChange={(e) => setNouveauNom(e.target.value)} />
                                            <Input aria-label={t({ fr: "Domaines autorisés", en: "Allowed domains" })} placeholder={t({ fr: "domaine.fr, www.domaine.fr", en: "domain.com, www.domain.com" })} value={nouveauxDomaines} onChange={(e) => setNouveauxDomaines(e.target.value)} />
                                            <Button
                                                type="button"
                                                size="sm"
                                                disabled={occupe || !nouveauNom.trim()}
                                                onClick={() =>
                                                    agir(
                                                        () => creerUnSiteApiV1OrganizationsSitesPost({ body: { nom: nouveauNom.trim(), allowed_domains: domainesDe(nouveauxDomaines) } }),
                                                        { fr: "Site créé.", en: "Site created." },
                                                        { fr: "Site non créé. Vérifiez les domaines.", en: "Site not created. Check the domains." },
                                                    ).then((ok) => {
                                                        if (ok) {
                                                            setNouveauNom("");
                                                            setNouveauxDomaines("");
                                                        }
                                                    })
                                                }
                                            >
                                                {t({ fr: "Ajouter un site", en: "Add a site" })}
                                            </Button>
                                        </div>
                                        <Label htmlFor="pages-servies" className="pt-2">{t({ fr: "Pages servies (un chemin par ligne, / = tout le site)", en: "Pages served (one path per line, / = whole site)" })}</Label>
                                        <Textarea id="pages-servies" rows={3} value={chemins} onChange={(e) => setChemins(e.target.value)} />
                                        <Button
                                            type="button"
                                            size="sm"
                                            disabled={occupe || siteChoisi === null}
                                            onClick={() =>
                                                agir(
                                                    () =>
                                                        poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut({
                                                            path,
                                                            body: { site_id: siteChoisi as number, chemins: chemins.split("\n").map((c) => c.trim()).filter(Boolean) },
                                                        }),
                                                    { fr: "Emplacement enregistré.", en: "Placement saved." },
                                                    { fr: "Emplacement non enregistré. Un autre agent sert peut-être déjà cette page.", en: "Placement not saved. Another agent may already serve this page." },
                                                )
                                            }
                                        >
                                            {t({ fr: "Poser l'agent", en: "Place the agent" })}
                                        </Button>
                                    </div>
                                    {siteLu && emplacement?.embed_token_id && (
                                        <>
                                            <div className="break-all rounded-lg bg-muted px-4 py-3 font-mono text-xs" data-testid="script-du-site">{siteLu.script}</div>
                                            <Button
                                                type="button"
                                                size="sm"
                                                variant="outline"
                                                onClick={async () => {
                                                    await copyTextToClipboard(siteLu.script);
                                                    notifier.succes({ fr: "Script copié.", en: "Script copied." });
                                                    setCopie(true);
                                                    setTimeout(() => setCopie(false), 1500);
                                                }}
                                            >
                                                {copie ? <Check className="size-4" /> : <Copy className="size-4" />} {copie ? t({ fr: "Copié", en: "Copied" }) : t({ fr: "Copier le script", en: "Copy the script" })}
                                            </Button>
                                        </>
                                    )}
                                    <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                                        <li><b className="text-foreground">Google Tag Manager</b> : {t({ fr: "nouvelle balise « HTML personnalisé », déclenchée sur toutes les pages.", en: "new “Custom HTML” tag, triggered on all pages." })}</li>
                                        <li><b className="text-foreground">WordPress</b> : {t({ fr: "extension d'en-tête et de pied de page, champ « pied de page ».", en: "header and footer plugin, “footer” field." })}</li>
                                        <li><b className="text-foreground">Wix, Shopify, Webflow, Squarespace</b> : {t({ fr: "champ « code personnalisé » des réglages du site.", en: "the site settings' “custom code” field." })}</li>
                                        <li>{t({ fr: "Ou ", en: "Or " })}<b className="text-foreground">{t({ fr: "écrivez à .mark", en: "write to .mark" })}</b>{t({ fr: " : nous le posons pour vous.", en: ": we install it for you." })}</li>
                                    </ul>
                                    <p className="text-sm" data-testid="script-detecte">
                                        {emplacement?.dernier_chargement ? (
                                            <span className="text-(--etat-fait)">✓ {t({ fr: "Script détecté", en: "Script detected" })}{lien ? ` ${t({ fr: "sur", en: "on" })} ${lien.replace(/^https:\/\//, "")}` : ""} ({emplacement.dernier_chargement}).</span>
                                        ) : (
                                            <span className="text-muted-foreground">{t({ fr: "Script pas encore vu sur votre site.", en: "Script not yet seen on your site." })}</span>
                                        )}
                                    </p>
                                </div>
                            </TabsContent>

                            <TabsContent value="mark" className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                                {rm && charge && (
                                    <div className="max-w-3xl space-y-4">
                                        <div className="space-y-1.5">
                                            <Label htmlFor="agent-branche">{t({ fr: "Agent branché", en: "Connected agent" })}</Label>
                                            <Input id="agent-branche" readOnly value={`${emplacement?.agent_nom ?? ""}${emplacement?.version_publiee ? ` (v${emplacement.version_publiee})` : ""}`} />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label htmlFor="domaines-autorises">{t({ fr: "Domaines autorisés", en: "Allowed domains" })}</Label>
                                            <Input id="domaines-autorises" value={rm.domaines} onChange={(e) => setRm({ ...rm, domaines: e.target.value })} />
                                            <p className="text-xs text-muted-foreground">{t({ fr: "Sur tout autre site, le script refuse de s'ouvrir : la consommation est protégée.", en: "On any other site the script refuses to open: consumption is protected." })}</p>
                                        </div>
                                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                            <div className="space-y-1.5">
                                                <Label htmlFor="plafond-mois">{t({ fr: "Plafond du mois (conversations)", en: "Monthly limit (conversations)" })}</Label>
                                                <ChampNombre id="plafond-mois" valeur={rm.plafond_conversations_mois} onChange={(n) => setRm({ ...rm, plafond_conversations_mois: n })} faute={fauteReglage("plafond_conversations_mois")} />
                                                <p className="text-xs text-muted-foreground">
                                                    {t({
                                                        fr: `Le nombre maximal de conversations de cet agent par mois, fixé par .mark pour protéger votre consommation. Atteint, le widget propose au visiteur de laisser ses coordonnées. Ce mois-ci : ${charge.consomme.conversations_ce_mois ?? 0} (${Math.round(((charge.consomme.conversations_ce_mois ?? 0) / Math.max(rm.plafond_conversations_mois, 1)) * 100)} %).`,
                                                        en: `The maximum number of conversations of this agent per month, set by .mark to protect your consumption. Once reached, the widget asks the visitor to leave their details. This month: ${charge.consomme.conversations_ce_mois ?? 0} (${Math.round(((charge.consomme.conversations_ce_mois ?? 0) / Math.max(rm.plafond_conversations_mois, 1)) * 100)} %).`,
                                                    })}
                                                </p>
                                            </div>
                                            <div className="space-y-1.5">
                                                <Label htmlFor="modes-conversation">{t({ fr: "Modes de conversation", en: "Conversation modes" })}</Label>
                                                <Select value={rm.modes} onValueChange={(v) => setRm({ ...rm, modes: v as Saisie["modes"] })}>
                                                    <SelectTrigger id="modes-conversation" className="w-full"><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="voix_et_ecrit">{t({ fr: "Voix, avec champ de saisie", en: "Voice, with an input field" })}</SelectItem>
                                                        <SelectItem value="voix">{t({ fr: "Voix seule", en: "Voice only" })}</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="space-y-1.5">
                                                <Label htmlFor="plafond-minutes">{t({ fr: "Plafond du mois (minutes)", en: "Monthly limit (minutes)" })}</Label>
                                                <ChampNombre id="plafond-minutes" valeur={rm.plafond_minutes_mois} onChange={(n) => setRm({ ...rm, plafond_minutes_mois: n })} faute={fauteReglage("plafond_minutes_mois")} />
                                                <p className="text-xs text-muted-foreground">{t({ fr: `Ce mois-ci : ${charge.consomme.minutes_ce_mois ?? 0} min.`, en: `This month: ${charge.consomme.minutes_ce_mois ?? 0} min.` })}</p>
                                            </div>
                                            <div className="space-y-1.5">
                                                <Label htmlFor="duree-max">{t({ fr: "Durée maximale d'une conversation (s)", en: "Maximum conversation length (s)" })}</Label>
                                                <ChampNombre id="duree-max" valeur={rm.duree_max_s} onChange={(n) => setRm({ ...rm, duree_max_s: n })} faute={fauteReglage("duree_max_s")} />
                                            </div>
                                            <div className="space-y-1.5">
                                                <Label htmlFor="sessions-ip">{t({ fr: "Sessions par heure et par adresse", en: "Sessions per hour and address" })}</Label>
                                                <ChampNombre id="sessions-ip" valeur={rm.sessions_par_heure_et_ip} onChange={(n) => setRm({ ...rm, sessions_par_heure_et_ip: n })} faute={fauteReglage("sessions_par_heure_et_ip")} />
                                            </div>
                                        </div>
                                        <div className="max-w-xs space-y-1.5">
                                            <Label htmlFor="expiration-jeton" className="flex items-center gap-1.5">
                                                {t({ fr: "Expiration du jeton", en: "Token expiry" })}
                                                <Info>{t({ fr: "Vide : le jeton n'expire jamais. Passé cette date, le widget n'apparaît plus.", en: "Empty: the token never expires. After this date the widget no longer shows." })}</Info>
                                            </Label>
                                            <Input id="expiration-jeton" type="date" value={rm.expire} onChange={(e) => setRm({ ...rm, expire: e.target.value })} />
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button asChild size="sm" variant="outline">
                                                <Link href={`/workflow/${workflowId}`}><ExternalLink className="size-4" /> {t({ fr: "Ouvrir l'agent dans Dograh", en: "Open the agent in Dograh" })}</Link>
                                            </Button>
                                            <Button type="button" size="sm" variant="outline" disabled={!siteLu} onClick={() => setRegenerer(true)}>
                                                {t({ fr: "Régénérer le jeton", en: "Regenerate the token" })}
                                            </Button>
                                        </div>
                                    </div>
                                )}
                            </TabsContent>
                        </Tabs>
                    )}

                    <DialogFooter className="flex-row flex-wrap justify-end gap-2 border-t bg-background px-6 py-4">
                        <Button variant="outline" onClick={tenterFermer}>{t({ fr: "Annuler", en: "Cancel" })}</Button>
                        <Button disabled={!modifie || occupe || fautes()} onClick={() => void enregistrer()}>{t({ fr: "Enregistrer", en: "Save" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <AlertDialog open={quitter} onOpenChange={setQuitter}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t({ fr: "Quitter sans enregistrer ?", en: "Leave without saving?" })}</AlertDialogTitle>
                        <AlertDialogDescription>{t({ fr: "Vos changements du widget ne seront pas enregistrés.", en: "Your widget changes will not be saved." })}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t({ fr: "Continuer à modifier", en: "Keep editing" })}</AlertDialogCancel>
                        <AlertDialogAction onClick={onFermer}>{t({ fr: "Quitter sans enregistrer", en: "Leave without saving" })}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={regenerer} onOpenChange={setRegenerer}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t({ fr: "Régénérer le jeton du site ?", en: "Regenerate the site token?" })}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t({
                                fr: "L'ancien script cesse de fonctionner tout de suite sur le site : il faudra y coller le nouveau script.",
                                en: "The old script stops working on the site right away: the new script has to be pasted there.",
                            })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t({ fr: "Annuler", en: "Cancel" })}</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={() => {
                                if (!siteLu) return;
                                void agir(
                                    () => regenererLaCleDuSiteApiV1OrganizationsSitesSiteIdRegenererClePost({ path: { site_id: siteLu.id } }),
                                    { fr: "Jeton régénéré. Collez le nouveau script sur le site.", en: "Token regenerated. Paste the new script on the site." },
                                    { fr: "Jeton non régénéré. Réessayez.", en: "Token not regenerated. Try again." },
                                ).then((ok) => ok && setOnglet("pose"));
                            }}
                        >
                            {t({ fr: "Régénérer", en: "Regenerate" })}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}

function ChampNombre({ id, valeur, onChange, faute }: { id: string; valeur: number; onChange: (n: number) => void; faute: string | null }) {
    return (
        <>
            <Input id={id} type="number" value={Number.isFinite(valeur) ? valeur : ""} aria-invalid={!!faute} aria-describedby={faute ? `${id}-faute` : undefined} onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
            <ErreurChamp id={`${id}-faute`}>{faute}</ErreurChamp>
        </>
    );
}

/** Une couleur : les teintes proposées d'un clic, puis le choix libre (aucun contrôle de lisibilité, décision d'Evan). */
function ChoixCouleur({ libelle, valeur, onChange, sansTeintes = false }: { libelle?: string; valeur: string; onChange: (v: string) => void; sansTeintes?: boolean }) {
    const { t } = useLangue();
    const [brut, setBrut] = useState(valeur);
    useEffect(() => setBrut(valeur), [valeur]);
    const invalide = !HEX.test(brut);
    return (
        <div className="space-y-1.5">
            {libelle && <Label>{libelle}</Label>}
            <div className="flex flex-wrap items-center gap-1.5">
                {!sansTeintes &&
                    TEINTES.map((c) => (
                        <button
                            key={c}
                            type="button"
                            onClick={() => onChange(c)}
                            aria-label={c}
                            className={`size-6 cursor-pointer rounded-full border ${valeur.toLowerCase() === c ? "ring-2 ring-foreground ring-offset-2" : ""}`}
                            style={{ background: c }}
                        />
                    ))}
                <label className="relative size-6 cursor-pointer overflow-hidden rounded-full border" title={t({ fr: "Autre couleur", en: "Other colour" })} style={{ background: "conic-gradient(#f43f5e, #f59e0b, #22c55e, #3b82f6, #a855f7, #f43f5e)" }}>
                    <input type="color" aria-label={t({ fr: "Autre couleur", en: "Other colour" })} value={hexSur7(HEX.test(valeur) ? valeur : "#000000")} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
                </label>
                <Input
                    aria-label={libelle ? `${libelle} (hex)` : "hex"}
                    aria-invalid={invalide}
                    value={brut}
                    onChange={(e) => {
                        setBrut(e.target.value);
                        if (HEX.test(e.target.value)) onChange(e.target.value.toLowerCase());
                    }}
                    className={`ml-1 h-7 font-mono text-xs ${sansTeintes ? "flex-1" : "w-24"}`}
                />
            </div>
            {invalide && <ErreurChamp>{t({ fr: "Une couleur s'écrit #rgb ou #rrggbb.", en: "A colour is written #rgb or #rrggbb." })}</ErreurChamp>}
        </div>
    );
}

/** « Couleur de mon site » : le serveur lit la page d'accueil (domaines autorisés seulement) et rend sa couleur et son logo. */
function CouleurDuSite({ workflowId, domaine, onAppliquer }: { workflowId: number; domaine: string; onAppliquer: (couleur: string, logo: string | null) => void }) {
    const { t } = useLangue();
    const [adresse, setAdresse] = useState(domaine);
    const [lu, setLu] = useState<{ couleur: string | null; logo: string | null } | undefined>(undefined);
    const [ouvert, setOuvert] = useState(false);
    const [occupe, setOccupe] = useState(false);
    useEffect(() => setAdresse(domaine), [domaine]);
    const lire = async () => {
        setOccupe(true);
        try {
            const res = await lireLaCouleurDuSiteApiV1OrganizationsAgentsSiteWorkflowIdLireSitePost({
                path: { workflow_id: workflowId },
                body: adresse.trim() ? { adresse: adresse.trim().startsWith("http") ? adresse.trim() : `https://${adresse.trim()}` } : {},
            });
            if (res.error) {
                notifier.echec({ fr: "Couleurs non importées. Vérifiez l'adresse du site.", en: "Colours not imported. Check the site address." }, { erreur: res.error });
                return;
            }
            setLu({ couleur: res.data?.couleur ?? null, logo: res.data?.logo_url ?? null });
        } finally {
            setOccupe(false);
        }
    };
    return (
        <Popover open={ouvert} onOpenChange={setOuvert}>
            <PopoverTrigger asChild>
                <button type="button" className="flex h-8 w-full cursor-pointer items-center gap-2 rounded-full border px-3 text-sm transition-colors hover:bg-muted hover:font-medium">
                    <Sparkles className="size-4" /> {t({ fr: "Couleur de mon site", en: "My site's colour" })}
                </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-80 space-y-3">
                <p className="text-sm font-medium">{t({ fr: "Reprendre la couleur de votre site", en: "Use your site's colour" })}</p>
                <div className="flex gap-2">
                    <Input aria-label={t({ fr: "Adresse du site", en: "Site address" })} value={adresse} onChange={(e) => setAdresse(e.target.value)} placeholder="www.votre-site.fr" />
                    <Button type="button" size="sm" className="h-9" disabled={occupe} onClick={() => void lire()}>{t({ fr: "Lire", en: "Read" })}</Button>
                </div>
                {lu && !lu.couleur && <p className="text-xs text-muted-foreground">{t({ fr: "Aucune couleur trouvée sur cette page. Choisissez une couleur, puis retouchez-la dans l'aperçu.", en: "No colour found on this page. Pick a colour, then tweak it in the preview." })}</p>}
                {lu?.couleur && (
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <span className="size-8 rounded-full border" style={{ background: lu.couleur }} />
                            <span className="font-mono text-sm">{lu.couleur}</span>
                        </div>
                        <Button type="button" size="sm" onClick={() => { onAppliquer(lu.couleur as string, lu.logo); setOuvert(false); }}>{t({ fr: "Appliquer au widget", en: "Apply to the widget" })}</Button>
                    </div>
                )}
                <p className="text-xs text-muted-foreground">{t({ fr: "Nous lisons la page d'accueil de votre site : sa couleur principale et son logo.", en: "We read your site's home page: its main colour and logo." })}</p>
            </PopoverContent>
        </Popover>
    );
}

/** Un réglage de comportement : des cartes illustrées, un clic pour choisir. */
function Choix<T extends string>({ titre, aide, valeur, onChange, options }: { titre: string; aide?: string; valeur: T; onChange: (v: T) => void; options: { id: T; libelle: string; schema: React.ReactNode }[] }) {
    return (
        <div className="space-y-2">
            <p className="text-sm font-medium">{titre}</p>
            <div className="flex flex-wrap gap-3" role="radiogroup" aria-label={titre}>
                {options.map((o) => (
                    <button
                        key={o.id}
                        type="button"
                        role="radio"
                        aria-checked={valeur === o.id}
                        onClick={() => onChange(o.id)}
                        className={`w-40 cursor-pointer rounded-xl border p-2 text-left transition-colors ${valeur === o.id ? "border-foreground ring-1 ring-foreground" : "hover:bg-muted"}`}
                    >
                        {o.schema}
                        <span className="mt-2 flex items-center justify-between text-sm">
                            {o.libelle}
                            {valeur === o.id && <Check className="size-4" />}
                        </span>
                    </button>
                ))}
            </div>
            {aide && <p className="text-xs text-muted-foreground">{aide}</p>}
        </div>
    );
}

/** La page du site en miniature : où se tient le widget, où s'ouvre la fenêtre, l'accroche. */
function Schema({ rond, fenetre, accroche = false }: { rond: "gauche" | "droite"; fenetre?: "centree" | "ancree"; accroche?: boolean }) {
    const cote = rond === "droite" ? { right: 6 } : { left: 6 };
    return (
        <span className="relative block h-20 overflow-hidden rounded-md bg-muted" aria-hidden>
            <span className="absolute left-2 top-2 h-1.5 w-12 rounded bg-foreground/15" />
            <span className="absolute left-2 top-5 h-1.5 w-20 rounded bg-foreground/10" />
            {fenetre === "centree" && <span className="absolute left-1/2 top-1/2 h-12 w-14 -translate-x-1/2 -translate-y-1/2 rounded-md border bg-background shadow-sm" />}
            {fenetre === "ancree" && <span className="absolute bottom-6 h-11 w-12 rounded-md border bg-background shadow-sm" style={cote} />}
            {accroche && !fenetre && <span className="absolute bottom-1.5 h-3 w-14 rounded-full bg-primary/70" style={rond === "droite" ? { right: 22 } : { left: 22 }} />}
            <span className="absolute bottom-1.5 size-3.5 rounded-full bg-primary" style={cote} />
        </span>
    );
}
