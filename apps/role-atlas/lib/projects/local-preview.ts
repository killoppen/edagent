import type { ProjectActor } from "./lifecycle";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

export function isLocalPreviewRequest(request: Request) {
  if (process.env.NODE_ENV === "production") return false;
  if (process.env.ROLE_ATLAS_LOCAL_MANAGEMENT === "false") return false;
  return LOCAL_HOSTS.has(new URL(request.url).hostname);
}

export function localPreviewActor(request: Request): ProjectActor | null {
  return isLocalPreviewRequest(request) ? { subjectId: "role-atlas:local-preview", role: "admin" } : null;
}
