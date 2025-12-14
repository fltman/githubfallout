import os
import json
import base64
import random
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import ffmpeg
import subprocess
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv()

# Configuration
config = {
    'watch_directory': 'input',
    'output_directory': 'output',
    'openai_api_key': os.getenv('OPENAI_API_KEY'),
    'elevenlabs_api_key': os.getenv('ELEVENLABS_API_KEY')
}

if not config['openai_api_key'] or not config['elevenlabs_api_key']:
    raise ValueError("Missing required API keys in .env file")

openai_client = OpenAI(api_key=config['openai_api_key'])

# Vault-Tec configuration
VAULT_TEC_VOICE_ID = "bSavelQ2BLlnmVngFsig"

VAULT_TEC_PERSONALITY = """You are a Vault-Tec automated greeting system from the Fallout universe.
Speak like a 1950s American advertisement - aggressively cheerful and unnervingly optimistic.
Crisp, over-enunciated delivery like old educational films.
Deliver dark or concerning observations with sunny enthusiasm, as if selling soap.
Reference Vault-Tec products, S.P.E.C.I.A.L. stats, and survival tips casually.
Keep responses SHORT - one or two sentences maximum.
Think 'Duck and Cover' narrator on happy pills."""

VAULT_TEC_ARRIVING_PROMPT = """The visitor is ARRIVING at the Vault entrance.
Welcome them warmly while subtly assessing their potential as a Vault dweller.
Comment on their appearance, preparedness, or potential usefulness."""

VAULT_TEC_LEAVING_PROMPT = """The visitor is LEAVING the Vault.
Bid them farewell with cheerful warnings about the wasteland dangers outside.
Remind them of Vault-Tec's superior safety, and wish them luck (they'll need it)."""

MUSIC_DIRECTORY = "music"
MUSIC_INTRO_DURATION = 5  # sekunder på 100%
MUSIC_DUCKED_VOLUME = 0.10  # 10% volym under tal


def extract_keyframes(video_path, num_frames=4):
    """Extract keyframes using FFmpeg"""
    temp_dir = Path("temp_frames")
    temp_dir.mkdir(exist_ok=True)

    try:
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration'])
        timestamps = [i * (duration / num_frames) for i in range(num_frames)]

        keyframes = []
        for i, timestamp in enumerate(timestamps):
            output_path = temp_dir / f"frame_{i}.jpg"

            try:
                stream = ffmpeg.input(video_path, ss=timestamp)
                stream = ffmpeg.output(stream, str(output_path),
                                      vframes=1,
                                      loglevel='error',
                                      **{'qscale:v': 2})
                ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)

                if output_path.exists() and output_path.stat().st_size > 0:
                    with open(output_path, 'rb') as f:
                        keyframes.append(base64.b64encode(f.read()).decode())
            except Exception as e:
                print(f"Error extracting frame {i}: {e}")

        return keyframes

    except Exception as e:
        print(f"Error in extract_keyframes: {e}")
        raise


def analyze_visitor(frames):
    """Analyze visitor with GPT-4 and generate Vault-Tec greeting"""
    print(f"Analyzing {len(frames)} frames...")

    # First, determine direction of movement
    direction_content = [
        {
            "type": "text",
            "text": "These frames show a visitor at a door/entrance. Based on the sequence, is the person ARRIVING (approaching, getting closer, entering) or LEAVING (moving away, exiting, departing)? Reply with only one word: ARRIVING or LEAVING"
        }
    ]

    for frame_data in frames:
        direction_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame_data}"}
        })

    direction_response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": direction_content}],
        max_tokens=10
    )

    direction = direction_response.choices[0].message.content.strip().upper()
    is_arriving = "ARRIVING" in direction

    print(f"Detected direction: {'ARRIVING' if is_arriving else 'LEAVING'}")

    # Generate appropriate greeting
    context_prompt = VAULT_TEC_ARRIVING_PROMPT if is_arriving else VAULT_TEC_LEAVING_PROMPT

    greeting_content = [
        {
            "type": "text",
            "text": f"Based on these frames of a visitor, deliver a SHORT Vault-Tec message (max 250 characters). {VAULT_TEC_PERSONALITY} {context_prompt}"
        }
    ]

    for frame_data in frames:
        greeting_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame_data}"}
        })

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": greeting_content}],
        max_tokens=350
    )

    greeting = response.choices[0].message.content
    print(f"Generated greeting: {greeting}")
    return greeting, is_arriving


def generate_speech(text, output_path):
    """Generate speech using ElevenLabs"""
    print(f"Generating speech...")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VAULT_TEC_VOICE_ID}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": config['elevenlabs_api_key']
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.5,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise Exception(f"ElevenLabs API error: {response.text}")

    with open(output_path, 'wb') as f:
        f.write(response.content)

    print(f"Speech saved to: {output_path}")
    return output_path


