from . import lister

import asyncio
from loguru import logger

from pathlib import Path


def cmd(db: str, *lists):
    """Fetch twitter lists 'lists' into DB"""
    logger.info("[{}] Reading from lists: {}", db, lists)

    # Convert DB str to Path and create directory for it (if needed)
    fullDB = Path(db)
    fullDB.parent.mkdir(parents=True, exist_ok=True)

    s = lister.Storage(fullDB)

    # simple search example:
    # for t in s.search("alert OR unusual OR uo OR trigger"):
    #    print(t.content, t.score)

    tt = lister.TimelineTracker(lists, s)
    asyncio.run(tt.run())


def runit():
    import fire

    try:
        fire.Fire(cmd)
    except KeyboardInterrupt:
        # user requested exit, don't log exception
        logger.info("Goodbye!")
        pass
    except:
        logger.exception("no?")


if __name__ == "__main__":
    runit()
