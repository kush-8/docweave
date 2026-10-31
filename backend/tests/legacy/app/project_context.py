import json
from uuid import uuid4


def context_payload(body):
    context = body.model_dump(mode="json", exclude_unset=True, exclude={"expected_revision", "stack_review_id"})
    if "stack" in context:
        context["stack"] = [{"id": str(uuid4()), "technology": dep.technology, "declared_version": None,
            "resolved_version": None, "docs_target": dep.docs_target} for dep in body.stack]
    return json.dumps(context)
