"""Sequential content workflow guard. This is an orchestration check, not OS isolation."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PMO = "01a11194-c40d-7bf0-8396-5bb5d6449444"
PASS = {"PASSED", "IMPORTED_VERIFIED_BASELINE"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ensure(condition, reason):
    if not condition:
        raise ValueError(reason)


def snapshot(paths):
    return [{"path": str(Path(p).resolve()), "sha256": sha(p)} for p in paths]


def intact(files):
    return all(Path(x["path"]).is_file() and sha(x["path"]) == x["sha256"] for x in files)


def check(state, registry, content_id, stage, thread_id):
    ensure(state["active_content_id"] == content_id, "ACTIVE_CONTENT_MISMATCH_OR_UNASSIGNED")
    run = state["runs"][content_id]
    ensure(run["current_stage"] == stage, "STAGE_OUT_OF_ORDER")
    owner = next(x for x in registry["stages"] if x["id"] == stage)
    ensure(owner["thread_id"] == thread_id and thread_id, "OWNER_MISMATCH_OR_UNASSIGNED")
    row = run["stages"][stage]
    ensure(row["status"] == "RELEASED", "STAGE_NOT_RELEASED")
    for previous in range(1, int(stage)):
        prev = run["stages"][f"{previous:02d}"]
        ensure(prev["status"] in PASS, "UPSTREAM_NOT_PASSED")
        ensure(intact(prev["outputs"]), "UPSTREAM_VERSION_CHANGED")
    ensure(intact(row["inputs"]), "RELEASED_INPUT_VERSION_CHANGED")
    if stage == "07":
        auth = run.get("publication_authorization") or {}
        required = ["human_source", "platforms", "accounts", "video_sha256", "actions", "visibility", "time"]
        ensure(all(auth.get(k) for k in required), "SPECIFIC_PUBLICATION_AUTHORIZATION_MISSING")
        ensure(auth["video_sha256"] in [x["sha256"] for x in row["inputs"]], "PUBLICATION_VERSION_NOT_APPROVED")
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["status", "check", "start", "import-baseline", "release", "approve", "rollback"])
    ap.add_argument("--state", type=Path, default=ROOT / "流程状态.json")
    ap.add_argument("--registry", type=Path, default=ROOT / "会话登记.json")
    ap.add_argument("--content")
    ap.add_argument("--stage")
    ap.add_argument("--thread")
    ap.add_argument("--pmo")
    ap.add_argument("--authorization-source")
    ap.add_argument("--input", action="append", default=[])
    ap.add_argument("--output", action="append", default=[])
    ap.add_argument("--review", type=Path)
    args = ap.parse_args()
    state = json.loads(args.state.read_text())
    registry = json.loads(args.registry.read_text())
    if args.action == "status":
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    if args.action == "check":
        check(state, registry, args.content, args.stage, args.thread)
        print(json.dumps({"allowed": True, "content": args.content, "stage": args.stage}))
        return
    ensure(args.pmo == PMO == state["pmo_thread_id"], "PMO_ONLY_STATE_MUTATION")
    if args.action == "start":
        ensure(not state["active_content_id"], "ANOTHER_CONTENT_IS_ACTIVE")
        ensure(args.content and args.content not in state["runs"], "CONTENT_ID_MISSING_OR_DUPLICATE")
        ensure(args.authorization_source, "BUSINESS_SCOPE_AUTHORIZATION_SOURCE_REQUIRED")
        state["runs"][args.content] = {
            "scope_authorization_source": args.authorization_source,
            "current_stage": "01", "publication_authorization": None,
            "stages": {f"{n:02d}": {"status": "WAITING", "inputs": [], "outputs": [], "review": None} for n in range(1, 9)},
        }
        state["active_content_id"] = args.content
    else:
        ensure(state["active_content_id"] == args.content, "ACTIVE_CONTENT_MISMATCH")
        run = state["runs"][args.content]
        ensure(args.stage in run["stages"], "INVALID_STAGE")
        row = run["stages"][args.stage]
        if args.action == "import-baseline":
            ensure(int(args.stage) <= 4, "BASELINE_IMPORT_CANNOT_SKIP_VISUAL_OR_PUBLICATION_GATES")
            ensure(args.review and args.review.is_file(), "EXISTING_CONTENT_BASELINE_REVIEW_REQUIRED")
            review = json.loads(args.review.read_text())
            ensure(review.get("pmo_thread_id") == PMO and review.get("decision") == "PASS_BASELINE_ONLY", "BASELINE_REVIEW_NOT_AUTHORIZED")
            ensure(review.get("content_id") == args.content and review.get("target_stage") == args.stage, "BASELINE_TARGET_MISMATCH")
            ensure(run["current_stage"] == "01" and all(x["status"] == "WAITING" for x in run["stages"].values()), "BASELINE_IMPORT_ONLY_BEFORE_NEW_WORK")
            ensure(review.get("human_change_source") and review.get("preserved_scope") and review.get("known_defects"), "BASELINE_SCOPE_OR_CHANGE_EVIDENCE_MISSING")
            for n in range(1, int(args.stage)):
                sid = f"{n:02d}"
                files = review.get("prior_stage_evidence", {}).get(sid, [])
                ensure(files and intact(files), "BASELINE_EVIDENCE_MISSING_OR_CHANGED")
                run["stages"][sid].update(status="IMPORTED_VERIFIED_BASELINE", outputs=files, review=snapshot([args.review])[0])
            run["current_stage"] = args.stage
            run["baseline_import_note"] = "Existing unchanged inputs accepted now; not a fabricated historic stage approval."
        elif args.action == "release":
            ensure(run["current_stage"] == args.stage, "STAGE_OUT_OF_ORDER")
            ensure(row["status"] == "WAITING", "STAGE_ALREADY_RELEASED_OR_COMPLETE")
            ensure(args.input, "EXPLICIT_INPUT_FILES_REQUIRED")
            row["inputs"] = snapshot(args.input)
            row["status"] = "RELEASED"
            owner = next(x for x in registry["stages"] if x["id"] == args.stage)
            check(state, registry, args.content, args.stage, owner["thread_id"])
        elif args.action == "approve":
            ensure(run["current_stage"] == args.stage and row["status"] == "RELEASED", "NO_CURRENT_RELEASED_STAGE")
            owner = next(x for x in registry["stages"] if x["id"] == args.stage)
            check(state, registry, args.content, args.stage, owner["thread_id"])
            ensure(args.review and args.review.is_file() and args.output, "ACTUAL_PMO_REVIEW_AND_OUTPUT_REQUIRED")
            ensure(intact(row["inputs"]), "RELEASED_INPUT_VERSION_CHANGED")
            review = json.loads(args.review.read_text())
            ensure(review.get("pmo_thread_id") == PMO and review.get("decision") == "PASS", "PMO_REVIEW_NOT_PASS")
            ensure(review.get("content_id") == args.content and review.get("stage") == args.stage, "REVIEW_TARGET_MISMATCH")
            ensure(review.get("evidence_read") and review.get("remaining_required_work") == [], "NECESSARY_REVIEW_INCOMPLETE")
            if args.stage == "05":
                ensure(review.get("human_review_source"), "HUMAN_FINAL_REVIEW_REQUIRED")
            row.update(status="PASSED", outputs=snapshot(args.output), review=snapshot([args.review])[0])
            run["current_stage"] = f"{int(args.stage) + 1:02d}" if args.stage != "08" else "COMPLETE"
            if args.stage == "08":
                state["active_content_id"] = None
        elif args.action == "rollback":
            ensure(args.review and args.review.is_file(), "CHANGE_SCOPE_REVIEW_REQUIRED")
            ensure(int(args.stage) <= min(int(run["current_stage"]) if run["current_stage"].isdigit() else 8, 8), "ROLLBACK_CANNOT_SKIP_FORWARD")
            run.setdefault("history", []).append({"rollback_stage": args.stage, "review": snapshot([args.review])[0], "previous_stages": run["stages"].copy()})
            for n in range(int(args.stage), 9):
                run["stages"][f"{n:02d}"] = {"status": "WAITING", "inputs": [], "outputs": [], "review": None}
            run["current_stage"] = args.stage
            run["publication_authorization"] = None
    args.state.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"saved": True, "active_content": state["active_content_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, StopIteration) as exc:
        print(json.dumps({"allowed": False, "reason": str(exc)}, ensure_ascii=False))
        sys.exit(2)
