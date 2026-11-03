"use client";

import { useLangue } from "@/components/mark/langue/langue";
import { TitrePage } from "@/components/mark/studio/titre-page";

import { ListeDesFils } from "./ListeDesFils";

export default function PageHistorique() {
    const { t } = useLangue();
    return (
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
            <TitrePage titre={t({ en: "Chat", fr: "Chat" })} />
            <ListeDesFils />
        </div>
    );
}
