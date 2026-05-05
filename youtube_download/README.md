# opencli-plugin-aiskill

AI-powered skills for everyday workflows — YouTube video download and more.

## Commands

| Command | Description |
|---------|-------------|
| `aiskill/youtube-download` | Download YouTube videos via yt-dlp with proxy auto-detection |

## Install

```bash
# From GitHub
opencli plugin install github:ftyszyx/aiskill

# From local directory (for development)
opencli plugin install file://./aiskill
```

## Requirements

- **yt-dlp** — install with `pip install yt-dlp`
- **A local proxy** for YouTube access (Clash, V2Ray, etc. on ports 7890, 1080, etc.)

## Usage

```bash
# Download with auto-detected proxy (best quality)
opencli aiskill youtube-download https://www.youtube.com/watch?v=XqKcYMLMV6E

# Specify quality
opencli aiskill youtube-download XqKcYMLMV6E --quality 1080p

# Custom output directory
opencli aiskill youtube-download XqKcYMLMV6E --output ./downloads --quality 720p

# Manual proxy
opencli aiskill youtube-download XqKcYMLMV6E --proxy http://127.0.0.1:7890
```

## How It Works

1. **Proxy auto-detection** — probes common local proxy ports (7890, 1080, 10809) to find an active proxy
2. **Metadata extraction** — navigates to the video page via the user's browser (CDP) to get the video title
3. **Download** — spawns `yt-dlp` with the detected proxy to download the best video + audio, merging into MKV
4. **Output** — saves to the current directory (or `--output`) with the video title as the filename
