import { getConversation, getProjectWorkspace } from "@/lib/projects/repository";
import { mayViewProject } from "@/lib/projects/lifecycle";
import { isLocalPreviewRequest, manageProject, projectActor } from "@/lib/projects/lifecycle-api";

export const runtime = "edge";

export async function DELETE(request: Request, context: { params: Promise<{ projectId: string }> }) {
  return manageProject(request, (await context.params).projectId, "delete");
}

export async function PATCH(request: Request, context: { params: Promise<{ projectId: string }> }) {
  try {
    const input = await request.json() as { action?: unknown };
    if (input.action !== "restore") return Response.json({ error: "仅支持 restore 操作。" }, { status: 400 });
    return manageProject(request, (await context.params).projectId, "restore");
  } catch { return Response.json({ error: "请求格式不正确。" }, { status: 400 }); }
}

export async function GET(request: Request, context: { params: Promise<{ projectId: string }> }) {
  try {
    const { projectId } = await context.params;
    const actor = process.env.LEARNFLOW_BASE_URL || isLocalPreviewRequest(request) ? await projectActor(request) : null;
    if (actor instanceof Response) return actor;
    const conversationId = new URL(request.url).searchParams.get("conversation");
    const conversation = conversationId ? await getConversation(conversationId) : null;
    if (conversationId && (!conversation || conversation.conversation.projectId !== projectId)) {
      return Response.json({ error: "项目会话不存在。" }, { status: 404 });
    }
    const workspace = conversation?.workspace || await getProjectWorkspace(projectId);
    if (!workspace) return Response.json({ error: "项目不存在。" }, { status: 404 });
    if (actor && !mayViewProject(workspace.project.ownerSubjectId, actor)) {
      return Response.json({ error: "只有项目所有者或管理员可以读取此项目。" }, { status: 403 });
    }
    return Response.json(workspace);
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "项目读取失败。" }, { status: 500 });
  }
}
