from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from chorale.commercial_legal_signoff import build_prefilled_draft
from chorale.dependency_license_inventory import collect_inventory, write_inventory_outputs


DEFAULT_OUT_DIR = "results/project1_commercial_legal_review_packet"


def build_legal_packet(
    out_dir: str | Path = DEFAULT_OUT_DIR,
    *,
    delivery_zip: str | Path = "",
) -> dict[str, object]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    delivery_zip = delivery_zip or latest_delivery_zip()
    release_manifest = latest_release_manifest()
    delivery_zip_sha256 = str(release_manifest.get("zip_sha256", ""))

    inventory = collect_inventory("requirements.txt")
    inventory_outputs = write_inventory_outputs(inventory, out / "dependency_license_inventory.json")

    copied = copy_if_exists("docs/commercial_legal_signoff_template.json", out / "commercial_legal_signoff_TEMPLATE.json")
    copied += copy_if_exists("results/project1_delivery_release_manifest_latest.json", out / "delivery_release_manifest.json")
    copied += copy_if_exists("results/project1_commercial_acceptance_report_latest.md", out / "commercial_acceptance_report.md")
    copied += copy_if_exists("results/project1_playback_license_audit_latest.json", out / "playback_license_audit.json")
    copied += copy_if_exists("results/project1_commercial_delivery_audit_latest.json", out / "commercial_delivery_audit.json")
    copied += copy_if_exists("results/project1_delivery_media_audit_latest.json", out / "delivery_media_audit.json")
    copied += copy_if_exists("results/project1_delivery_conformance_audit_latest.json", out / "delivery_conformance_audit.json")
    copied += copy_if_exists("results/project1_pro_playback_traceability_audit_latest.json", out / "score_audio_traceability_audit.json")
    copied += copy_if_exists("results/project1_commercial_claims_audit_latest.json", out / "commercial_claims_audit.json")
    copied += copy_if_exists("results/project1_review_issue_intake_latest.json", out / "review_issue_intake.json")

    checklist = make_checklist(delivery_zip, inventory)
    prefilled_signoff_path = out / "commercial_legal_signoff_PREFILLED_DRAFT.json"
    prefilled_signoff_path.write_text(
        json.dumps(build_prefilled_draft("."), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    checklist_path = out / "LEGAL_COMMERCIAL_REVIEW_CHECKLIST.md"
    checklist_path.write_text(checklist, encoding="utf-8")
    claims_path = out / "COMMERCIAL_CLAIMS_BOUNDARY.md"
    claims_path.write_text(make_claims_boundary(), encoding="utf-8")
    human_subjects_path = out / "EXPERT_EVALUATION_PRIVACY_NOTE.md"
    human_subjects_path.write_text(make_privacy_note(), encoding="utf-8")

    summary = {
        "schema": "project1_commercial_legal_review_packet_v1",
        "created_at_local": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(out),
        "delivery_zip": str(delivery_zip),
        "delivery_zip_sha256": delivery_zip_sha256,
        "dependency_license_inventory": inventory_outputs,
        "copied_evidence_files": copied,
        "review_files": {
            "checklist": str(checklist_path),
            "claims_boundary": str(claims_path),
            "privacy_note": str(human_subjects_path),
            "signoff_template": str(out / "commercial_legal_signoff_TEMPLATE.json"),
            "prefilled_signoff_draft": str(prefilled_signoff_path),
        },
        "status": "manual review required",
        "note": "This packet organizes evidence for review. It does not approve commercial distribution.",
    }
    (out / "LEGAL_PACKET_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(make_packet_readme(summary), encoding="utf-8")
    return summary


def copy_if_exists(src: str | Path, dst: str | Path) -> list[str]:
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.is_file():
        return []
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    return [str(dst_path)]


def latest_delivery_zip() -> str:
    return str(latest_release_manifest().get("zip_file", ""))


def latest_release_manifest() -> dict[str, object]:
    path = Path("results/project1_delivery_release_manifest_latest.json")
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def make_checklist(delivery_zip: str | Path, inventory: dict[str, object]) -> str:
    unknown = inventory.get("unknown_license_count")
    return f"""# Project1 Legal and Commercial Review Checklist

Delivery ZIP under review:

```text
{delivery_zip}
```

Delivery ZIP SHA256:

```text
{latest_release_manifest().get("zip_sha256", "")}
```

## Required Manual Checks

- [ ] Dataset and generated score rights reviewed.
- [ ] music21 Bach chorale usage and redistribution context reviewed.
- [ ] Generated MusicXML/PDF/MP3/MIDI redistribution scope approved.
- [ ] SoundFont notices and included third-party notice files reviewed.
- [ ] Delivery conformance audit reviewed for MusicXML/MIDI pitch matching and MP3 audible signal checks.
- [ ] Playback tool chain reviewed: MuseScore/FluidSynth/FFmpeg are not redistributed in the delivery ZIP.
- [ ] Python dependency license inventory reviewed.
- [ ] Unknown dependency license metadata reviewed manually. Current unknown count: `{unknown}`.
- [ ] Expert evaluation privacy/human-subject expectations reviewed.
- [ ] Returned reviewer issue intake report reviewed, including invalid or unmatched issue rows if present.
- [ ] Commercial claims reviewed against actual evidence.
- [ ] Automated commercial claims audit reviewed.
- [ ] Any excluded uses are written into the final signoff.

## Signoff Rule

Do not create `results/project1_commercial_legal_signoff.json` with
`approved_for_commercial_distribution: true` until the above checks have been completed by a responsible reviewer.
"""


def make_claims_boundary() -> str:
    return """# Project1 Commercial Claims Boundary

## Supported Claims

- Score-level SATB choral harmonization system.
- Outputs MusicXML/PDF score-level materials and score-derived MP3/MIDI listening aids.
- Includes automatic common-practice rule reports, score-audio traceability audits, and score-playback conformance checks.
- Delivery package passed engineering integrity checks in this repository.

## Claims Not Supported Without Additional Evidence

- Do not claim human-level composition quality without completed expert evaluation.
- Do not claim legal approval until `results/project1_commercial_legal_signoff.json` is completed by a real reviewer.
- Do not claim audio-generation capability; playback files are rendered from notation.
- Do not claim real choral/vocal production quality.
- Do not claim all generated harmonizations are musically optimal.
"""


def make_privacy_note() -> str:
    return """# Expert Evaluation Privacy Note

The expert evaluation workflow collects reviewer background fields and score ratings.

Before commercial or publication use, review whether local institutional, privacy, consent, or human-subject requirements apply. Store returned rating workbooks in `expert_eval/project1/returned_ratings` and avoid publishing personally identifying reviewer details unless explicit permission is obtained.
"""


def make_packet_readme(summary: dict[str, object]) -> str:
    return f"""# Project1 Commercial Legal Review Packet

Status: `{summary['status']}`

This folder collects evidence for a real commercial/legal review. It does not approve commercial redistribution by itself.

Start with:

1. `LEGAL_COMMERCIAL_REVIEW_CHECKLIST.md`
2. `COMMERCIAL_CLAIMS_BOUNDARY.md`
3. `dependency_license_inventory.md`
4. `playback_license_audit.json`
5. `delivery_release_manifest.json`
6. `review_issue_intake.json`
7. `commercial_legal_signoff_TEMPLATE.json`
8. `commercial_legal_signoff_PREFILLED_DRAFT.json`

If review is approved, copy the completed signoff to:

```text
results/project1_commercial_legal_signoff.json
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Project1 commercial/legal review packet.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--delivery-zip", default="")
    args = parser.parse_args()
    summary = build_legal_packet(args.out_dir, delivery_zip=args.delivery_zip)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
