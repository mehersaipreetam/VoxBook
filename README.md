# VoxBook

VoxBook is a local-first, free AI-powered smart audiobook generator and player. It allows you to compile standard PDF books into structured audiobooks with segment-level audio tracks, real-time interactive transcripts, figure extraction, and local library management.

## Features

- **Automatic Compilation Pipeline:** Parses PDF structures, extracts chapters/lessons, segments body texts, and synthesizes high-quality audio using `edge-tts` (with an offline `pyttsx3` fallback).
- **TOC Mismatch Alignment:** Dynamically calculates page offsets between printed TOC listings and actual PDF page indexes.
- **Figure & Image Extraction:** Automatically extracts embedded diagrams and figures, rendering them inline inside the corresponding page in the transcript.
- **Interactive Transcript Player:**
  - High-frequency 60fps tracking that highlights the active sentence as it is spoken.
  - Click-to-seek jump points directly from any sentence in the transcript.
- **Permanent Deletion:** Permanently delete compiled books from the UI and backend manifest.
- **Local LLM Integration:** Optional Table of Contents parsing using a local Ollama instance (`llama3.2` 3B).

## Project Structure

- `/backend` - FastAPI server, text extractors, TTS synthesizers, and structuring logic.
- `/frontend` - React/Vite client SPA styled with Vanilla CSS.

## Setup & Running

### Requirements
- Python 3.10 to 3.12 (managed via `uv`)
- Node.js
- Ollama (running locally with `llama3.2`)

### 1. Run the Backend API Server
Navigate to the `/backend` directory and start the server:
```bash
uv run python server.py
```

### 2. Run the Frontend Dev Server
Navigate to the `/frontend` directory and start the dev server:
```bash
npm run dev
```
Open the Dev URL (e.g. `http://localhost:5174/`) in your browser.

### 3. CLI Pipeline Compiler (Optional)
You can also compile PDF books directly from the command line:
```bash
uv run backend/main.py path/to/your/book.pdf
```
