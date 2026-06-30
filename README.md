# Vault-Tec Greeting System

[![Support me on Patreon](https://img.shields.io/badge/Patreon-Support%20my%20work-FF424D?style=flat&logo=patreon&logoColor=white)](https://www.patreon.com/AndersBjarby)

A Fallout-themed video greeter. Drop a video clip of someone arriving at (or leaving) "the Vault" into a watched folder and the script analyzes it, writes a cheerfully ominous Vault-Tec greeting, voices it, mixes it over background music, and saves a finished audio file.

## What it does

- Watches an `input/` folder for new video files (`.mp4`, `.mov`, `.avi`)
- Extracts keyframes with FFmpeg and uses an OpenAI vision model to detect whether the visitor is **arriving** or **leaving** and describe them
- Generates a short, in-character Vault-Tec greeting (1950s-ad cheerfulness with dark undertones)
- Synthesizes speech with ElevenLabs
- Ducks a random track from `music/` under the speech and renders the final mix to `output/`
- Deletes the processed input file automatically

## Setup

Requires Python, FFmpeg, and a `.env` file with API keys:

```bash
pip install openai python-dotenv ffmpeg-python requests watchdog
```

```env
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
```

## Usage

```bash
python welcome.py
```

It creates the `input/`, `output/`, and `music/` folders on start. Add `.mp3`/`.wav` tracks to `music/`, then drop a video into `input/` and the greeting is generated automatically.

## Tech

Python, OpenAI (vision + chat), ElevenLabs TTS, FFmpeg, watchdog.
