"""Command-line evaluation and engine lifetime."""

import argparse, asyncio
from pathlib import Path
from uuid import UUID
from docweave.core.identity import Actor
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.evaluation.config import DEFAULT_DATASET
from docweave.evaluation.datasets import load_dataset, load_recording
from docweave.evaluation.runner import evaluate
from docweave.evaluation.reports import write_report
from docweave.rag.contracts import RetrievalError


async def main(args):
    dataset = load_dataset(args.dataset)
    recording = load_recording(args.vectors)
    engine = make_engine(database_url("DATABASE_URL"))
    try:
        report = await evaluate(dataset, actor=Actor(args.actor, args.workspace), project_id=args.project, collection_ids=args.collection,
            generation_id=args.generation, recording=recording, denied_collection_ids=args.denied_collection, engine=engine)
        write_report(args.output, report)
    finally:
        await engine.dispose()

def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("actor", "workspace", "project", "generation"):
        parser.add_argument("--" + name, type=UUID, required=True)
    parser.add_argument("--collection", type=UUID, action="append", required=True)
    parser.add_argument("--denied-collection", type=UUID, action="append")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    try:
        asyncio.run(main(parser.parse_args()))
    except (ValueError, RetrievalError, OSError):
        parser.exit(2, "Invalid, unavailable or incompatible evaluation inputs.\n")
