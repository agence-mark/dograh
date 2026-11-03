"use client";

// [.mark] U3 septies (E92, E93) : la boîte de messages, demandes de logiciel comprises. `?fil=<id>` ouvre un fil.
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { EcranMessages } from "@/components/mark/relation/EcransRelation";

function Contenu() {
    const fil = Number(useSearchParams().get("fil"));
    return <EcranMessages fil={Number.isInteger(fil) && fil > 0 ? fil : null} />;
}

export default function Page() {
    return (
        <Suspense>
            <Contenu />
        </Suspense>
    );
}
