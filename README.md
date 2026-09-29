# Plex Similar Playlist

Create a Plex playlist from tracks that Plex considers sonically similar to a reference track.

The script uses Plex's built-in Sonic Analysis feature to find similar music tracks. The reference track can be identified by:

- A local MP3 file, using its ID3 title and artist tags
- A track title and artist name
- A Plex `ratingKey`

## Requirements

- Python 3.8 or newer
- A running Plex Media Server
- A Plex music library
- PlexAPI
- Mutagen
- Sonic Analysis enabled and completed for the reference track
- The reference track must already exist in Plex

The script expects the Plex music library section to be named `Music` by default.

## Installation

Clone or download this repository, then install the required dependencies:

```bash
pip install PlexAPI mutagen
```

The script also attempts to install missing dependencies automatically, but installing them manually is recommended.

## Plex API Token

The script requires a Plex API token. You can provide it directly with `--plex-token` or set the `PLEX_TOKEN` environment variable.

```bash
export PLEX_TOKEN="your-plex-token"
```

The Plex server URL defaults to:

```text
http://localhost:32400
```

To use a different server, set `PLEX_URL`:

```bash
export PLEX_URL="http://192.168.1.100:32400"
```

You can also pass the URL directly with `--plex-url`.

## Usage

### Use a local MP3 file

The script reads the title and artist from the MP3's ID3 tags and searches for the matching track in Plex.

```bash
python create_similar_playlist.py \
  --reference-mp3 "/home/sacha/Music/Massive Attack/Teardrop.mp3" \
  --playlist-name "Similar to Teardrop" \
  --max-results 50
```

### Specify the title and artist

```bash
python create_similar_playlist.py \
  --reference-title "Teardrop" \
  --reference-artist "Massive Attack" \
  --playlist-name "Similar to Teardrop"
```

The artist is optional, but is useful when multiple tracks have the same title.

```bash
python create_similar_playlist.py \
  --reference-title "Teardrop"
```

### Use a Plex rating key

A Plex `ratingKey` uniquely identifies a track and avoids title-matching ambiguity.

```bash
python create_similar_playlist.py \
  --reference-key 12345 \
  --playlist-name "Similar Tracks"
```

### Use a custom Plex server URL

```bash
python create_similar_playlist.py \
  --plex-url "http://192.168.1.100:32400" \
  --plex-token "your-plex-token" \
  --reference-title "Teardrop" \
  --reference-artist "Massive Attack"
```

### Use a different music library section

If your Plex music library is not named `Music`, specify its name:

```bash
python create_similar_playlist.py \
  --music-section "My Music" \
  --reference-title "Teardrop" \
  --reference-artist "Massive Attack"
```

## Command-line options

| Option | Description | Default |
|---|---|---|
| `--plex-url` | Plex server URL | `http://localhost:32400` |
| `--plex-token` | Plex API token | `PLEX_TOKEN` environment variable |
| `--reference-mp3` | Local MP3 file used to read title and artist tags | None |
| `--reference-title` | Reference track title in Plex | None |
| `--reference-artist` | Reference track artist in Plex | None |
| `--reference-key` | Plex rating key for the reference track | None |
| `--playlist-name` | Name of the playlist to create | `Similar to <reference title>` |
| `--max-results` | Maximum number of similar tracks to request | `50` |
| `--music-section` | Plex music library section name | `Music` |

## Reference track resolution

The script resolves the reference track in the following order:

1. If `--reference-key` is provided, it is used directly.
2. If `--reference-mp3` is provided, the script reads the MP3's title and artist tags.
3. Explicit `--reference-title` and `--reference-artist` values take precedence over values read from the MP3.
4. The title and optional artist are used to search the Plex music library.

For example, explicit values override tags from the MP3:

```bash
python create_similar_playlist.py \
  --reference-mp3 "/music/example.mp3" \
  --reference-title "Different Title" \
  --reference-artist "Different Artist"
```

## Playlist behavior

When the script runs:

1. It connects to Plex.
2. It locates the reference track.
3. It verifies that Sonic Analysis is available.
4. It requests tracks that Plex considers sonically similar.
5. It adds the reference track and similar tracks to the result set.
6. It creates a Plex playlist.
7. If a playlist with the same name already exists, it deletes and replaces it.

The reference track is included as the first item in the playlist.

Duplicate tracks are removed using both Plex rating keys and artist/title pairs.

## Sonic Analysis

The reference track must have completed Plex Sonic Analysis. If analysis is unavailable, the script exits with an error similar to:

```text
Plex Sonic Analysis is not available/completed for ...
```

To resolve this:

1. Open Plex Media Server.
2. Go to the Music library settings.
3. Ensure Sonic Analysis is enabled.
4. Analyze or refresh the reference track.
5. Wait for analysis to complete.
6. Run the script again.

The exact Sonic Analysis settings may depend on your Plex Media Server version.

## MP3 metadata

When using `--reference-mp3`, the script looks for:

- `TIT2` — title
- `TPE1` — artist

It first attempts to read tags through Mutagen's easy-access interface and then falls back to raw ID3 frames.

If the file has no readable title or artist tags, specify the values manually:

```bash
python create_similar_playlist.py \
  --reference-mp3 "/music/example.mp3" \
  --reference-title "Example Track" \
  --reference-artist "Example Artist"
```

## Examples

Create a playlist with the default limit of 50 tracks:

```bash
python create_similar_playlist.py \
  --reference-title "Bachelorette" \
  --reference-artist "Björk"
```

Create a playlist with up to 100 tracks:

```bash
python create_similar_playlist.py \
  --reference-title "Bachelorette" \
  --reference-artist "Björk" \
  --max-results 100 \
  --playlist-name "Björk - Similar Tracks"
```

Use environment variables for Plex connection details:

```bash
export PLEX_URL="http://localhost:32400"
export PLEX_TOKEN="your-plex-token"

python create_similar_playlist.py \
  --reference-key 12345 \
  --playlist-name "Plex Sonic Recommendations"
```

## Troubleshooting

### `PlexAPI` or `mutagen` is not installed

Install the dependencies manually:

```bash
pip install PlexAPI mutagen
```

### Plex library section not found

Check the library name in Plex and pass it using `--music-section`:

```bash
python create_similar_playlist.py \
  --music-section "My Music" \
  --reference-title "Track Title"
```

### Track cannot be found

Verify that:

- The track exists in the Plex music library.
- The title matches the Plex metadata.
- The artist name is correct.
- The correct music library section is being used.
- You are not searching for a file that has not been added to Plex.

Using `--reference-key` can avoid title and artist matching problems.

### The playlist already exists

Existing playlists with the requested name are automatically deleted and recreated.

Choose a different name if you do not want to replace an existing playlist.

### Plex connection errors

Check that:

- Plex Media Server is running.
- The server URL is correct.
- The API token is valid.
- The machine running the script can reach the Plex server.
- The Plex server is not blocking the connection.

## Security

Avoid committing your Plex token to source control. Prefer an environment variable:

```bash
export PLEX_TOKEN="your-plex-token"
```

If you pass the token directly on the command line, it may be visible in shell history or process listings.

## License

MIT License

Copyright (c) 2026 Sacha Wheeler

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

