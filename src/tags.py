from mutagen.easyid3 import EasyID3

EasyID3.RegisterTextKey("grouping", "TIT1")


def build_grouping(tags: dict):
    result = []

    for category, values in tags.items():
        if not values:
            continue

        result.append(f"{category}={','.join(values)}")

    return "|".join(result)


def parse_grouping(grouping: str):
    tags = {}

    if not grouping or grouping == "Brak":
        return tags

    for item in grouping.split("|"):
        if "=" not in item:
            continue

        category, values = item.split("=", 1)
        tags[category] = values.split(",")

    return tags


def has_tag(tags, category, value):
    return value in tags.get(category, [])


def add_tag(tags, category, value):
    tags.setdefault(category, [])

    if value not in tags[category]:
        tags[category].append(value)


def remove_tag(tags, category, value):
    if category not in tags:
        return

    if value in tags[category]:
        tags[category].remove(value)

    if not tags[category]:
        del tags[category]


def save_grouping(path, tags):
    grouping = build_grouping(tags)

    audio = EasyID3(path)
    audio["grouping"] = [grouping]
    audio.save()

    return grouping


def read_grouping(path):
    audio = EasyID3(path)
    return audio.get("grouping", ["Brak"])[0]