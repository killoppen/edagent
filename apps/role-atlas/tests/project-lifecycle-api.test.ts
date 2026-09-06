import assert from "node:assert/strict";
import test from "node:test";
import { isDesktopRequest, isLocalPreviewRequest, localPreviewActor } from "@/lib/projects/local-preview";

const environment = process.env as Record<string, string | undefined>;

test("回环地址的开发预览在无身份桥时使用本地管理员主体", async () => {
  const previousNodeEnv = environment.NODE_ENV;
  const previousBaseUrl = environment.LEARNFLOW_BASE_URL;
  const previousLocalManagement = environment.ROLE_ATLAS_LOCAL_MANAGEMENT;
  try {
    environment.NODE_ENV = "development";
    delete environment.LEARNFLOW_BASE_URL;
    delete environment.ROLE_ATLAS_LOCAL_MANAGEMENT;
    const request = new Request("http://127.0.0.1:3000/api/projects/p1", { headers: { origin: "http://127.0.0.1:3000" } });
    assert.equal(isLocalPreviewRequest(request), true);
    assert.deepEqual(localPreviewActor(request), { subjectId: "role-atlas:local-preview", role: "admin" });
  } finally {
    if (previousNodeEnv === undefined) delete environment.NODE_ENV; else environment.NODE_ENV = previousNodeEnv;
    if (previousBaseUrl === undefined) delete environment.LEARNFLOW_BASE_URL; else environment.LEARNFLOW_BASE_URL = previousBaseUrl;
    if (previousLocalManagement === undefined) delete environment.ROLE_ATLAS_LOCAL_MANAGEMENT; else environment.ROLE_ATLAS_LOCAL_MANAGEMENT = previousLocalManagement;
  }
});

test("生产环境不会启用本地项目管理主体", async () => {
  const previousNodeEnv = environment.NODE_ENV;
  const previousBaseUrl = environment.LEARNFLOW_BASE_URL;
  const previousLocalManagement = environment.ROLE_ATLAS_LOCAL_MANAGEMENT;
  try {
    environment.NODE_ENV = "production";
    delete environment.LEARNFLOW_BASE_URL;
    environment.ROLE_ATLAS_LOCAL_MANAGEMENT = "true";
    const request = new Request("http://127.0.0.1:3000/api/projects/p1", { headers: { origin: "http://127.0.0.1:3000" } });
    assert.equal(isLocalPreviewRequest(request), false);
    assert.equal(localPreviewActor(request), null);
  } finally {
    if (previousNodeEnv === undefined) delete environment.NODE_ENV; else environment.NODE_ENV = previousNodeEnv;
    if (previousBaseUrl === undefined) delete environment.LEARNFLOW_BASE_URL; else environment.LEARNFLOW_BASE_URL = previousBaseUrl;
    if (previousLocalManagement === undefined) delete environment.ROLE_ATLAS_LOCAL_MANAGEMENT; else environment.ROLE_ATLAS_LOCAL_MANAGEMENT = previousLocalManagement;
  }
});

test("桌面管理请求需要显式桌面标记", () => {
  assert.equal(isDesktopRequest(new Request("http://127.0.0.1:3000")), false);
  assert.equal(isDesktopRequest(new Request("http://127.0.0.1:3000", { headers: { "x-role-atlas-desktop": "1" } })), true);
});
