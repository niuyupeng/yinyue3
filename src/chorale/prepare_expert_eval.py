from __future__ import annotations

import argparse
from pathlib import Path

from chorale.generate import generate
from chorale.utils import ensure_dir


RATING_MD = """# Blind Rating Form: Project 1 SATB Harmonization

Project: Explainable Neural-Symbolic Choral Harmonization with Common-Practice Harmony and Counterpoint Constraints

Instructions:

- Rate each anonymized MusicXML example without checking whether it is generated or ground truth.
- Use a 1--5 scale, where 1 = poor and 5 = excellent.
- Add concise comments only when they help explain the score.

| example_id | harmonic correctness | voice-leading correctness | seventh-resolution correctness | cadence quality | singability | stylistic consistency | usefulness for composition pedagogy | overall preference | comments |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| project1_00 |  |  |  |  |  |  |  |  |  |
| project1_01 |  |  |  |  |  |  |  |  |  |
| project1_02 |  |  |  |  |  |  |  |  |  |
| project1_03 |  |  |  |  |  |  |  |  |  |
| project1_04 |  |  |  |  |  |  |  |  |  |
| project1_05 |  |  |  |  |  |  |  |  |  |
| project1_06 |  |  |  |  |  |  |  |  |  |
| project1_07 |  |  |  |  |  |  |  |  |  |
| project1_08 |  |  |  |  |  |  |  |  |  |
| project1_09 |  |  |  |  |  |  |  |  |  |
"""


RATING_CSV_HEADER = (
    "example_id,harmonic_correctness,voice_leading_correctness,seventh_resolution_correctness,"
    "cadence_quality,singability,stylistic_consistency,usefulness_for_composition_pedagogy,"
    "overall_preference,comments\n"
)


def write_rating_forms(output_dir: str | Path = "expert_eval/project1", num_samples: int = 10) -> dict[str, str]:
    output_dir = ensure_dir(output_dir)
    md_path = output_dir / "blind_rating_form_project1.md"
    csv_path = output_dir / "blind_rating_form_project1.csv"
    md_path.write_text(RATING_MD, encoding="utf-8")
    csv_lines = [RATING_CSV_HEADER]
    for idx in range(num_samples):
        csv_lines.append(f"project1_{idx:02d},,,,,,,,,\n")
    csv_path.write_text("".join(csv_lines), encoding="utf-8")
    return {"md": str(md_path), "csv": str(csv_path)}


def prepare_expert_eval_package(
    config_path: str | Path,
    checkpoint_path: str | Path | None,
    output_dir: str | Path = "expert_eval/project1",
    num_samples: int = 10,
) -> dict:
    output_dir = ensure_dir(output_dir)
    outputs = generate(
        config_path=config_path,
        checkpoint_path=checkpoint_path,
        output_dir=output_dir,
        num_samples=num_samples,
        prefix="project1",
    )
    forms = write_rating_forms(output_dir, num_samples=num_samples)
    return {"outputs": outputs, "forms": forms}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare blind expert-evaluation package for Project 1.")
    parser.add_argument("--config", default="configs/chorale_main.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--output-dir", default="expert_eval/project1")
    parser.add_argument("--num-samples", type=int, default=10)
    args = parser.parse_args()
    package = prepare_expert_eval_package(args.config, args.checkpoint, args.output_dir, args.num_samples)
    print(package)


if __name__ == "__main__":
    main()
