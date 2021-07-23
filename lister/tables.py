# Modeled after:
# https://charlesleifer.com/blog/using-sqlite-full-text-search-with-python/

import peewee
from peewee import *
from playhouse.sqlite_ext import *

from loguru import logger

# Parameterized as:
# https://stackoverflow.com/questions/44984429/how-to-manage-a-peewee-database-in-a-separate-module
# (allows us to specify the DB filename at runtime)
db = peewee.Proxy()


class BaseModel(Model):
    class Meta:
        database = db
        auto_increment = False


class Tweet(BaseModel):
    id = TextField(primary_key=True)
    ts = DateTimeField()
    member = TextField(index=True)  # lazy non-foreign list status
    name = TextField()
    screen_name = TextField(index=True)
    content = TextField()
    entities = JSONField()


class FTSEntry(FTSModel):
    content = TextField()

    class Meta:
        database = db


def add(t, listname) -> bool:
    """Returns True if tweet added, False otherwise (i.e. if duplicate)"""
    try:
        # We didn't notice t.created_at was being inserted as a string initially,
        # so we back-filled the on-disk database with epoch timestamps using:
        # lists.db> update tweet set ts = strftime('%s', ts);
        # Query OK, 55960 rows affected
        # Time: 0.223s
        tw = Tweet.create(
            id=t.id,
            ts=int(t.created_at.timestamp()),
            member=listname,
            name=t.author.name,
            screen_name=t.author.screen_name,
            content=t.full_text,
            entities=t.entities,
        )
    except peewee.IntegrityError:
        # ignore duplicate entries
        # (the same tweet can be in multiple lists, so we are also
        #  ignoring the other 'member' attributes and just go with
        #  the first one we ingested)
        # logger.exception("why?")
        return False

    fw = FTSEntry.create(docid=tw.id, content=t.full_text)

    return True


def search(what):
    q = (
        Tweet.select(Tweet, FTSEntry.bm25().alias("score"))
        .join(FTSEntry, on=(Tweet.id == FTSEntry.docid))
        .where(FTSEntry.match(what))
        .order_by(SQL("score").desc())
    )

    return q


def setup() -> int:
    Tweet.create_table()
    FTSEntry.create_table()

    # Return highest ID for resuming fetching against
    for maxval in Tweet.select(Tweet.id).order_by(Tweet.id.desc()).limit(1):
        return int(maxval.id)

    return 0
