"use client";

// [.mark] U3 septies (E78) : la fiche d'un client (messages et demandes, notes internes, technique, entrées au portail).
import { notFound, useParams } from "next/navigation";

import { FicheClient } from "@/components/mark/relation/EcransRelation";

export default function Page() {
    const id = Number(useParams<{ id: string }>().id);
    if (!Number.isInteger(id) || id <= 0) notFound();
    return <FicheClient id={id} />;
}
