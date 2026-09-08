// [.mark] Hand-written client for the organization membership routes.
//
// It does NOT live in src/client/, and that is deliberate: everything under
// src/client/ is regenerated from a running backend's openapi.json, so a
// generated function for these routes only appears once someone runs
// `npm run generate-client` against a backend carrying the .mark patch. Until
// then a generated call would be silently dropped by the next regeneration.
// This module goes through the same client instance, so base URL resolution
// and the auth interceptor apply exactly as they do to generated calls.
//
// When the generated SDK does carry these routes, this file becomes redundant
// and should be deleted rather than kept alongside them.
import { client } from "@/client/client.gen";
import { detailFromError } from "@/lib/apiError";

export interface Organization {
  id: number;
  provider_id: string;
  is_selected: boolean;
}

interface OrganizationListResponse {
  organizations: Organization[];
}

export async function listOrganizations(): Promise<Organization[]> {
  const { data, error } = await client.get<OrganizationListResponse>({
    url: "/api/v1/organizations",
  });
  if (error || !data) {
    throw new Error(detailFromError(error, "Failed to list organizations"));
  }
  return data.organizations;
}

export async function createOrganization(
  providerId: string,
  options: { select?: boolean } = {},
): Promise<Organization> {
  const { data, error, response } = await client.post<Organization>({
    url: "/api/v1/organizations",
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
  const { data, error } = await client.put<Organization>({
    url: "/api/v1/organizations/selected",
    body: { organization_id: organizationId },
  });
  if (error || !data) {
    throw new Error(detailFromError(error, "Failed to switch organization"));
  }
  return data;
}
