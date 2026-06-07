# Mo Reader

Mo reader is a powerful, offline-first Chinese reading and dictionary web application designed for language learners. It offers a standalone, serverless experience that works seamlessly across desktop and mobile devices.

## Key Features

- **Offline Dictionary & Reader:** Fully functional without an internet connection, built as a self-contained web app.
- **Android Webapp Bundling:** Includes a Python build script (`build_android.py`) that packages HTML, CSS, JavaScript, fonts, and dependencies into a single deployable file for mobile devices.
- **Audio Transcription Workflow:** Streamlined process (`chinread.py`) to record system audio, transcribe it, and organize the output for reading sessions.
- **Advanced Dictionary Enrichment:** Automated background pipeline to fetch Chinese synonyms and enrich the local dictionary data dynamically.
- **Smart Highlighting:** Automatically highlights known vocabulary words from your local dictionary to reinforce learning memory while reading.
- **Syntax & POS Color Coding:** Context-aware colorization for parts of speech (verbs, adjectives, adverbs), improving visual structure and reading comprehension.
- **Session Management:** Hierarchical tree-based navigation mirroring the local file system, with tracking of the most-read sessions.
- **Custom Font Support:** Embedded local typography resources ensuring consistent aesthetics without external calls.

## Project Structure

- `reader.html` - The main interface for the reading application.
- `Dict/` - Local dictionary storage.
- `Sessions/` - Stores your reading content and transcribed audio sessions.
- `js/`, `css/`, `fonts/`, `libs/` - Modular frontend assets.
- `build_android.py` - Script to bundle all assets into a single static file (`android/Chinread-Mobile.html`).
- `chinread.py` - Helper script for audio transcription and alignment.
- `enrich_dict.py`, `enrich.sh` - Scripts for automating dictionary data augmentation.

## Usage

1. Open `reader.html` in your browser for desktop usage.
2. For Android offline usage, run `python build_android.py` to generate the bundled `.html` file.
3. Use the sidebar to seamlessly navigate and read your stored sessions.

### Creating a Reading Session (Transcribing Audio)

Because you have configured a custom Bash wrapper (`chread`) on your system, you have zero friction. Simply place your recorded audio file into a new directory inside `Sessions/`, navigate to that folder, and run:

```bash
# Automatically transcribes current audio using the OpenAI API
chread audio.mp3 --online
```
This wrapper automatically activates your `whisperx` Conda environment and executes `chinread.py` behind the scenes. It generates the `audio.json` perfectly segmented right next to your mp3 file. 

### Dictionary Enrichment

I have just modified `enrich_dict.py` so that it automatically defaults to `Dict/chinese_reader_dictionary_backup.json` from the repository. You **never need to type the source or output file paths again**. 

Run the existing `enrich.sh` helper from anywhere on your system:
```bash
~/Ai/Chinread/enrich.sh
```
It will always auto-detect your `.env` key, load the default dictionary, and output `chinese_reader_dictionary_backup_enriched.json` perfectly. 

### Moving to a New PC (Future-Proofing)
If you ever clone this on a new PC and forget how you set up your frictionless terminal commands, refer to the `commands.md` file in this repository. It contains the exact scripts you originally placed in your `~/.local/bin/` folder to achieve this!
