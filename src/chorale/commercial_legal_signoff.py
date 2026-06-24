from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chorale.commercial_readiness_audit import legal_signoff_is_complete


DEFAULT_TEMPLATE = "docs/commercial_legal_signoff_template.json"
DEFAULT_DRAFT = "results/project1_commercial_legal_signoff_DRAFT.json"
DEFAULT_FINAL = "results/project1_commercial_legal_signoff.json"
DEFAULT_VALIDATION = "results/project1_commercial_legal_signoff_validation_latest.json"


def build_prefilled_draft(
    root: str | Path = ".",
    *,
    template_path: str | Path = DEFAULT_TEMPLATE,
) -> dict[str, Any]:
    root_path = Path(root)
    template = read_json(root_path / template_path)
    release = read_release(root_path)
    draft: dict[str, Any] = dict(template)
    draft["approved_for_commercial_distribution"] = False
    draft["delivery_zip"] = str(release.get("zip_file", ""))
    draft["delivery_zip_sha256"] = str(release.get("zip_sha256", ""))
    draft["created_from_release_manifest_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    draft["draft_status"] = "manual_review_required_not_approved"
    draft["notes"] = (
        "Prefilled draft only. Keep approved_for_commercial_distribution=false until a real "
        "legal/commercial reviewer completes every required check and signs the final file."
    )
    return draft


def validate_signoff(
    root: str | Path = ".",
    *,
    signoff_path: str | Path = DEFAULT_FINAL,
) -> dict[str, Any]:
    root_path = Path(root)
    release = read_release(root_path)
    path = root_path / signoff_path
    signoff = read_json(path)
    if not path.is_file():
        problems = [f"signoff file missing: {signoff_path}"]
        complete = False
    else:
        complete, problems = legal_signoff_is_complete(signoff, release)
    return {
        "schema": "project1_commercial_legal_signoff_validation_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signoff_path": str(signoff_path),
        "release_zip": release.get("zip_file", ""),
        "release_zip_sha256": release.get("zip_sha256", ""),
        "approved_for_commercial_distribution": signoff.get("approved_for_commercial_distribution"),
        "ready_for_commercial_release_gate": complete,
        "status": "pass" if complete else "blocked",
        "problems": problems,
    }


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def read_release(root: Path) -> dict[str, Any]:
    release = read_json(root / "results" / "project1_delivery_release_manifest_latest.json")
    return release if release else {}


def read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or validate Project1 commercial legal signoff files.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--write-draft", action="store_true", help="Write a prefilled unapproved legal signoff draft.")
    parser.add_argument("--draft-out", default=DEFAULT_DRAFT)
    parser.add_argument("--validate", action="store_true", help="Validate a final signoff JSON against the current release manifest.")
    parser.add_argument("--signoff-path", default=DEFAULT_FINAL)
    parser.add_argument("--validation-out", default=DEFAULT_VALIDATION)
    args = parser.parse_args()

    outputs: dict[str, str] = {}
    payload: dict[str, Any] = {"schema": "project1_commercial_legal_signoff_cli_v1"}
    if args.write_draft:
        draft = build_prefilled_draft(args.root)
        outputs["draft"] = str(write_json(draft, Path(args.root) / args.draft_out))
        payload["draft"] = draft
    if args.validate:
        validation = validate_signoff(args.root, signoff_path=args.signoff_path)
        outputs["validation"] = str(write_json(validation, Path(args.root) / args.validation_out))
        payload["validation"] = validation
    if not args.write_draft and not args.validate:
        draft = build_prefilled_draft(args.root)
        outputs["draft"] = str(write_json(draft, Path(args.root) / args.draft_out))
        payload["draft"] = draft
    payload["outputs"] = outputs
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
