"""Random pick from the rotation, avoiding recent repeats."""
import random


def item_key(item):
    return item.get("path") or item.get("url")


def pick(rotation, recent, rng=random):
    """Return a random item whose key isn't in `recent`.

    `recent` is a list of keys (most recent last). We avoid up to
    len(rotation) - 1 of them so there's always something left to choose.
    """
    if not rotation:
        raise ValueError("content rotation is empty")
    avoid = set(recent[-(len(rotation) - 1):]) if len(rotation) > 1 else set()
    choices = [i for i in rotation if item_key(i) not in avoid] or rotation
    return rng.choice(choices)


def remember(recent, item, keep=20):
    recent.append(item_key(item))
    del recent[:-keep]
    return recent
