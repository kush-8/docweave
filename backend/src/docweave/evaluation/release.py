"""Separate release drafts and human review packets; never dispatches providers."""
import copy
import hashlib
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, PrivateAttr, model_validator
from docweave.rag.contracts import unique_keys
from docweave.schemas.common import StrictInput, Nonblank


class ProjectContext(StrictInput):
    technology: Nonblank
    docs_target: Nonblank


class ReleaseCase(StrictInput):
    id: str = Field(pattern=r'^[a-z0-9_-]{1,64}$')
    family_id: str = Field(pattern=r'^[a-z0-9_-]{1,64}$')
    split: Literal['development', 'held_out']
    kind: Literal['answerable', 'no_evidence', 'denied', 'version', 'guardrail']
    query: str = Field(min_length=1, max_length=4096)
    required_facts: list[Nonblank] = Field(max_length=20)
    sources: list[str] = Field(max_length=10)
    project_context: ProjectContext
    expected_outcome: Literal['answered', 'abstained', 'blocked_policy', 'needs_clarification']

    @model_validator(mode='after')
    def validate_expectations(self):
        if not self.query.strip() or '\x00' in self.query:
            raise ValueError('Invalid question')
        if self.kind == 'answerable':
            if not self.required_facts or not self.sources or self.expected_outcome != 'answered':
                raise ValueError('Answerable cases require factual labels and sources')
        elif self.expected_outcome == 'answered':
            raise ValueError('Boundary cases cannot require an answer')
        for source in self.sources:
            url = urlsplit(source)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or any(ord(c) < 33 for c in source):
                raise ValueError('Sources must be credential-free HTTPS references')
        return self


class ReleaseDataset(StrictInput):
    _sha256: str = PrivateAttr(default='')
    _validated_json: str = PrivateAttr(default='')
    version: str = Field(min_length=1, max_length=64)
    human_label_review: Literal['pending', 'complete']
    cases: list[ReleaseCase] = Field(min_length=150, max_length=150)

    @model_validator(mode='after')
    def validate_splits(self):
        if sum(case.split == 'development' for case in self.cases) != 100:
            raise ValueError('Release requires 100 development and 50 held-out cases')
        if len({case.id for case in self.cases}) != 150:
            raise ValueError('Duplicate scenario ID')
        if len({' '.join(case.query.casefold().split()) for case in self.cases}) != 150:
            raise ValueError('Duplicate question')
        families = {}
        for case in self.cases:
            if families.setdefault(case.family_id, case.split) != case.split:
                raise ValueError('Scenario family crosses splits')
        return self


def load_release_dataset(path):
    with Path(path).open('rb') as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Release dataset too large')
    result = ReleaseDataset.model_validate(json.loads(raw, object_pairs_hook=unique_keys))
    result._sha256 = hashlib.sha256(raw).hexdigest()
    result._validated_json = result.model_dump_json()
    return result


def review_packets(dataset, captures):
    if dataset.model_dump_json() != dataset._validated_json:
        raise ValueError('Release dataset changed after validation')
    if not dataset._sha256 or not isinstance(captures, dict) or set(captures) != {case.id for case in dataset.cases}:
        raise ValueError('Every scenario requires one captured result')
    encoded = json.dumps(captures, default=str, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    captured_hash = hashlib.sha256(encoded).hexdigest()
    packets = {}
    for split in ('development', 'held_out'):
        cases = [case for case in dataset.cases if case.split == split]
        cases.sort(key=lambda case: hashlib.sha256((dataset._sha256 + ':' + case.id).encode()).digest())
        packets[split] = {'dataset_sha256': dataset._sha256, 'captures_sha256': captured_hash,
            'label_review': dataset.human_label_review, 'human_review': 'pending', 'semantic_quality_evidence': False,
            'items': [{'scenario': case.model_dump(), 'capture': copy.deepcopy(captures[case.id]), 'ratings': None}
                      for case in cases[:30]]}
    return packets


def main():
    import argparse
    from docweave.evaluation.reports import write_report
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Private output directory for the two review packets')
    args = parser.parse_args()
    try:
        dataset = load_release_dataset(args.dataset)
        with args.captures.open('rb') as file:
            raw = file.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('Captures too large')
        captures = json.loads(raw, object_pairs_hook=unique_keys)
        for split, packet in review_packets(dataset, captures).items():
            write_report(args.output / (split + '-review.json'), packet)
        print('Prepared two separate 30-output review packets; human review remains pending.')
    except (ValueError, OSError, TypeError):
        parser.exit(2, 'Invalid or unavailable release inputs; no acceptance is claimed.\n')


if __name__ == '__main__':
    main()
