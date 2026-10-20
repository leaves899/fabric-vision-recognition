from __future__ import annotations


def _status(value: object, default: str = "NOT_AVAILABLE") -> str:
    if isinstance(value, dict):
        value = value.get("status", default)
    return str(value or default)


def summarize_gate3(
    gate2: dict | None,
    overall: dict | None,
    width: dict | None,
    twill: dict | None,
    yarn_advisory: dict | None,
    evidence: dict | None = None,
) -> dict:
    """Aggregate existing quality states without recalculating measurements."""
    gate2_status = _status(gate2)
    density_status = _status(overall)
    width_status = _status(width)
    twill = twill or {}
    yarn_advisory = yarn_advisory or {}
    weave_status = _status(twill.get("weave_status"))
    direction_status = _status(twill.get("direction_status"))
    angle_status = _status(twill.get("angle_status"))
    evidence_status = _status(evidence, "NOT_AVAILABLE") if evidence is not None else "NOT_AVAILABLE"

    core = {
        "gate2_input": gate2_status,
        "density": density_status,
        "width": width_status,
    }
    auxiliary = {
        "twill_direction": direction_status,
        "twill_angle": angle_status,
        "weave": weave_status,
        "yarn_advisory": "REFERENCE_ONLY" if yarn_advisory.get("reference_only") else _status(yarn_advisory),
        "evidence": evidence_status,
    }
    failures: list[str] = []
    warnings: list[str] = []
    for name, status in core.items():
        if status == "FAIL":
            failures.append(f"GATE3_{name.upper()}_FAIL")
        elif status in {"LOW_CONFIDENCE", "NOT_AVAILABLE"}:
            warnings.append(f"GATE3_{name.upper()}_{status}")
    for name, status in auxiliary.items():
        if status in {"LOW_CONFIDENCE", "NOT_AVAILABLE"}:
            warnings.append(f"GATE3_{name.upper()}_{status}")
    warnings.extend(str(reason) for reason in (width or {}).get("reasons", []))
    warnings.extend(str(reason) for reason in twill.get("weave_reasons", []))
    if failures:
        status = "FAIL"
    elif any(value in {"LOW_CONFIDENCE", "NOT_AVAILABLE"} for value in core.values()):
        status = "LOW_CONFIDENCE"
    else:
        status = "PASS"
    return {
        "status": status,
        "publishable": status != "FAIL",
        "core_checks": core,
        "auxiliary_checks": auxiliary,
        "failures": sorted(set(failures)),
        "warnings": sorted(set(warnings)),
        "ground_truth_required_for_accuracy": True,
    }
