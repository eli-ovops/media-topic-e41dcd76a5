"""Bounded fixture checks; never acts on the real production state or platforms."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Q = ROOT / "门禁验证"
Q.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location("gate", ROOT / "workflow_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
data = Q / "fixture-input.txt"
data.write_text("SIMULATION ONLY: source v1\n")
registry = {"stages": [{"id": f"{n:02d}", "thread_id": f"fixture-owner-{n}"} for n in range(1, 9)]}
base = {"version": "TEST_FIXTURE", "active_content_id": "SIMULATION", "pmo_thread_id": gate.PMO,
        "runs": {"SIMULATION": {"current_stage": "02", "publication_authorization": None,
        "stages": {f"{n:02d}": {"status": "WAITING", "inputs": [], "outputs": [], "review": None} for n in range(1, 9)}}}}
base["runs"]["SIMULATION"]["stages"]["01"].update(status="PASSED", outputs=gate.snapshot([data]))
base["runs"]["SIMULATION"]["stages"]["02"].update(status="RELEASED", inputs=gate.snapshot([data]))
results = []


def expect(name, state, content, stage, owner, expected=None):
    try:
        gate.check(state, registry, content, stage, owner)
        observed = "ALLOW"
    except ValueError as exc:
        observed = str(exc)
    wanted = expected or "ALLOW"
    results.append({"case": name, "expected": wanted, "observed": observed, "passed": wanted == observed})


expect("valid sequential release", base, "SIMULATION", "02", "fixture-owner-2")
expect("another content", base, "OTHER", "02", "fixture-owner-2", "ACTIVE_CONTENT_MISMATCH_OR_UNASSIGNED")
expect("skip directly to 03", base, "SIMULATION", "03", "fixture-owner-3", "STAGE_OUT_OF_ORDER")
expect("wrong owner", base, "SIMULATION", "02", "fixture-owner-3", "OWNER_MISMATCH_OR_UNASSIGNED")
x = copy.deepcopy(base)
x["runs"]["SIMULATION"]["stages"]["02"]["status"] = "WAITING"
expect("waiting is not release", x, "SIMULATION", "02", "fixture-owner-2", "STAGE_NOT_RELEASED")
x = copy.deepcopy(base)
x["runs"]["SIMULATION"]["stages"]["01"]["status"] = "SUBMITTED"
expect("self-submission is not upstream PASS", x, "SIMULATION", "02", "fixture-owner-2", "UPSTREAM_NOT_PASSED")
data.write_text("SIMULATION ONLY: changed source\n")
expect("changed frozen upstream", base, "SIMULATION", "02", "fixture-owner-2", "UPSTREAM_VERSION_CHANGED")
data.write_text("SIMULATION ONLY: source v1\n")
x = copy.deepcopy(base)
x["runs"]["SIMULATION"]["stages"]["02"]["inputs"][0]["sha256"] = "invalid"
expect("changed released input", x, "SIMULATION", "02", "fixture-owner-2", "RELEASED_INPUT_VERSION_CHANGED")
x = copy.deepcopy(base)
r = x["runs"]["SIMULATION"]
r["current_stage"] = "07"
for n in range(1, 7):
    r["stages"][f"{n:02d}"].update(status="PASSED", outputs=gate.snapshot([data]))
r["stages"]["07"].update(status="RELEASED", inputs=gate.snapshot([data]))
expect("publication without human specific authorization", x, "SIMULATION", "07", "fixture-owner-7", "SPECIFIC_PUBLICATION_AUTHORIZATION_MISSING")
auth = {"human_source": "FICTIONAL FIXTURE ONLY", "platforms": ["fixture"], "accounts": ["fixture"],
        "video_sha256": "wrong-version", "actions": ["fixture"], "visibility": "fixture", "time": "fixture"}
r["publication_authorization"] = auth
expect("publication authorization for another version", x, "SIMULATION", "07", "fixture-owner-7", "PUBLICATION_VERSION_NOT_APPROVED")

# CLI rollback fixture checks invalidation without touching actual workflow files.
state_path, registry_path, review_path = Q / "state.fixture.json", Q / "registry.fixture.json", Q / "review.fixture.json"
state_path.write_text(json.dumps(x))
registry_path.write_text(json.dumps(registry))
review_path.write_text(json.dumps({"fixture": True, "change": "rollback to 04"}))
cmd = [sys.executable, str(ROOT / "workflow_gate.py"), "rollback", "--state", str(state_path),
       "--registry", str(registry_path), "--content", "SIMULATION", "--stage", "04", "--pmo", gate.PMO,
       "--review", str(review_path)]
proc = subprocess.run(cmd, capture_output=True, text=True)
rolled = json.loads(state_path.read_text())["runs"]["SIMULATION"]
good = proc.returncode == 0 and rolled["current_stage"] == "04" and not rolled["publication_authorization"]
good = good and all(rolled["stages"][f"{n:02d}"]["status"] == "WAITING" for n in range(4, 9))
results.append({"case": "rollback invalidates downstream and clears authorization", "passed": good, "cli_output": proc.stdout})
report = {"scope": "pure local fixtures; no actual business release/publication/remote calls", "cases": results,
          "passed": all(x["passed"] for x in results), "fixture_files_retained": [str(data), str(state_path), str(registry_path), str(review_path)]}
(Q / "结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"cases": len(results), "passed": report["passed"]}))
assert report["passed"]
