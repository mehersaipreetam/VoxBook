import os
import sys
import json
import asyncio

# Adjust path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tts.synthesizer import SpeechSynthesizer
from main import slugify

async def main():
    book_title = "Welcome to VoxBook"
    author = "VoxBook Team"
    book_slug = slugify(book_title)
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "public", "books")
    book_output_dir = os.path.join(output_dir, book_slug)
    audio_output_dir = os.path.join(book_output_dir, "audio")
    
    os.makedirs(audio_output_dir, exist_ok=True)
    
    print(f"[*] Compiling default welcome audiobook: {book_title}")
    
    lessons = [
        {
            "lesson_id": "ch1_l1",
            "chapter_title": "Chapter 1: Getting Started",
            "chapter_number": 1,
            "title": "1.1 What is VoxBook?",
            "text": "Welcome to VoxBook, your free and local AI-powered smart audiobook generator. VoxBook transforms static PDF books into interactive, chapter-earmarked web audio players. Instead of a single long audio file, the system parses the PDF's chapters and lessons to create a dynamic Table of Contents. You can listen on a web-based player, skip to specific lessons, and save your progress locally in your browser."
        },
        {
            "lesson_id": "ch1_l2",
            "chapter_title": "Chapter 1: Getting Started",
            "chapter_number": 1,
            "title": "1.2 How it Works",
            "text": "VoxBook works in two major parts. First, the Python preprocessing pipeline parses your PDF, strips headers and footers, structures the text, and synthesizes it into high-quality local MP3 files. Second, the React web player loads the generated assets statically. There is no active server or database required to run the player; it is completely local-first."
        },
        {
            "lesson_id": "ch2_l1",
            "chapter_title": "Chapter 2: Guide",
            "chapter_number": 2,
            "title": "2.1 Generating Books",
            "text": "To compile your own audiobooks, simply drop a PDF into the project and run the backend script. Open your terminal, go to the backend directory, and run the command: uv run main.py path to your book dot pdf. The pipeline will automatically parse, structure, synthesize, and add the book to your local library. Once finished, refresh this page to start listening."
        }
    ]
    
    synthesizer = SpeechSynthesizer()
    total_duration = 0.0
    
    # Process structured chapters
    chapters_map = {}
    
    for l in lessons:
        ch_num = l["chapter_number"]
        if ch_num not in chapters_map:
            chapters_map[ch_num] = {
                "chapter_number": ch_num,
                "chapter_title": l["chapter_title"],
                "lessons": []
            }
            
        track_filename = f"{l['lesson_id']}.mp3"
        track_path = os.path.join(audio_output_dir, track_filename)
        
        print(f"    -> Synthesizing track: {l['title']}...")
        duration = await synthesizer.synthesize_async(l["text"], track_path)
        total_duration += duration
        
        chapters_map[ch_num]["lessons"].append({
            "lesson_id": l["lesson_id"],
            "title": l["title"],
            "audio_file": f"/books/{book_slug}/audio/{track_filename}",
            "duration_seconds": round(duration, 2)
        })
        
    # Sort and construct chapter list
    chapters_list = [chapters_map[k] for k in sorted(chapters_map.keys())]
    
    # Write metadata.json
    metadata = {
        "book_id": book_slug,
        "book_title": book_title,
        "author": author,
        "total_chapters": len(chapters_list),
        "total_duration_seconds": round(total_duration, 2),
        "cover_url": f"/books/{book_slug}/cover.jpg",
        "chapters": chapters_list
    }
    
    metadata_json_path = os.path.join(book_output_dir, "metadata.json")
    with open(metadata_json_path, "w") as f:
        json.dump(metadata, f, indent=2)
        
    # Write empty cover placeholder
    cover_path = os.path.join(book_output_dir, "cover.jpg")
    with open(cover_path, "wb") as f:
        f.write(b"")
        
    # Update books.json manifest
    manifest_path = os.path.join(output_dir, "books.json")
    books_manifest = []
    
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                books_manifest = json.load(f)
        except Exception:
            books_manifest = []
            
    # Remove existing
    books_manifest = [b for b in books_manifest if b.get("id") != book_slug]
    
    books_manifest.append({
        "id": book_slug,
        "title": book_title,
        "author": author,
        "cover_url": f"/books/{book_slug}/cover.jpg",
        "path": f"/books/{book_slug}/metadata.json"
    })
    
    with open(manifest_path, "w") as f:
        json.dump(books_manifest, f, indent=2)
        
    print("[+] Welcome book generated successfully!")

if __name__ == "__main__":
    asyncio.run(main())
