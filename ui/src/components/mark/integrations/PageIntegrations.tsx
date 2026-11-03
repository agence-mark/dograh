"use client";

/**
 * [.mark] U3 sexies point 1 (E73) : « Connecteurs » devient « Intégrations », trois onglets : Logiciels, Serveurs MCP,
 * Identifiants. L'adresse `/labo/connecteurs` reste valable. Une intégration est le branchement d'un logiciel une fois
 * pour l'organisation ; elle met des actions à disposition, que les Outils utilisent.
 */
import { useConnecteurs } from "../connecteurs/useConnecteurs";
import { useLangue } from "../langue/langue";
import { OngletsPage } from "../studio/onglets-page";
import { TitrePage } from "../studio/titre-page";
import { OngletIdentifiants } from "./OngletIdentifiants";
import { OngletLogiciels } from "./OngletLogiciels";
import { OngletServeursMcp } from "./OngletServeursMcp";

export function PageIntegrations() {
    const { t } = useLangue();
    const connecteurs = useConnecteurs();
    return (
        <div className="space-y-6">
            <TitrePage
                titre={t({ en: "Integrations", fr: "Intégrations" })}
                info={t({
                    en: "A software is connected once for the organization (Nango account, key, MCP server); it makes actions available, which the Tools use.",
                    fr: "Un logiciel se branche une fois pour l'organisation (compte Nango, clé, serveur MCP) ; il met des actions à disposition, que les Outils utilisent.",
                })}
            />
            <OngletsPage
                onglets={[
                    { id: "logiciels", titre: t({ en: "Software", fr: "Logiciels" }), contenu: <OngletLogiciels connecteurs={connecteurs} /> },
                    { id: "mcp", titre: t({ en: "MCP servers", fr: "Serveurs MCP" }), contenu: <OngletServeursMcp /> },
                    { id: "identifiants", titre: t({ en: "Credentials", fr: "Identifiants" }), contenu: <OngletIdentifiants /> },
                ]}
            />
        </div>
    );
}
