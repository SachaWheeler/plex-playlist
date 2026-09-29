#!/usr/bin/env python3
"""
Create a Plex playlist from tracks that Plex says are sonically similar
to a reference track already in the library.

The reference track can be specified in three ways:
  1. --reference-mp3 PATH   -> title/artist are read from the file's ID3 tags
  2. --reference-title / --reference-artist
  3. --reference-key (Plex ratingKey)

Requirements:
- Plex server running
- PlexAPI installed
- mutagen installed (for ID3 tag reading): pip install mutagen
- Music library section called "Music" (or change section name below)
- Reference track already exists in Plex
- Sonic Analysis enabled/completed for that reference track

Example:
    python create_playlist.py \
      --reference-mp3 "/home/sacha/Music/Massive Attack/Teardrop.mp3" \
      --playlist-name "Similar to Teardrop" \
      --max-results 50
"""

import os
import sys
import argparse
from typing import List, Dict, Optional, Tuple

try:
    from plexapi.server import PlexServer
except ImportError:
    os.system("pip install PlexAPI")
    from plexapi.server import PlexServer

try:
    from plexapi.playlist import Playlist
except ImportError:
    os.system("pip install PlexAPI")
    from plexapi.playlist import Playlist

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
except ImportError:
    os.system("pip install mutagen")
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3


