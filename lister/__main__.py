from . import lister

import asyncio
from loguru import logger

from pathlib import Path


def listercmd():
    import fire

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

    try:
        fire.Fire(cmd)
    except KeyboardInterrupt:
        # user requested exit, don't log exception
        logger.info("Goodbye!")
        pass
    except:
        logger.exception("no?")


def deletercmd():
    import fire
    import tweepy
    import time
    import random

    def cmd(delay_s: float = 0, *tweet_ids: str):
        """Delete tweets from account defined by environment credentials."""
        api = tweepy.API(lister.auth)

        logger.info(
            "[{} s delay] Deleting {} tweets: {}", delay_s, len(tweet_ids), tweet_ids
        )
        for idx, status_id in enumerate(tweet_ids):
            stage = (idx, len(tweet_ids))

            # we're being lazy here and just trying to delete or unretweet if exception...
            # because we don't want to check which type of tweet we are deleting...
            while True:
                try:
                    logger.info("[{} :: {}] Deleting...", stage, status_id)
                    # 'trim_user' means just return user id of status instead of
                    # fetching the entire user object each time as a value.
                    api.destroy_status(status_id, trim_user=True)
                    time.sleep(delay_s + random.uniform(0, delay_s / 2))
                except tweepy.error.TweepError as e:
                    logger.warning(
                        "[{} :: {}] Delete failed? Trying Un-Retweeting... ({})",
                        stage,
                        status_id,
                        e,
                    )
                    try:
                        # Twitter API is very flaky, so if we failed due to a connection error
                        # instead of an actual API error, just continue retrying forever until
                        # the API starts accepting requests again.
                        # The connection error is rendered out as a string like:
                        # > Failed to send request: ('Connection aborted.', TimeoutError(60, 'Operation timed out'))
                        if "Connection" in str(e):
                            logger.error(
                                "Detected connection failure, so trying original delete again..."
                            )
                            # If connection error, pause and resume forever
                            time.sleep(delay_s + random.uniform(0, delay_s / 2))
                            continue
                    except:
                        logger.error("Failed failure check!")
                        continue

                    try:
                        api.unretweet(status_id, trim_user=True)
                    except tweepy.error.TweepError:
                        logger.error(
                            "[{} :: {}] Un-Retweet also failed!", stage, status_id
                        )

                break

    try:
        fire.Fire(cmd)
    except KeyboardInterrupt:
        # user requested exit, don't log exception
        logger.info("Goodbye!")
        pass
    except:
        logger.exception("no?")


if __name__ == "__main__":
    listercmd()
