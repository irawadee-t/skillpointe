"""
platform.py — Detect which ATS / careers platform a URL is running on.

Most employer career pages are powered by one of a handful of platforms
(Workday, Greenhouse, Lever, SmartRecruiters, iCIMS, Avature, SAP SuccessFactors).
Each platform has a documented JSON API or stable HTML shell, so a SINGLE
*platform* adapter can ingest any employer using that platform — no per-employer
code needed.

This module:
  • detects the platform from a URL (cheap — just URL pattern matching plus
    one optional HEAD/GET for ambiguous cases).
  • returns the right ScraperPlatform enum so the import pipeline picks the
    correct universal adapter.

Pure functions; no I/O beyond an optional probe request.
"""
from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlparse


class Platform(str, Enum):
    WORKDAY         = "workday"
    GREENHOUSE      = "greenhouse"
    LEVER           = "lever"
    SMARTRECRUITERS = "smartrecruiters"
    SUCCESSFACTORS  = "successfactors"
    ICIMS           = "icims"
    AVATURE         = "avature"
    ASHBY           = "ashby"
    JOBVITE         = "jobvite"
    BAMBOOHR        = "bamboohr"
    PARADOX         = "paradox"
    UNKNOWN         = "unknown"


# Host-substring → platform mapping. Conservative: only confident matches.
_HOST_RULES: list[tuple[re.Pattern[str], Platform]] = [
    (re.compile(r"\.myworkdayjobs\.com$|\.wd\d+\.myworkdayjobs\.com$|workday\.com$",  re.I), Platform.WORKDAY),
    (re.compile(r"boards\.greenhouse\.io$|boards-api\.greenhouse\.io$|greenhouse\.io$", re.I), Platform.GREENHOUSE),
    (re.compile(r"jobs\.lever\.co$|hire\.lever\.co$|api\.lever\.co$",                 re.I), Platform.LEVER),
    (re.compile(r"smartrecruiters\.com$|jobs\.smartrecruiters\.com$",                 re.I), Platform.SMARTRECRUITERS),
    (re.compile(r"successfactors\.com$|sapsf\.com$",                                  re.I), Platform.SUCCESSFACTORS),
    (re.compile(r"icims\.com$|careers-[^.]+\.icims\.com$",                            re.I), Platform.ICIMS),
    (re.compile(r"avature\.net$|jobs-[^.]+\.avature\.net$",                           re.I), Platform.AVATURE),
    (re.compile(r"\.ashbyhq\.com$|jobs\.ashbyhq\.com$",                                re.I), Platform.ASHBY),
    (re.compile(r"jobs\.jobvite\.com$|\.jobvite\.com$",                                re.I), Platform.JOBVITE),
    (re.compile(r"bamboohr\.com$",                                                     re.I), Platform.BAMBOOHR),
    (re.compile(r"paradox\.ai$|\.paradox\.ai$",                                       re.I), Platform.PARADOX),
]


def detect_from_url(url: str) -> Platform:
    """Return the platform for a careers URL. UNKNOWN if no rule matches."""
    if not url:
        return Platform.UNKNOWN
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return Platform.UNKNOWN
    if not host:
        return Platform.UNKNOWN
    for pattern, plat in _HOST_RULES:
        if pattern.search(host):
            return plat
    # Common indirection: a vanity careers.<company>.com page that iframes /
    # links to an ATS. We give up here — the caller may fall back to fetching
    # the page and looking for known platform fingerprints in the body.
    return Platform.UNKNOWN


# ----------------------------------------------------------------------------
# Lightweight "fingerprint" detection for vanity careers domains (e.g.
# careers.acme.com that proxies a Greenhouse board). Only call when
# detect_from_url returns UNKNOWN and you already have the page HTML.
# ----------------------------------------------------------------------------

_BODY_FINGERPRINTS: list[tuple[re.Pattern[str], Platform]] = [
    (re.compile(r"boards\.greenhouse\.io|greenhouse_iframe",       re.I), Platform.GREENHOUSE),
    (re.compile(r"jobs\.lever\.co|lever-job-listing",              re.I), Platform.LEVER),
    (re.compile(r"myworkdayjobs|wd[0-9]+\.myworkdayjobs",          re.I), Platform.WORKDAY),
    (re.compile(r"smartrecruiters",                                re.I), Platform.SMARTRECRUITERS),
    (re.compile(r"successfactors|sapsf|jobsearch_jsp",             re.I), Platform.SUCCESSFACTORS),
    (re.compile(r"icims",                                          re.I), Platform.ICIMS),
    (re.compile(r"avature",                                        re.I), Platform.AVATURE),
    (re.compile(r"ashby|ashbyhq",                                  re.I), Platform.ASHBY),
    (re.compile(r"jobvite",                                        re.I), Platform.JOBVITE),
    (re.compile(r"bamboohr",                                       re.I), Platform.BAMBOOHR),
    (re.compile(r"__preload_state__",                              re.I), Platform.PARADOX),
]


def detect_from_html(html: str) -> Platform:
    if not html:
        return Platform.UNKNOWN
    for pattern, plat in _BODY_FINGERPRINTS:
        if pattern.search(html):
            return plat
    return Platform.UNKNOWN
