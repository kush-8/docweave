"""Offline robots decisions with the same agent/parser/status policy as ingestion."""
import base64
import json
import sys
from pathlib import Path
from urllib.robotparser import RobotFileParser


AGENT = "DocWeave/0.1"


def decision(policy, url):
    robots = RobotFileParser()
    if policy.get("status") == 404:
        robots.parse([])
    elif policy.get("status") == 200:
        robots.parse(base64.b64decode(policy["body_base64"]).decode("utf-8-sig").splitlines())
    else:
        return {"can_fetch": False, "crawl_delay": None, "reason": "robots permission unavailable"}
    allowed = robots.can_fetch(AGENT, url)
    delay = robots.crawl_delay(AGENT) or 1
    return {"can_fetch": allowed and delay <= 10, "crawl_delay": delay,
            "reason": "allowed" if allowed and delay <= 10 else "robots disallows source or crawl delay exceeds 10 seconds"}


if __name__ == "__main__":
    path = Path(sys.argv[1])
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    policies = {policy["origin"]: policy for policy in report["robots"]}
    for page in report["receipts"]:
        page["robots"] = decision(policies[page["origin"]], page["url"])
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
