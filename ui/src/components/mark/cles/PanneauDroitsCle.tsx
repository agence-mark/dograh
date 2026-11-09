"use client";

/**
 * [.mark] Clôture, lot A (D21, décision d'Evan du 09/11) : le panneau de droits d'une clé d'API.
 *  - le rôle que la clé porte (jamais plus de droits que son créateur : le serveur refuse sinon) ;
 *  - suspendre ou rétablir la clé en un clic ;
 *  - trois interrupteurs pour les gestes qui coûtent ou engagent par la porte MCP (Publier, Tests payants, Appels réels), ÉTEINTS par défaut :
 *    un interrupteur allumé ne donne rien de plus que le rôle.
 * Chaque changement dit son résultat par une notification ; un refus du serveur reste affiché jusqu'à fermeture.
 */
import { useEffect, useState } from "react";

import { listerLesRolesApiV1EquipeMarkRolesGet } from "@/client/sdk.gen";
import type { RoleResponse } from "@/client/types.gen";
import {
    changerLeRoleDeLaCle,
    changerLesInterrupteursMcp,
    type CleDroits,
    type GesteMcp,
    suspendreLaCle,
} from "@/components/mark/equipe/api-cloture";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Liste } from "@/components/mark/studio/liste";
import { Switch } from "@/components/ui/switch";
import { detailFromError } from "@/lib/apiError";

const GESTES: { id: GesteMcp; champ: "mcp_publier" | "mcp_tests_payants" | "mcp_appels_reels"; libelle: Texte; aide: Texte }[] = [
    {
        id: "publier",
        champ: "mcp_publier",
        libelle: { fr: "Publier par MCP", en: "Publish through MCP" },
        aide: { fr: "Publier un agent, une branche ou un groupe.", en: "Publish an agent, a branch or a group." },
    },
    {
        id: "tests_payants",
        champ: "mcp_tests_payants",
        libelle: { fr: "Tests payants par MCP", en: "Paid tests through MCP" },
        aide: { fr: "Rejouer les tests et les attaques (consomme des modèles payants).", en: "Replay tests and attacks (spends paid models)." },
    },
    {
        id: "appels_reels",
        champ: "mcp_appels_reels",
        libelle: { fr: "Appels réels par MCP", en: "Real calls through MCP" },
        aide: { fr: "Lancer une campagne ou un appel de test vers de vraies personnes.", en: "Start a campaign or a test call to real people." },
    },
];

const SANS_ROLE = "__aucun__";

export function PanneauDroitsCle({ cle, recharger }: { cle: CleDroits; recharger: () => void }) {
    const { t } = useLangue();
    const [roles, setRoles] = useState<RoleResponse[]>([]);
    useEffect(() => {
        listerLesRolesApiV1EquipeMarkRolesGet().then((res) => setRoles(res.data ?? []));
    }, []);

    const refus = (res: { error?: unknown }, repli: Texte) => {
        notifier.echec(repli, { erreur: res.error ? detailFromError(res.error as never, "") : undefined });
    };

    const changerRole = async (v: string) => {
        const res = await changerLeRoleDeLaCle(cle.id, v === SANS_ROLE ? null : Number(v));
        if (res.error) return refus(res, { fr: "Rôle de la clé non modifié.", en: "Key role not changed." });
        notifier.succes({ fr: "Rôle de la clé enregistré.", en: "Key role saved." });
        recharger();
    };
    const suspendre = async (suspendue: boolean) => {
        const res = await suspendreLaCle(cle.id, suspendue);
        if (res.error) return refus(res, { fr: "Clé non modifiée.", en: "Key not changed." });
        notifier.succes(suspendue ? { fr: "Clé suspendue.", en: "Key suspended." } : { fr: "Clé rétablie.", en: "Key restored." });
        recharger();
    };
    const interrupteur = async (g: (typeof GESTES)[number], allume: boolean) => {
        const res = await changerLesInterrupteursMcp(cle.id, { [g.id]: allume });
        if (res.error) return refus(res, { fr: "Interrupteur non modifié.", en: "Switch not changed." });
        notifier.succes(allume ? { fr: `${g.libelle.fr} allumé.`, en: `${g.libelle.en} on.` } : { fr: `${g.libelle.fr} éteint.`, en: `${g.libelle.en} off.` });
        recharger();
    };

    return (
        <div className="mt-3 space-y-3 border-t pt-3" data-testid={`droits-cle-${cle.id}`}>
            <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium">{t({ fr: "Rôle de la clé", en: "Key role" })}</span>
                <Liste
                    valeur={cle.role_id != null ? String(cle.role_id) : SANS_ROLE}
                    changer={(v) => void changerRole(v)}
                    options={[
                        { valeur: SANS_ROLE, libelle: t({ fr: "Aucun (liste fermée du portail)", en: "None (closed portal list)" }) },
                        ...roles.map((r) => ({ valeur: String(r.id), libelle: r.nom })),
                    ]}
                    className="w-64"
                    libelle={t({ fr: "Rôle de la clé", en: "Key role" })}
                />
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <Switch checked={!cle.suspendue} onCheckedChange={(v) => void suspendre(!v)} aria-label={t({ fr: "Clé active", en: "Key active" })} className="cursor-pointer" />
                    {cle.suspendue ? t({ fr: "Suspendue", en: "Suspended" }) : t({ fr: "Active", en: "Active" })}
                </label>
            </div>
            <div className="space-y-2">
                <p className="text-muted-foreground text-xs">
                    {t({
                        fr: "Gestes par MCP, éteints par défaut. Allumé, un interrupteur ne donne rien de plus que le rôle de la clé et que les droits de son créateur.",
                        en: "Gestures through MCP, off by default. When on, a switch gives nothing beyond the key's role and its creator's rights.",
                    })}
                </p>
                {GESTES.map((g) => (
                    <label key={g.id} className="flex cursor-pointer items-center gap-3 text-sm">
                        <Switch
                            checked={Boolean(cle[g.champ])}
                            onCheckedChange={(v) => void interrupteur(g, v)}
                            aria-label={t(g.libelle)}
                            disabled={cle.role_id == null}
                            className="cursor-pointer"
                        />
                        <span className="font-medium">{t(g.libelle)}</span>
                        <span className="text-muted-foreground text-xs">{t(g.aide)}</span>
                    </label>
                ))}
                {cle.role_id == null && (
                    <p className="text-muted-foreground text-xs">
                        {t({ fr: "Choisissez un rôle pour pouvoir allumer un interrupteur.", en: "Choose a role to turn a switch on." })}
                    </p>
                )}
            </div>
        </div>
    );
}