def get_random_music():
    """Select random music file from music directory"""
    music_dir = Path(MUSIC_DIRECTORY)
    music_files = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))

    if not music_files:
        raise FileNotFoundError(f"No music files found in {MUSIC_DIRECTORY}")

    selected = random.choice(music_files)
    print(f"Selected music: {selected.name}")
    return str(selected)


def get_audio_duration(audio_path):
    """Get duration of audio file"""
    probe = ffmpeg.probe(audio_path)
    return float(probe['format']['duration'])


def create_final_audio(speech_path, output_path):
    """Combine music and speech with volume ducking"""
    music_path = get_random_music()
    speech_duration = get_audio_duration(speech_path)
    total_duration = MUSIC_INTRO_DURATION + speech_duration + 1  # +1 för utfadning

    print(f"Creating final audio...")
    print(f"Speech duration: {speech_duration:.2f}s")
    print(f"Total duration: {total_duration:.2f}s")

    # FFmpeg filter för volym-ducking:
    # - Musik på 100% i 5 sekunder
    # - Fade ner till 10% över 0.5 sekunder
    # - Håll 10% under talet
    # - Fade ut på slutet

    filter_complex = (
        f"[0:a]volume=1:enable='lt(t,{MUSIC_INTRO_DURATION})',"
        f"volume={MUSIC_DUCKED_VOLUME}:enable='gte(t,{MUSIC_INTRO_DURATION})',"
        f"afade=t=out:st={total_duration - 1}:d=1[music];"
        f"[1:a]adelay={int(MUSIC_INTRO_DURATION * 1000)}|{int(MUSIC_INTRO_DURATION * 1000)}[speech];"
        f"[music][speech]amix=inputs=2:duration=longest"
    )

    cmd = [
        'ffmpeg', '-y',
        '-i', music_path,
        '-i', speech_path,
        '-filter_complex', filter_complex,
        '-t', str(total_duration),
        '-ac', '2',
        '-ar', '44100',
        output_path
    ]

    print(f"Running FFmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        raise Exception("Failed to create final audio")

    print(f"Final audio created: {output_path}")
    return output_path


def process_video(video_path):
    """Main processing pipeline"""
    print(f"\n{'='*50}")
    print(f"Processing: {video_path}")
    print(f"{'='*50}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = Path("temp_audio")
    temp_dir.mkdir(exist_ok=True)

    try:
        # 1. Extrahera frames
        frames = extract_keyframes(video_path, num_frames=4)

        # 2. Analysera och generera hälsning
        greeting, is_arriving = analyze_visitor(frames)

        # 3. Generera tal
        speech_path = temp_dir / f"speech_{timestamp}.mp3"
        generate_speech(greeting, str(speech_path))

        # 4. Kombinera med musik
        direction_tag = "arriving" if is_arriving else "leaving"
        output_filename = f"vault_tec_{direction_tag}_{timestamp}.mp3"
        output_path = Path(config['output_directory']) / output_filename
        create_final_audio(str(speech_path), str(output_path))

        print(f"\n✓ Complete! Output: {output_path}")
        return str(output_path)

    except Exception as e:
        print(f"Error processing video: {e}")
        raise
    finally:
        cleanup_temp_directories()


def cleanup_temp_directories():
    """Clean up temporary directories"""
    for dir_name in ['temp_frames', 'temp_audio']:
        dir_path = Path(dir_name)
        if dir_path.exists():
            for file in dir_path.glob('*'):
                try:
                    file.unlink()
                except Exception as e:
                    print(f"Error deleting {file}: {e}")


def is_file_ready(file_path, check_time=5, check_interval=0.5):
    """Check if file is ready for processing"""
    initial_size = Path(file_path).stat().st_size
    checks = int(check_time / check_interval)

    for _ in range(checks):
        time.sleep(check_interval)
        current_size = Path(file_path).stat().st_size
        if current_size != initial_size:
            return False
        initial_size = current_size
    return True


class VideoHandler(FileSystemEventHandler):
    def __init__(self):
        self.processing_files = set()

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(('.mp4', '.mov', '.avi')):
            return

        file_path = event.src_path

        if file_path in self.processing_files:
            return

        try:
            self.processing_files.add(file_path)
            time.sleep(1)

            if not is_file_ready(file_path):
                print(f"File still being written: {file_path}")
                return

            process_video(file_path)

            # Ta bort input-filen efter processning
            Path(file_path).unlink()
            print(f"Deleted input file: {file_path}")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.processing_files.discard(file_path)


def main():
    cleanup_temp_directories()

    # Skapa nödvändiga mappar
    Path(config['output_directory']).mkdir(exist_ok=True)
    Path(MUSIC_DIRECTORY).mkdir(exist_ok=True)
    Path(config['watch_directory']).mkdir(exist_ok=True)

    print(f"Vault-Tec Greeting System Online")
    print(f"Monitoring: {config['watch_directory']}")
    print(f"Output: {config['output_directory']}")
    print(f"Music: {MUSIC_DIRECTORY}/")

    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, config['watch_directory'], recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
