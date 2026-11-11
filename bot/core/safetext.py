"""Cleaning text that crosses a trust line: what players wrote before an AI agent reads it, and what an AI (the bot's own, or a dev's agent)
wrote before it is posted where players see it. One place, so every door uses the same rules.
- HIDDEN: invisible characters that can spell instructions nobody sees.
- Links and invites: an agent that was tricked must not be able to hand players a link, so AI-written public text carries none.
- Mentions: AI-written text never names @everyone, a role or a user."""
import re

HIDDEN = re.compile('[\U000e0000-\U000e007f​-‏‪-‮⁠-⁤﻿]')
_TLD = 'com|net|org|gg|io|xyz|ru|cn|tk|ly|me|co|app|dev|link|site|top|info|shop|club|online|live|biz|cc|to'
LINK = re.compile(rf'(?:https?://|www\.)\S+|discord(?:app)?\s*\.\s*(?:gg|com/invite)\S*|\b(?:[a-z0-9-]+\.)+(?:{_TLD})\b(?:/\S*)?', re.I)
MENTION = re.compile(r'@\s*(?:everyone|here)|<@[!&]?\d+>|<#\d+>|<id:\w+>', re.I)


def tidy(text, cap=200):
    """One clean line: no invisible characters, no line breaks, at most `cap` characters."""
    return ' '.join(HIDDEN.sub('', str(text or '')).split())[:cap]


def has_link(text):
    return bool(LINK.search(str(text or '')))


def has_mention(text):
    return bool(MENTION.search(str(text or '')))


def no_links(text):
    """The text with every link and invite taken out."""
    return LINK.sub('[link removed]', str(text or ''))


def no_mentions(text):
    return MENTION.sub('[mention removed]', str(text or ''))


def public(text, cap=200):
    """AI-written text on its way to a public post: one clean line with no links and no mentions."""
    return no_mentions(no_links(tidy(text, cap * 2)))[:cap]


def refuse(text):
    """Why agent-written text may not be posted (a short reason), or None when it is fine."""
    if has_link(text):
        return 'links and invites are not allowed in text an agent posts (your dev can add a link in Discord)'
    if has_mention(text):
        return 'mentions (@everyone, roles, users, channels) are not allowed in text an agent posts'
    return None
