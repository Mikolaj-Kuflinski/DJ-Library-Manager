from src.config import get_available_tags
from src.tags import parse_grouping, read_grouping, has_tag

path = r"C:\DJ all\wszystko\22Bullets, Pascal Letoublon, MERYLL - Something In The Air.mp3"

song_tags = parse_grouping(read_grouping(path))
available_tags = get_available_tags()

for category, values in available_tags.items():

    print(f"\n=== {category} ===")

    for value in values:

        checked = has_tag(song_tags, category, value)

        print(f"{checked}  {value}")