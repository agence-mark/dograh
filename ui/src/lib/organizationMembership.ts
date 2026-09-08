// [.mark] Thin wrapper over the generated organization membership SDK.
//
// This module used to build the requests by hand, because src/client/ is
// regenerated from a running backend's openapi.json and did not yet carry the
// .mark routes. It does now, so the URLs live in exactly one place again: a
// second hand-written copy is the one that eventually drifts.
//
// What is left here is the part the generated SDK cannot express: turning a
// typed transport result into the message a user should read, in particular
// the 409 that tells them the identifier is taken.
import {
  createOrganizationApiV1OrganizationsPost,
  listOrganizationsApiV1OrganizationsGet,
  selectOrganizationApiV1OrganizationsSelectedPut,
} from "@/client/sdk.gen";
import type { OrganizationSummary } from "@/client/types.gen";
import { detailFromError } from "@/lib/apiError";

export type Organization = OrganizationSummary;

export async function listOrganizations(): Promise<Organization[]> {
  const { data, error } = await listOrganizationsApiV1OrganizationsGet();
  if (error || !data) {
    throw new Error(detailFromError(error, "Failed to list organizations"));
  }
  return data.organizations;
}

export async function createOrganization(
  providerId: string,
  options: { select?: boolean } = {},
): Promise<Organization> {
  const { data, error, response } = await createOrganizationApiV1OrganizationsPost({
    body: { provider_id: providerId, select: options.select ?? false },
  });
  if (error || !data) {
    // 409 is the one failure a user can act on, so it gets a message written
    // for them rather than whatever the backend put in `detail`.
    throw new Error(
      response?.status === 409
        ? "An organization with this identifier already exists"
        : detailFromError(error, "Failed to create the organization"),
    );
  }
  return data;
}

export async function selectOrganization(
  organizationId: number,
): Promise<Organization> {
  const { data, error } = await selectOrganizationApiV1OrganizationsSelectedPut({
    body: { organization_id: organizationId },
  });
  if (error || !data) {
    throw new Error(detailFromError(error, "Failed to switch organization"));
  }
  return data;
}
