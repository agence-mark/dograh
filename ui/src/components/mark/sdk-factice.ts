/**
 * [.mark] The mock of `@/client/sdk.gen` for our screen tests (chantier l-agent-travaille,
 * CI of 07/10: 43 unhandled errors).
 *
 * A test lists the routes it plays; the screens it renders also call routes it does not
 * care about, and every new route of the server used to break the tests that render them
 * (« No "…" export is defined on the mock »). Here every function of the real SDK exists,
 * answering « nothing » ({ data: undefined }), and the test's own routes replace them:
 *
 *     vi.mock("@/client/sdk.gen", async (importOriginal) =>
 *         (await import("./sdk-factice")).sdkFactice(await importOriginal(), { …the test's routes }),
 *     );
 */
import { vi } from "vitest";

export function sdkFactice<T extends object>(original: unknown, propres: T): Record<string, unknown> & T {
    const neutre: Record<string, unknown> = {};
    for (const [nom, valeur] of Object.entries(original as Record<string, unknown>)) {
        if (typeof valeur === "function") neutre[nom] = vi.fn(async () => ({ data: undefined, error: undefined }));
    }
    return { ...neutre, ...propres };
}
