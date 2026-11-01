"""Operator-only source review: python -m docweave.catalog --help."""
import argparse
import asyncio
import json
from uuid import UUID
from docweave.ownership import load_mapping
from docweave.services.catalog_review import parse_manifest
from docweave.repositories import catalog as repository
from docweave.core.settings import database_url
from docweave.db.engine import make_engine


async def review(path=None, *, apply=False, approve_hash=None, revoke=None, url_env='MIGRATION_DATABASE_URL'):
    if revoke and (path or approve_hash or not apply) or not revoke and not path:
        raise ValueError('Choose a manifest or --apply --revoke')
    if revoke:
        digest, entries = None, []
    else:
        entries, digest = parse_manifest(load_mapping(path))
        if approve_hash and (not apply or approve_hash != digest):
            raise ValueError('Approval must match the exact reviewed manifest hash')
    result = {'manifest_hash': digest, 'entries': len(entries), 'applied': apply,
        'source_approved': bool(approve_hash), 'paid_work_dispatched': False}
    if not apply:
        return result
    engine = make_engine(database_url(url_env))
    try:
        async with engine.begin() as connection:
            if revoke:
                result['revoked'] = await repository.revoke_revision(connection, UUID(str(revoke)))
            else:
                result['revision_ids'] = await repository.publish_manifest(connection, entries, digest, approved=bool(approve_hash))
    finally:
        await engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description='Review public source manifests; no fetching, embedding or provider calls')
    parser.add_argument('--manifest')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-hash', help='Approve only the exact manifest hash shown by dry run; creates immutable replacement revisions')
    parser.add_argument('--revoke', type=UUID)
    parser.add_argument('--database-url-env', default='MIGRATION_DATABASE_URL')
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(review(args.manifest, apply=args.apply, approve_hash=args.approve_hash,
            revoke=args.revoke, url_env=args.database_url_env)), sort_keys=True))
    except (ValueError, OSError):
        parser.exit(2, 'Invalid catalog review input or unavailable manifest. No approval was applied.\n')


if __name__ == '__main__':
    main()
