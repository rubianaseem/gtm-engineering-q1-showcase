"""Step 6. Lifecycle check: normalise the stage, only ever move it forward, flag custom values.

Pattern from lifecycle-stage-audit-agent. A form fill must never pull an Opportunity back to Lead.
"""


def normalise_stage(value, policy):
    v = " ".join((value or "").strip().lower().split())
    if not v:
        return "", True
    for stage, aliases in policy["lifecycle_aliases"].items():
        if v in aliases:
            return stage, True
    return value, False  # custom value inside the native property


def decide_stage(crm_value, proposed, policy):
    """Return (stage to write or '' to leave alone, note or None, blocking reason or None)."""
    order = policy["lifecycle_order"]
    current, known = normalise_stage(crm_value, policy)
    if not known:
        return "", None, "UNKNOWN_LIFECYCLE_VALUE"
    if not current:
        return proposed, None, None
    if order.index(proposed) > order.index(current):
        return proposed, "LIFECYCLE_MOVED_FORWARD", None
    return "", "LIFECYCLE_KEPT_NO_BACKWARD_MOVE", None
