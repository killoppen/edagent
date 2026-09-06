export type ProjectActor = { subjectId: string; role: "user" | "admin" };

export function mayManageProject(ownerSubjectId: string | null, actor: ProjectActor) {
  return actor.role === "admin" || Boolean(ownerSubjectId && ownerSubjectId === actor.subjectId);
}

export function mayViewProject(ownerSubjectId: string | null, actor: ProjectActor) {
  return actor.role === "admin" || Boolean(ownerSubjectId && ownerSubjectId === actor.subjectId);
}

export function projectLifecycleStatements(d1: D1Database, input: { projectId: string; actor: ProjectActor; action: "delete" | "restore"; now: string }) {
  const { projectId, actor, action, now } = input;
  const restoring = action === "restore";
  const statements = [
    d1.prepare(`UPDATE projects SET deleted_at=?, deleted_by=?, updated_at=?
      WHERE id=? AND (owner_subject_id=? OR ?='admin') AND deleted_at IS ${restoring ? "NOT " : ""}NULL`)
      .bind(restoring ? null : now, restoring ? null : actor.subjectId, now, projectId, actor.subjectId, actor.role),
    d1.prepare(`INSERT INTO project_version_events(project_id, version_id, action, actor_kind, detail_json, created_at)
      SELECT ?, NULL, ?, 'user', ?, ? WHERE changes()>0`)
      .bind(projectId, restoring ? "project.restored" : "project.deleted", JSON.stringify({ subjectId: actor.subjectId, recoverable: true }), now),
  ];
  if (!restoring) {
    // Cancel work and revoke leases in the same transaction. Artifacts/releases/history are untouched.
    for (const table of ["build_runs", "risk_runs", "snapshot_risk_runs", "snapshot_iteration_runs", "workspace_ingestion_runs"]) {
      statements.push(d1.prepare(`UPDATE ${table} SET status='cancelled', error='PROJECT_DELETED', completed_at=?
        WHERE project_id=? AND status='running' AND EXISTS (SELECT 1 FROM projects WHERE id=? AND deleted_at IS NOT NULL AND (owner_subject_id=? OR ?='admin'))`)
        .bind(now, projectId, projectId, actor.subjectId, actor.role));
    }
    statements.push(d1.prepare(`UPDATE role_jobs SET status='cancelled', lease_owner=NULL, lease_expires_at=NULL,
      error='PROJECT_DELETED', completed_at=?, updated_at=? WHERE project_id=? AND status IN ('queued','running','waiting_user')
      AND EXISTS (SELECT 1 FROM projects WHERE id=? AND deleted_at IS NOT NULL AND (owner_subject_id=? OR ?='admin'))`)
      .bind(now, now, projectId, projectId, actor.subjectId, actor.role));
  }
  return statements;
}

export function projectPurgeStatements(d1: D1Database, input: { projectId: string; actor: ProjectActor }) {
  const { projectId, actor } = input;
  const guard = "WHERE project_id=? AND EXISTS (SELECT 1 FROM projects WHERE id=? AND (owner_subject_id=? OR ?='admin'))";
  const statements = [
    d1.prepare(`DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE project_id=? )`).bind(projectId),
    d1.prepare(`DELETE FROM build_events ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM risk_events ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM risk_issues ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM risk_patches ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM snapshot_risk_events WHERE run_id IN (SELECT id FROM snapshot_risk_runs WHERE project_id=? )`).bind(projectId),
    d1.prepare(`DELETE FROM snapshot_iteration_events WHERE run_id IN (SELECT id FROM snapshot_iteration_runs WHERE project_id=? )`).bind(projectId),
    d1.prepare(`DELETE FROM workspace_ingestion_events WHERE run_id IN (SELECT id FROM workspace_ingestion_runs WHERE project_id=? )`).bind(projectId),
    d1.prepare(`DELETE FROM project_tags ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM semantic_diffs ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM project_version_events ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM role_jobs ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM risk_runs ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM snapshot_risk_runs WHERE project_id=?`).bind(projectId),
    d1.prepare(`DELETE FROM snapshot_iteration_runs WHERE project_id=?`).bind(projectId),
    d1.prepare(`DELETE FROM workspace_ingestion_runs WHERE project_id=?`).bind(projectId),
    d1.prepare(`DELETE FROM project_versions ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM build_runs ${guard}`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM conversations WHERE project_id=? AND EXISTS (SELECT 1 FROM projects WHERE id=? AND (owner_subject_id=? OR ?='admin'))`).bind(projectId, projectId, actor.subjectId, actor.role),
    d1.prepare(`DELETE FROM projects WHERE id=? AND (owner_subject_id=? OR ?='admin')`).bind(projectId, actor.subjectId, actor.role),
  ];
  return statements;
}
