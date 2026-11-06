import { PageInvitation } from "./PageInvitation";

export const dynamic = "force-dynamic";

export default async function Page({ searchParams }: { searchParams: Promise<{ jeton?: string }> }) {
    const { jeton } = await searchParams;
    return <PageInvitation jeton={jeton ?? ""} />;
}
