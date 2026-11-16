#!/usr/bin/env python3
"""Self-check for wheel_community.py. Run: python3 skills/wheel/scripts/test_wheel_community.py

No network: the sources are replaced by stubs. What is pinned is what the card
relies on -- a source that failed is never reported as "no results", queries are
scrubbed before they leave, results de-duplicate across phrasings, and every run
leaves a receipt the registry's gate can read.
"""
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wheel_community as wc  # noqa: E402
import test_wheel_registry as regtest  # noqa: E402

CHECKS, FAILS = [], []


def check(cond, label):
    CHECKS.append(label)
    if not cond:
        FAILS.append(label)


def test_outcomes_keep_failure_apart_from_silence():
    def hits(q, n, r):
        return [wc.item("t " + q, "https://x/" + q)]

    def empty(q, n, r):
        return []

    def limited(q, n, r):
        raise urllib.error.HTTPError("u", 429, "slow down", None, None)

    def refused(q, n, r):
        raise urllib.error.HTTPError("u", 403, "forbidden", None, None)

    def down(q, n, r):
        raise urllib.error.URLError("no route")

    def skipped(q, n, r):
        raise RuntimeError("skipped")

    report = wc.search(["a", "b"], 5, None, sources=(
        ("hits", hits), ("empty", empty), ("limited", limited), ("down", down),
        ("skipped", skipped), ("refused", refused)))
    got = {k: v["outcome"] for k, v in report.items()}
    check(got == {"hits": "ok", "empty": "no-results", "limited": "rate-limited",
                  "down": "unreachable", "skipped": "skipped", "refused": "blocked"},
          "each source reports its own outcome: %r" % got)
    check(len(report["hits"]["items"]) == 2, "hits from both phrasings are kept")


def test_merge_dedupes_and_survives_a_partial_failure():
    a = wc.item("one", "https://x/1")
    outcome, items = wc.merge([("rate-limited", []), ("ok", [a, a]), ("ok", [a])])
    check(outcome == "ok" and len(items) == 1, "one query getting through is an answer, de-duplicated")
    check(wc.merge([("ok", []), ("ok", [])])[0] == "no-results", "answered with nothing is no-results")
    check(wc.merge([("unreachable", []), ("unreachable", [])])[0] == "unreachable",
          "never answered is not no-results")


def test_scrub_strips_what_identifies_the_machine():
    home = os.path.expanduser("~")
    out = wc.scrub("ENOENT %s/proj/a.js mail me@example.com tx 0x%s" % (home, "ab" * 32))
    check(home not in out, "home path removed")
    check("me@example.com" not in out and "<email>" in out, "e-mail removed")
    check("ab" * 32 not in out and "<hex>" in out, "long hex removed")
    check("ENOENT" in out and "a.js" in out, "the error text itself survives")


def test_parsers_read_each_api_shape():
    check(wc.parse_gh_api({"items": [{"title": "T", "html_url": "u", "comments": 3,
                                      "updated_at": "2026-01-02T00:00:00Z", "state": "open"}]})
          == [wc.item("T", "u", comments=3, date="2026-01-02", state="open")], "GitHub search API")
    check(wc.parse_gh_search([{"title": "T", "url": "u", "commentsCount": 1,
                               "updatedAt": "2026-01-02T00:00:00Z", "state": "closed"}])[0]["state"]
          == "closed", "gh search --json")
    check(wc.parse_hn({"hits": [{"objectID": "7", "title": "T", "points": 9, "num_comments": 2,
                                 "created_at": "2026-01-02T00:00:00Z"}]})[0]["url"]
          == "https://news.ycombinator.com/item?id=7", "Hacker News")
    check(wc.parse_so({"items": [{"title": "T", "link": "u", "score": 4, "answer_count": 1,
                                  "is_answered": True, "creation_date": 1767312000}]})[0]["state"]
          == "answered", "Stack Overflow")
    check(wc.parse_reddit({"data": {"children": [{"data": {
        "title": "T", "permalink": "/r/x/1", "score": 5, "num_comments": 6,
        "subreddit": "x", "created_utc": 1767312000}}]}})[0]["url"]
        == "https://www.reddit.com/r/x/1", "Reddit")
    check(wc.parse_gh_discussions({"data": {"search": {"nodes": [None, {
        "title": "T", "url": "u", "upvoteCount": 2, "isAnswered": True,
        "updatedAt": "2026-01-02T00:00:00Z", "comments": {"totalCount": 3}}]}}})[0]["comments"]
        == 3, "GitHub Discussions (null nodes skipped)")
    check(wc.parse_hn({}) == [] and wc.parse_reddit(None) == [], "empty payloads are empty, not errors")


def test_receipt_opens_the_registry_gate():
    with tempfile.TemporaryDirectory() as tmp:
        led, reg = os.path.join(tmp, "w", "ledger.jsonl"), os.path.join(tmp, "r.tsv")
        old = os.environ.get("WHEEL_LEDGER")
        os.environ["WHEEL_LEDGER"] = led
        try:
            report = {"gh_issues": {"outcome": "ok", "items": [wc.item("T", "https://x/1")]},
                      "hn": {"outcome": "no-results", "items": []},
                      "reddit": {"outcome": "rate-limited", "items": []}}
            entry = wc.write_receipt(["q"], report)
        finally:
            if old is None:
                os.environ.pop("WHEEL_LEDGER", None)
            else:
                os.environ["WHEEL_LEDGER"] = old
        with open(led, encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh]
        check(len(lines) == 1 and lines[0]["kind"] == "search"
              and lines[0]["sources"]["reddit"]["outcome"] == "rate-limited",
              "one receipt line, outcomes preserved")
        check(wc.receipt_line(entry["sources"]) == "gh_issues ok 1｜hn no-results｜reddit rate-limited",
              "receipt line reads the same as the ledger")
        p = regtest.run("add", "採用", "q", "pick", 90, registry=reg, ledger=led)
        check(p.returncode == 0 and "社群收據：" in p.stdout,
              "a receipt this script wrote is accepted by wheel_registry add")


def main():
    for fn in (test_outcomes_keep_failure_apart_from_silence,
               test_merge_dedupes_and_survives_a_partial_failure,
               test_scrub_strips_what_identifies_the_machine,
               test_parsers_read_each_api_shape,
               test_receipt_opens_the_registry_gate):
        try:
            fn()
        except Exception as e:
            FAILS.append("%s raised %r" % (fn.__name__, e))
    for f in FAILS:
        print("FAIL ", f)
    if FAILS:
        print("\n%d of %d checks failed" % (len(FAILS), len(CHECKS)))
        return 1
    print("PASS  %d checks: outcomes, merge, scrub, six parsers, receipt -> registry gate" % len(CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
