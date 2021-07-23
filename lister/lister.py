#!/usr/bin/env python3

from __future__ import annotations

import arrow
import tweepy
from loguru import logger

import peewee
from playhouse.sqlite_ext import SqliteExtDatabase

import re
import html  # unescape encoded tweets so we can see < > & etc
import datetime
from . import tables  # local sqlite/table manipulation

import socket
import urllib3.exceptions

import os
import asyncio
from dataclasses import dataclass, field
from collections import deque, namedtuple
from dotenv import dotenv_values

# By default trigger on all tweets being read
CONFIG_DEFAULT = dict(
    NOTIFY_TRIGGER_REGEX=".*", NOTIFY_IGNORE_REGEX="", REFRESH_SECONDS=15
)

# read env and convert to namedtuple
config_ = {
    k: v
    for k, v in {**CONFIG_DEFAULT, **dotenv_values(".env.lister"), **os.environ}.items()
    if not k.startswith("_")
}
Config = namedtuple("Config", config_.keys())
config = Config(**config_)

access_token = config.access_token
access_token_secret = config.access_token_secret

consumer_key = config.consumer_key
consumer_secret = config.consumer_secret

auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)

fetchDefaults = dict(tweet_mode="extended", include_rts=True)

TRIGGERS = re.compile(
    config.NOTIFY_TRIGGER_REGEX,
    flags=re.I,
)
IGNORE = re.compile(config.NOTIFY_IGNORE_REGEX, flags=re.I)

LIST_CHECK_INTERVAL_SECONDS = int(config.REFRESH_SECONDS)


def trigger(what) -> bool:
    """Returns True if 'what' regex parses as (NOT IGNORE) and (YES TRIGGER)"""
    return (not IGNORE.findall(what)) and TRIGGERS.findall(what)


@dataclass
class Storage:
    filename: str

    def __post_init__(self):
        pragmas = [("journal_mode", "wal"), ("cache_size", -1000 * 32)]
        # Could be replaced with any good DB connect string
        db = SqliteExtDatabase(self.filename, pragmas=pragmas)
        tables.db.initialize(db)

        # .setup() must be AFTER initialize because we need the DB
        # details created before tables get managed...
        self.resumeId = tables.setup()

    def add(self, tweet, listname):
        added = tables.add(tweet, listname)

        try:
            # if is RT, the full text isn't in tweet.full_text, the full
            # text is actually in tweet.retweeted_status.full_text. sigh.
            tweet.full_text = tweet.retweeted_status.full_text
        except:
            # if this isn't a retweet, the set will fail, but it's okay
            # because the original .full_tweet is correct.
            pass

        # if trigger passes, print the trigger'd tweet
        # TODO: this could be extended to send triggered tweets to
        #       an external service for alerting on-demand.
        if added and trigger(tweet.full_text):
            logger.info(
                "[{}, ({}, {})] {}: {}",
                listname,
                arrow.get(tweet.created_at).to("US/Eastern"),
                int(tweet.created_at.timestamp()),
                tweet.author.screen_name,
                html.unescape(tweet.full_text),
            )

        return added

    def search(self, what):
        return tables.search(what)


def now() -> float:
    return datetime.datetime.now().timestamp()


