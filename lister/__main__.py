from . import lister

import asyncio
from loguru import logger


def cmd(db, *lists):
    """Fetch twitter lists 'lists' into DB"""
    logger.info("[{}] Reading from lists: {}", db, lists)

    s = lister.Storage(db)

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
