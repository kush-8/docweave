"""Operator lifecycle commands: python -m docweave.guardrails --help."""
import argparse
import asyncio
import json
from uuid import UUID
from docweave.core.guardrails import RULE_REVISION
from docweave.core.settings import database_url,storage_root
from docweave.db.engine import make_engine
from docweave.repositories import guardrails as repository
from sqlalchemy.exc import DBAPIError
from docweave.services.guardrails import review_page
from docweave.storage.artifacts import ArtifactStore


async def operate(args):
    engine=make_engine(database_url(args.database_url_env))
    try:
        async with engine.begin() as connection:
            if args.command=='activate':
                result=await repository.activate(connection,args.expected_epoch)
            elif args.command=='retry':
                result={'queued':await repository.retry(connection,args.version)}
            elif args.command=='review':
                result={'approved':await repository.review_catalog(connection,args.version,args.content_hash,args.expected_epoch)}
            elif args.command=='audit':
                result={'events':[dict(row) for row in await repository.audit(connection,after=args.after,limit=args.limit)]}
            elif args.command=='inspect':
                snapshot=await repository.review_snapshot(connection,args.version)
                result=review_page(ArtifactStore(storage_root()),snapshot,args.offset)
            else:
                result=await repository.status(connection)
            return {'scanner_revision':RULE_REVISION,**result}
    finally:
        await engine.dispose()


def main():
    parser=argparse.ArgumentParser(description='Activate compiled rules, inspect safe audit events, retry local rescans or approve public injection examples. No provider calls.')
    parser.add_argument('--database-url-env',default='MIGRATION_DATABASE_URL')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    activate=sub.add_parser('activate')
    activate.add_argument('--expected-epoch',type=int,required=True)
    retry=sub.add_parser('retry')
    retry.add_argument('--version',type=UUID,required=True)
    review=sub.add_parser('review')
    review.add_argument('--version',type=UUID,required=True)
    review.add_argument('--content-hash',required=True)
    review.add_argument('--expected-epoch',type=int,required=True)
    audit=sub.add_parser('audit')
    audit.add_argument('--after',type=UUID)
    audit.add_argument('--limit',type=int,default=100)
    inspect=sub.add_parser('inspect')
    inspect.add_argument('--version',type=UUID,required=True)
    inspect.add_argument('--offset',type=int,default=0)
    args=parser.parse_args()
    try:
        print(json.dumps(asyncio.run(operate(args)),default=str,sort_keys=True))
    except (ValueError,OSError,DBAPIError):
        parser.exit(2,'Guardrail operation rejected: verify current epoch, exact assessment, operator role and database availability.\n')


if __name__=='__main__':
    main()
