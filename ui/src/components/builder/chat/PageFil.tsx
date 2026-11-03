"use client";

import { useParams } from "next/navigation";

import { FilDuBuilder } from "./FilDuBuilder";

export default function PageFil() {
    const { fil } = useParams<{ fil: string }>();
    const id = Number(fil);
    return Number.isFinite(id) ? <FilDuBuilder filId={id} /> : null;
}
