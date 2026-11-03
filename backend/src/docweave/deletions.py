"""Provision the live erasure journal, or replay it into an offline restored database."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from docweave.core.settings import database_url, deletion_root
from docweave.db.engine import make_engine
from docweave.services.deletions import replay_deletions
from docweave.storage.artifacts import ArtifactStore, snapshot_artifacts
from docweave.storage.deletions import DeletionJournal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--initialize', action='store_true', help='First installation only; never replace the latest journal during restore')
    mode.add_argument('--replay', action='store_true', help='Replay latest journal with providers disabled and workers drained')
    parser.add_argument('--journal', type=Path, default=deletion_root())
    parser.add_argument('--artifacts', type=Path, help='Existing restored artifact directory; required for replay')
    parser.add_argument('--database-url-env', default='MIGRATION_DATABASE_URL')
    args = parser.parse_args()
    try:
        if args.initialize:
            args.journal.mkdir(mode=0o700, exist_ok=False)
            DeletionJournal(args.journal).check_root()
            result = {'initialized': True}
        else:
            if args.artifacts is None:
                raise ValueError('Explicit restored artifacts are required')
            snapshot_artifacts(args.artifacts)
            async def replay():
                engine = make_engine(database_url(args.database_url_env))
                try:
                    return await replay_deletions(engine=engine, journal=DeletionJournal(args.journal), store=ArtifactStore(args.artifacts))
                finally:
                    await engine.dispose()
            result = asyncio.run(replay(), loop_factory=asyncio.SelectorEventLoop if sys.platform == 'win32' else None)
        print(json.dumps(result))
    except Exception:
        parser.exit(2, 'Deletion reconciliation unavailable; keep services offline and inspect the latest journal, restored database and artifacts.\n')


if __name__ == '__main__':
    main()
