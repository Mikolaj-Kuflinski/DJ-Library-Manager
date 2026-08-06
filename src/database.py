from dataclasses import dataclass
import sqlite3


@dataclass
class Song:
    title: str
    artist: str
    album: str
    grouping: str
    path: str


DB_NAME = "library.db"


def create_database():
    connection = sqlite3.connect(DB_NAME)

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            artist TEXT,
            album TEXT,
            grouping TEXT,
            path TEXT UNIQUE
        )
    """)

    connection.commit()
    connection.close()


def save_songs(songs):

    connection = sqlite3.connect(DB_NAME)

    cursor = connection.cursor()

    for song in songs:

        cursor.execute("""
        INSERT OR IGNORE INTO songs
        (title, artist, album, grouping, path)

        VALUES (?, ?, ?, ?, ?)
        """, (

            song.title,
            song.artist,
            song.album,
            song.grouping,
            song.path

        ))

    connection.commit()
    connection.close()