import asyncio
from sqlalchemy.orm import Session
from .simulator import run_single
from .run_service import create_run, update_run, finish_batch

async def run_batch(db: Session, batch_id: int, descriptions: list[str], concurrency: int = 3):
    """
    Execute a batch of Physis builds with limited concurrency.
    Updates DB after each run completes so the frontend can poll progress.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(description: str):
        async with semaphore:
            run = create_run(db, description=description, batch_id=batch_id)
            sim_result = await run_single(description)
            update_run(db, run.id, sim_result)

    tasks = [run_one(desc) for desc in descriptions]
    await asyncio.gather(*tasks)
    finish_batch(db, batch_id)
