"""Worker-only private indexing RPCs; caller owns transactions."""
from sqlalchemy import text

async def enqueue(c,actor,document,generation):
    return await c.scalar(text('SELECT app.private_index_enqueue(:actor,:document,:generation)'),dict(actor=actor,document=document,generation=generation))

async def claim(c,job):
    return await c.scalar(text('SELECT app.private_index_claim(:job)'),dict(job=job))

async def context(c,job,token,profile,key=None):
    return await c.scalar(text('SELECT app.private_index_context(:job,:token,:profile,:key)'),dict(job=job,token=token,profile=profile,key=key))

async def finish(c,job,token,status):
    return await c.scalar(text('SELECT app.private_index_finish(:job,:token,:status)'),dict(job=job,token=token,status=status))

async def reconcile(c,generation):
    return await c.scalar(text('SELECT app.private_index_reconcile(:generation)'),dict(generation=generation))
