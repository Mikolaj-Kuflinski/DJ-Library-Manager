import sqlite3
from src.database import Song

DB_NAME = "library.db"


def save_songs(songs):
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    for song in songs:
        cursor.execute(
            """
            INSERT OR IGNORE INTO songs
            (title, artist, album, grouping, path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                song.title,
                song.artist,
                song.album,
                song.grouping,
                song.path,
            ),
        )

    connection.commit()
    connection.close()


def load_songs():
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT title, artist, album, grouping, path
        FROM songs
        """
    )

    rows = cursor.fetchall()

    songs = []

    for row in rows:
        songs.append(
            Song(
                title=row[0],
                artist=row[1],
                album=row[2],
                grouping=row[3],
                path=row[4],
            )
        )

    connection.close()

    return songs


def update_song(song):
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE songs
        SET
            title = ?,
            artist = ?,
            album = ?,
            grouping = ?
        WHERE path = ?
        """,
        (
            song.title,
            song.artist,
            song.album,
            song.grouping,
            song.path,
        ),
    )

    connection.commit()
    connection.close()


def get_song_by_path(path):
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT title, artist, album, grouping, path
        FROM songs
        WHERE path = ?
        """,
        (path,),
    )

    row = cursor.fetchone()

    connection.close()

    if row is None:
        return None

    return Song(
        title=row[0],
        artist=row[1],
        album=row[2],
        grouping=row[3],
        path=row[4],
    )