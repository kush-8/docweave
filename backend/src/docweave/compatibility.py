"""Operator-only CLI for fixed synthetic probes; no arbitrary project input."""

import argparse, asyncio, json, os
from datetime import datetime, UTC
from dotenv import dotenv_values
from docweave.core.paths import ROOT
from docweave.core.settings import database_url
from docweave.rag.contracts import HostedError
from docweave.repositories import compatibility as repository
from docweave.services.compatibility import prepare_synthetic_probes, run_synthetic_probe


def operator_url():
    url = database_url("MIGRATION_DATABASE_URL")
    if (url.host, url.port, url.database, url.username) != ("127.0.0.1", 55432, "docweave", "docweave_migrator") or url.query:
        raise HostedError("development_operator_target_required")
    return url

async def main(run):
    from uuid import UUID
    from docweave.db.engine import make_engine
    from docweave.evaluation import write_report
    from docweave.core.identity import Actor

    engine = make_engine(operator_url())
    root = ROOT
    try:
        values = dotenv_values(root / ".env")
        keys = {provider: os.environ.get(provider.upper() + "_API_KEY", values.get(provider.upper() + "_API_KEY")) for provider in ("gemini", "groq")}
        if run and not all(keys.values()):
            raise HostedError("missing_api_keys")
        configuration = await prepare_synthetic_probes(engine)
        if not run:
            return {"prepared": True, "inference_dispatched": False, **configuration}
        actor = Actor(UUID(configuration["actor_id"]), UUID(configuration["workspace_id"]))
        results = {}
        for name, key in configuration["operations"].items():
            results[name] = await run_synthetic_probe(actor, UUID(configuration["project_id"]), name, key,
                engine=engine, api_key=keys["gemini" if name.startswith("gemini-") else "groq"])
        async with engine.connect() as connection:
            retained = await repository.retained_cost(connection, actor.workspace_id)
        report = {"version": "synthetic-compatibility-v1", "created_at": datetime.now(UTC).isoformat(),
            "billing_verified": False, "private_processing_enabled": False, "retained_usd": str(retained), "results": results}
        write_report(root / "backend/eval/reports/compatibility-v1.json", report)
        return report
    finally:
        await engine.dispose()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare fixed synthetic probes; --run dispatches only unclaimed requests under the durable US$0.25 cap.")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(main(args.run)), indent=2))
    except HostedError as error:
        parser.exit(1, f"Synthetic probe failed: {error}\n")
