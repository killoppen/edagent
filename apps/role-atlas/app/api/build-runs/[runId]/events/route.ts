import { getBuildRunStatus, getProjectWorkspace, listBuildEvents } from "@/lib/projects/repository";
import { mayViewProject } from "@/lib/projects/lifecycle";
import { projectActor } from "@/lib/projects/lifecycle-api";

export const runtime = "edge";

export async function GET(request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    const search = new URL(request.url).searchParams;
    const projectId = search.get("projectId");
    if (!projectId) return Response.json({ error: "缺少项目标识。" }, { status: 400 });
    const actor = await projectActor(request);
    if (actor instanceof Response) return actor;
    const workspace = await getProjectWorkspace(projectId);
    if (!workspace) return Response.json({ error: "项目不存在。" }, { status: 404 });
    if (!mayViewProject(workspace.project.ownerSubjectId, actor)) return Response.json({ error: "无权读取此项目的构建事件。" }, { status: 403 });
    const after = Number(search.get("after") || -1);
    const events = await listBuildEvents(projectId, runId, Number.isFinite(after) ? after : -1);
    const status = await getBuildRunStatus(projectId, runId);
    if (!status) return Response.json({ error: "构建运行不存在。" }, { status: 404 });
    return Response.json({ events, status: status.status, done: ["completed", "failed", "cancelled"].includes(status.status) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "构建事件读取失败。" }, { status: 500 });
  }
}