def read_id3_title_artist(mp3_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Read the title and artist from an MP3's ID3v2 tags.

    Handles both plain ID3 tags (TIT2/TPE1) and EasyID3-style access,
    falling back gracefully if tags are missing or malformed.

    Args:
        mp3_path: Path to the MP3 file.

    Returns:
        Tuple of (title, artist). Either may be None if not present.
    """
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"MP3 file not found: {mp3_path}")

    title = None
    artist = None

    # First try the generic mutagen File loader, which is format-agnostic
    # and works for most easy-access tag frames.
    try:
        audio = MutagenFile(mp3_path, easy=True)
        if audio is not None and audio.tags is not None:
            title_list = audio.tags.get("title")
            artist_list = audio.tags.get("artist")
            if title_list:
                title = title_list[0]
            if artist_list:
                artist = artist_list[0]
    except Exception:
        pass

    # Fall back to raw ID3 frames (TIT2 = title, TPE1 = artist) if the
    # easy loader didn't find anything, e.g. non-standard tag versions.
    if title is None or artist is None:
        try:
            id3 = ID3(mp3_path)
            if title is None and "TIT2" in id3:
                title = str(id3["TIT2"].text[0])
            if artist is None and "TPE1" in id3:
                artist = str(id3["TPE1"].text[0])
        except Exception:
            pass

    return title, artist


class PlexSimilarPlaylist:
    def __init__(
        self, plex_url: str, plex_token: str, music_section_name: str = "Music"
    ):
        self.plex = PlexServer(plex_url, plex_token)
        self.music_library = self._get_music_section(music_section_name)

    def _get_music_section(self, section_name: str):
        for section in self.plex.library.sections():
            if section.title == section_name:
                return section
        raise ValueError(
            f"Could not find Plex library section named '{section_name}'. "
            f"Available sections: {[s.title for s in self.plex.library.sections()]}"
        )

    def find_track_by_rating_key(self, rating_key: int):
        item = self.plex.fetchItem(rating_key)
        if getattr(item, "type", None) != "track":
            raise ValueError(f"Plex item {rating_key} is not a music track")
        return item

    def find_track_by_title(self, title: str, artist: Optional[str] = None):
        """
        Find a track in the Plex music library.

        If multiple matches exist, prefer the one whose grandparentTitle (artist)
        matches the supplied artist.
        """
        if not title:
            raise ValueError("A track title is required")

        candidates = self.music_library.searchTracks(title=title)

        if artist:
            artist_normalized = artist.casefold()
            filtered = [
                track
                for track in candidates
                if (getattr(track, "grandparentTitle", "") or "").casefold()
                == artist_normalized
            ]
            if filtered:
                return filtered[0]

        if not candidates:
            raise ValueError(f"Could not find any track named '{title}' in Plex")

        return candidates[0]

    def find_similar_tracks(
        self,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        rating_key: Optional[int] = None,
        max_results: int = 50,
    ) -> List[Dict]:
        """
        Retrieve tracks that Plex considers sonically similar to the reference track.

        The reference track must already exist in the Plex library and must have
        completed Sonic Analysis.
        """
        if rating_key is not None:
            reference = self.find_track_by_rating_key(rating_key)
        else:
            if not title:
                raise ValueError("Either a title or a rating key is required")
            reference = self.find_track_by_title(title=title, artist=artist)

        if not getattr(reference, "hasSonicAnalysis", False):
            raise ValueError(
                f"Plex Sonic Analysis is not available/completed for "
                f"{getattr(reference, 'grandparentTitle', 'Unknown')} - "
                f"{reference.title}. "
                "Check your Plex Music library analysis settings."
            )

        print(
            f"Reference track found in Plex: "
            f"{getattr(reference, 'grandparentTitle', 'Unknown')} - {reference.title}"
        )

        try:
            similar = reference.sonicallySimilar(limit=max_results)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch sonically similar tracks for "
                f"{reference.title}: {exc}"
            ) from exc

        results: List[Dict] = []
        seen_ratings = set()
        seen_tracks = set()

        artist = (
            getattr(reference, "originalTitle", None)
            or getattr(reference, "grandparentTitle", None)
            or "Unknown"
        )
        results.append(
            {
                "key": reference.key,
                "title": reference.title,
                "artist": artist,
                "album": getattr(reference, "parentTitle", None) or "Unknown",
                "rating_key": getattr(reference, "ratingKey", None),
                "object": reference,
                "distance": 0.0,
            }
        )
        seen_ratings.add(getattr(reference, "ratingKey", None))
        seen_tracks.add((artist.casefold(), reference.title.casefold()))

        for track in similar:
            track_rating_key = getattr(track, "ratingKey", None)
            if (
                track_rating_key is None
                or track_rating_key == getattr(reference, "ratingKey", None)
                or track_rating_key in seen_ratings
            ):
                continue
            seen_ratings.add(track_rating_key)

            artist_name = (
                getattr(track, "originalTitle", None)
                or getattr(track, "grandparentTitle", None)
                or "Unknown"
            )
            if (artist_name.casefold(), track.title.casefold()) in seen_tracks:
                continue

            seen_tracks.add((artist_name.casefold(), track.title.casefold()))
            results.append(
                {
                    "key": track.key,
                    "title": track.title,
                    "artist": artist_name,
                    "album": getattr(track, "parentTitle", None) or "Unknown",
                    "rating_key": track_rating_key,
                    "object": track,
                    "distance": getattr(track, "distance", None),
                }
            )

        return results

    def create_playlist(self, similar_tracks: List[Dict], playlist_name: str) -> bool:
        """
        Create a Plex playlist with the found tracks.
        """
        if not similar_tracks:
            print("No similar tracks found.")
            return False

        track_objects = [item["object"] for item in similar_tracks]
        try:
            # if a playlist with the same name already exists, it will be replaced.
            playlist_exists = any(
                pl.title == playlist_name for pl in self.plex.playlists()
            )
            if playlist_exists:
                print(f"Playlist '{playlist_name}' already exists. Replacing it.")
                existing_playlist = next(
                    pl for pl in self.plex.playlists() if pl.title == playlist_name
                )
                existing_playlist.delete()

            Playlist.create(self.plex, title=playlist_name, items=track_objects)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create Plex playlist '{playlist_name}': {exc}"
            ) from exc

        print(f"Created playlist '{playlist_name}' with {len(similar_tracks)} tracks")
        for i, track in enumerate(similar_tracks[:5], 1):
            print(
                f"  {i}. {track['artist']} - {track['title']} (distance={track['distance']})"
            )
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Create a Plex playlist using Plex's built-in sonic analysis."
    )
    parser.add_argument(
        "--plex-url",
        default=os.getenv("PLEX_URL", "http://localhost:32400"),
        help="Plex server URL (default: http://localhost:32400)",
    )
    parser.add_argument(
        "--plex-token",
        default=os.getenv("PLEX_TOKEN"),
        help="Plex API token (or set PLEX_TOKEN env var)",
    )
    parser.add_argument(
        "--reference-mp3",
        help="Path to a local MP3 file; title/artist are read from its ID3v2 tags",
    )
    parser.add_argument(
        "--reference-title", help="Title of the reference track in Plex"
    )
    parser.add_argument(
        "--reference-artist",
        help="Artist of the reference track (optional but useful for duplicates)",
    )
    parser.add_argument(
        "--reference-key",
        type=int,
        help="Plex ratingKey of the reference track (alternative to title/artist/mp3)",
    )
    parser.add_argument(
        "--playlist-name",
        default=None,
        help="Name for the playlist to create",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum number of similar tracks to include",
    )
    parser.add_argument(
        "--music-section",
        default="Music",
        help="Name of the Plex music library section (default: Music)",
    )

    args = parser.parse_args()

    if not args.plex_token:
        print(
            "Error: --plex-token is required or set PLEX_TOKEN in the environment",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve reference identification: mp3 tags take priority if both
    # --reference-mp3 and --reference-title/--reference-artist are passed,
    # but explicit title/artist values override tags read from the file.
    reference_title = args.reference_title
    reference_artist = args.reference_artist

    if args.reference_mp3:
        try:
            tag_title, tag_artist = read_id3_title_artist(args.reference_mp3)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        if not tag_title and not tag_artist:
            print(
                f"Error: could not read title/artist ID3 tags from '{args.reference_mp3}'. "
                "Pass --reference-title/--reference-artist explicitly instead.",
                file=sys.stderr,
            )
            sys.exit(1)

        reference_title = reference_title or tag_title
        reference_artist = reference_artist or tag_artist

        print(
            f"Read from ID3 tags: title='{reference_title}', artist='{reference_artist}'"
        )

    if args.reference_key is None and not reference_title:
        print(
            "Error: provide --reference-mp3, --reference-title, or --reference-key",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        plex_playlist = PlexSimilarPlaylist(
            plex_url=args.plex_url,
            plex_token=args.plex_token,
            music_section_name=args.music_section,
        )

        similar_tracks = plex_playlist.find_similar_tracks(
            title=reference_title,
            artist=reference_artist,
            rating_key=args.reference_key,
            max_results=args.max_results,
        )

        if similar_tracks:
            playlist_name = args.playlist_name or f"Similar to {reference_title}"
            plex_playlist.create_playlist(similar_tracks, playlist_name)
        else:
            print("No sonically similar tracks found.")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
