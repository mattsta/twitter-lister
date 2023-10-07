twitter-lister: download twitter lists into fts sqlite db
=========================================================

### 2023 Update

I had this running in a loop for years, but the API stopped working for me in July 2023.

For my own usage, I was logging 7 lists in real time which would now cost
$370,000 per month using paid API calls under New Management.

So... good luck with that?


### Hello TL

`lister` lets you save all tweets in your subscribed twitter lists in ~real time to a full text search sqlite db.

## Features

Features of `lister`:

- runs forever
    - polls twitter every 15 seconds for updates by default
        - twitter API limit is [900 get requests per 15 minutes](https://developer.twitter.com/en/docs/twitter-api/v1/rate-limits) for reading lists
        - twitter doesn't support a live push API for this use case, but polling is fine
    - doesn't crash or exit when seeing twitter API server errors or temporary disconnects
    - has run in production for months continuously
- resumes reading from last seen tweet on startup
    - when resuming from existing db, new tweets will be fetched based on the previously highest tweet saved
- when starting a new database, fetches 3 days back of tweets from each list
- all fetched tweets are added to the fts database
- you can configure custom regex watch strings for printing live tweets to the console when keywords appear in tweets
- properly extracts and saves RTs
- properly handles the same tweet appearing in multiple lists


## Requirements

Requires:

- you do need [a twitter v1.1 API key pair](https://developer.twitter.com/en/docs/twitter-api/getting-started/getting-access-to-the-twitter-api) to use the twitter API
- the full names of twitter lists on your account to download
    - lists can be public or private to your account

## Config Setup

You need to provide these configs either via `.env.lister` or via your environment:

- `access_token`
- `access_token_secret`
- `consumer_key`
- `consumer_secret`
- `NOTIFY_TRIGGER_REGEX`
    - if tweet matches TRIGGER (and not IGNORE regex), print tweet to screen
    - default: all text
- `NOTIFY_IGNORE_REGEX`
    - if tweet matches IGNORE regex, avoid printing even if it also matches TRIGGER regex
    - default: no text
- `REFRESH_SECONDS`
    - default: 15 seconds


## Running

```bash
poetry update
poetry run lister my-tweet-database.db "First List Name" second-list "third LIST NAME" extra-list
```

### Querying DB

Open your lists database using [your favorite sqlite3 cli](https://litecli.com/) then query the `ftsentry` table directly:

```sql
SELECT * FROM ftsentry WHERE ftsentry MATCH 'thing*';
```

Match syntax is the flexible [sqlite3 full text search syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax).
