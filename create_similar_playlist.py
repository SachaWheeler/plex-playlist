#!/usr/bin/env python3
"""
Create a Plex playlist from tracks that Plex says are sonically similar
to a reference track already in the library.

Requirements:
- Plex server running
- PlexAPI installed
- Music library section called "Music" (or change section name below)
- Reference track already exists in Plex
- Sonic Analysis enabled/completed for that reference track

Example:
    python create_playlist.py \
      --reference-title "Teardrop" \
      --reference-artist "Massive Attack" \
      --playlist-name "Similar to Teardrop" \
      --max-results 50
"""

import os
import sys
import argparse
from typing import List, Dict, Optional

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
                raise ValueError(
                    "Either --reference-title or --reference-key is required"
                )
            reference = self.find_track_by_title(title=title, artist=artist)

        if not getattr(reference, "hasSonicAnalysis", False):
            raise ValueError(
                f"Plex Sonic Analysis is not available/completed for "
                f"{getattr(reference, 'grandparentTitle', 'Unknown')} - "
                f"{reference.title}. "
                "Check your Plex Music library analysis settings."
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

        for track in similar:
            track_rating_key = getattr(track, "ratingKey", None)
            if track_rating_key is None:
                continue
            if track_rating_key == getattr(reference, "ratingKey", None):
                continue
            if track_rating_key in seen_ratings:
                continue
            seen_ratings.add(track_rating_key)

            results.append(
                {
                    "key": track.key,
                    "title": track.title,
                    "artist": getattr(track, "originalTitle", None)
                    or getattr(track, "grandparentTitle", None)
                    or "Unknown",
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

        # sort by distance if available
        similar_tracks.sort(key=lambda x: x.get("distance", float("inf")))

        track_objects = [item["object"] for item in similar_tracks]
        try:
            # This is the version-safe PlexAPI pattern.
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
        "--reference-title", help="Title of the reference track in Plex"
    )
    parser.add_argument(
        "--reference-artist",
        help="Artist of the reference track (optional but useful for duplicates)",
    )
    parser.add_argument(
        "--reference-key",
        type=int,
        help="Plex ratingKey of the reference track (alternative to title/artist)",
    )
    parser.add_argument(
        "--playlist-name", default=None, help="Name for the playlist to create"
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

    if args.reference_key is None and not args.reference_title:
        print("Error: provide --reference-title or --reference-key", file=sys.stderr)
        sys.exit(1)

    try:
        plex_playlist = PlexSimilarPlaylist(
            plex_url=args.plex_url,
            plex_token=args.plex_token,
            music_section_name=args.music_section,
        )

        similar_tracks = plex_playlist.find_similar_tracks(
            title=args.reference_title,
            artist=args.reference_artist,
            rating_key=args.reference_key,
            max_results=args.max_results,
        )

        if similar_tracks:
            playlist_name = args.playlist_name or f"Similar to {args.reference_title}"
            plex_playlist.create_playlist(similar_tracks, playlist_name)
        else:
            print("No sonically similar tracks found.")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
