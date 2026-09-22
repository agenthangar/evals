"""Authoring checks, deliberately separate from empirical grader calibration."""
from bench.task import Task


def audit(task: Task) -> list[str]:
    issues = []
    if not task.criteria:
        issues.append("map behavioral acceptance criteria to grading checks")
    covered = {c['check'] for c in task.criteria}
    if covered != {c.id for c in task.grading_checks}:
        issues.append("every grading check needs a documented acceptance criterion")
    if not task.negative_controls:
        issues.append("add a plausible wrong solution as a negative control")
    if not task.provenance.get("source") or not task.provenance.get("why_this_task"):
        issues.append("record provenance.source and provenance.why_this_task")
    if not task.limitations:
        issues.append("document evaluation limitations (what this task cannot establish)")
    return issues