@dataclass
class ListTimeline:
    ltlist: tweepy.List

    count: int = 512
    lastFetchId: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=1024))
    nextUpdate: float = now()
    defaultDaysBackLoad: int = 3

    async def bootstrap(self, storage: Storage):
        """Load timeline back to 3 days worth of tweets"""
        oldest = now()
        currentnow = now()
        until = 0

        # if we have an ID already, RESUME from there, don't get 3 days back.
        if self.lastFetchId > 0:
            return await self.updateTimeline(storage)

        while oldest > (currentnow - (86400 * self.defaultDaysBackLoad)):
            if until > 0:
                args = dict(max_id=until) | fetchDefaults
            else:
                args = fetchDefaults

            # First, we fetch the latest tweets, then we fetch back until
            # the oldest tweet is older than 3 days from now.
            tlgot = self.ltlist.timeline(count=self.count, **args)

            if until == 0 and tlgot:
                # If first result grab, populate the newest ID as the next
                # fetch ID for *regular* updates:
                self.lastFetchId = tlgot[0].id

            count = len(tlgot)
            logger.info("[{}] Loading {} oldest of {}", self.ltlist.name, count, oldest)

            if until == tlgot[0].id:
                # if retrieved id is same as lookup id, skip it because we previously
                # already recorded it into our dataset
                tlgot = tlgot[1:]

            # if we reached the end (where the return value is just one status
            # which is the 'max_id' we requested, but we previously got anyway,
            # so we removed it above with the filter), we can't go back any
            # further
            if not tlgot:
                logger.info(
                    "[{}] Stopping load early. Only got back to {}",
                    self.ltlist.name,
                    oldest,
                )
                break

            # History is 'extended' here, because each subsequent query will
            # be OLDER than the previous query, so we grow to the right (since
            # [0] is newest and [-1] is oldest)
            self.history.extend(tlgot)

            # if bootstrapping *and* we hit a duplicate, cancel this bootstrap
            # because we will have older entries.
            for t in tlgot:
                storage.add(t, self.ltlist.name)

            # Set next iteration conditions
            oldest = tlgot[-1].created_at.timestamp()
            until = tlgot[-1].id

    async def updateTimeline(self, storage: Storage) -> bool:
        """Update timeline for list using most recent saved offset.

        Returns True if timeline was updated with new entries.
        Returns False if timeline had no updates."""

        if self.lastFetchId > 0:
            # API only allows since_id to be valid numbers...
            args = dict(since_id=self.lastFetchId) | fetchDefaults
        else:
            args = fetchDefaults

        # Results are from NEWEST to OLDEST, so our history order is:
        # [0] is newest, [-1] is oldest
        while True:
            try:
                tlgot = self.ltlist.timeline(count=self.count, **args)
                break
            except (socket.timeout, urllib3.exceptions.ReadTimeoutError):
                logger.error("Network read error...")
                await asyncio.sleep(1)
            except tweepy.error.TweepError as e:
                logger.error("Service error: {}", e)
                await asyncio.sleep(1)
            except:
                logger.exception("Timeline failure?")
                await asyncio.sleep(3)

        if len(tlgot) <= 1:
            # Either no updates or just one update, so back off next
            # pull for 15 seconds from now.
            self.nextUpdate = now() + LIST_CHECK_INTERVAL_SECONDS

            # but if actually no updates this time, don't process updates!
            if not tlgot:
                return False

        self.history.extendleft(tlgot)

        count = len(tlgot)
        t0 = tlgot[0]
        t = tlgot[-1]

        for t in tlgot:
            storage.add(t, self.ltlist.name)

        logger.debug(
            "[{}] Fetched {} from {} ({}) to {} ({})",
            self.ltlist.name,
            count,
            t.id,
            arrow.get(t.created_at).to("US/Eastern"),
            t0.id,
            arrow.get(t0.created_at).to("US/Eastern"),
        )

        # logger.info("[{}] Last text [{}]: {}", self.ltlist.name, t.id, t.full_text)
        # set next query id to the newest ID retrieved
        self.lastFetchId = t0.id

    def loglines(self, back=100):
        for t in self.history[-100:]:
            print(t.id)
            print(t.created_at)
            print(t.full_text)
            print(t.entities)
            print(t.author.name)
            print(t.author.screen_name)


@dataclass
class TimelineTracker:
    timelineNames: set[str]
    storage: Storage

    def __post_init__(self):
        self.timelines = dict()
        logger.debug("Notify filter: {}", TRIGGERS)
        logger.debug("Ignore filter: {}", IGNORE)

    async def run(self):
        api = tweepy.API(auth)

        for l in api.lists_all():
            if l.name in self.timelineNames:
                logger.info(
                    "Attaching list: {} (resuming from: {})",
                    l.name,
                    self.storage.resumeId,
                )
                ltl = ListTimeline(l, lastFetchId=self.storage.resumeId)
                self.timelines[l.name] = ltl
                await ltl.bootstrap(self.storage)

        while True:
            checkNow = now()
            for name, tl in self.timelines.items():
                if tl.nextUpdate <= checkNow:
                    await tl.updateTimeline(self.storage)

            # Rate limit is 900 API requests per 15 minutes, so if we have
            # fewer than 15 lists and are updating every 15+ seconds
            # we should not hit the rate limit.

            # NOTE: This *could* be more exact by calculating the exact minimum
            # next check time to sleep until the next list scan, but it's
            # also basically free to just iterate over the timeline
            # dictionary to check which lists are ready ready to poll again.
            await asyncio.sleep(max(1, LIST_CHECK_INTERVAL_SECONDS / 4))
