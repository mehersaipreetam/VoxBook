import os
import sys
import json
import argparse
import re
from typing import List, Dict, Any
import asyncio

# Adjust path to allow importing local modules if run directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parser.pdf_extractor import PDFExtractor
from parser.llm_structurer import LLMStructurer
from tts.synthesizer import SpeechSynthesizer

def slugify(text: str) -> str:
    """Converts a title into a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

def segment_text_by_lessons(pages: List[Dict[str, Any]], structured_book: Dict[str, Any]) -> Dict[str, str]:
    """Segments the book's full text into individual lessons.

    Args:
        pages: The raw pages containing text blocks.
        structured_book: The JSON metadata representing the book structure.

    Returns:
        A dictionary mapping lesson_id to its corresponding text content.
    """
    # Flatten all text blocks in order
    all_blocks = []
    for p in pages:
        for b in p["blocks"]:
            all_blocks.append(b["text"])

    # Flatten the list of lessons we need to find
    flat_lessons = []
    for chapter in structured_book.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            flat_lessons.append(lesson)

    lesson_texts = {}
    if not flat_lessons:
        return lesson_texts

    # Find the starting index in all_blocks for each lesson
    lesson_start_indices = []
    
    for idx, lesson in enumerate(flat_lessons):
        title = lesson["title"].lower().strip()
        # Clean title for looser matching
        clean_title = re.sub(r'[^a-z0-9]', '', title)
        
        found_idx = -1
        # Search blocks for a title match
        for b_idx, block_text in enumerate(all_blocks):
            clean_block = re.sub(r'[^a-z0-9]', '', block_text.lower())
            
            # Match if block contains the title or title contains the block (short titles)
            if (clean_title in clean_block or (len(clean_block) > 4 and clean_block in clean_title)):
                found_idx = b_idx
                break
        
        if found_idx != -1:
            lesson_start_indices.append((idx, lesson["lesson_id"], found_idx))
        else:
            # If not found, place it proportionally through the blocks as fallback
            proportional_idx = int((idx / len(flat_lessons)) * len(all_blocks))
            lesson_start_indices.append((idx, lesson["lesson_id"], proportional_idx))

    # Sort by block index to ensure correct ordering
    lesson_start_indices.sort(key=lambda x: x[2])

    # Slice blocks for each lesson
    for i in range(len(lesson_start_indices)):
        current_flat_idx, lesson_id, start_block_idx = lesson_start_indices[i]
        
        if i < len(lesson_start_indices) - 1:
            end_block_idx = lesson_start_indices[i+1][2]
        else:
            end_block_idx = len(all_blocks)

        # Handle edge case where indices are misaligned
        if start_block_idx >= end_block_idx:
            end_block_idx = start_block_idx + 1

        lesson_blocks = all_blocks[start_block_idx:end_block_idx]
        lesson_texts[lesson_id] = " ".join(lesson_blocks)

    return lesson_texts

async def process_book_pipeline(pdf_path: str, output_dir: str, voice: str) -> None:
    """Orchestrates the entire PDF-to-audiobook generation pipeline.

    Args:
        pdf_path: Path to the input PDF.
        output_dir: Root directory for compiled books.
        voice: Voice name to use for TTS.
    """
    print(f"[*] Starting VoxBook pipeline for: {pdf_path}")
    
    # 1. PDF Extraction
    extractor = PDFExtractor(pdf_path)
    extractor.open()
    print("[+] Extracting text from PDF...")
    pages = extractor.extract_pages()
    extractor.close()
    
    # 2. Structural Parsing
    print("[+] Identifying book structure (Chapters & Lessons)...")
    structurer = LLMStructurer()
    structured_book = structurer.structure_book(pages)
    
    book_title = structured_book.get("book_title", "Untitled Book")
    if book_title == "Untitled Book" or not book_title.strip():
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        book_title = re.sub(r'[\-_]+', ' ', base_name).title()
        structured_book["book_title"] = book_title
        
    author = structured_book.get("author", "Local Compiler")
    book_slug = slugify(book_title)
    
    print(f"[+] Book Title: {book_title}")
    print(f"[+] Author: {author}")
    print(f"[+] Target ID (slug): {book_slug}")
    
    # 3. Text Segmentation
    print("[+] Segmenting book text by lesson...")
    lesson_texts = {}
    
    has_page_ranges = False
    for chapter in structured_book.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            if "start_page" in lesson and "end_page" in lesson:
                has_page_ranges = True
                break
        if has_page_ranges:
            break
            
    if has_page_ranges:
        print("    -> Extracting text directly from page ranges...")
        for chapter in structured_book.get("chapters", []):
            for lesson in chapter.get("lessons", []):
                start = lesson["start_page"]
                end = lesson["end_page"]
                lesson_pages = pages[start-1:end]
                lesson_texts[lesson["lesson_id"]] = " ".join([p["full_text"] for p in lesson_pages])
    else:
        print("    -> Segmenting text by block search-and-slice...")
        lesson_texts = segment_text_by_lessons(pages, structured_book)
    
    # 4. Audio Synthesis (TTS)
    synthesizer = SpeechSynthesizer(voice=voice)
    book_output_dir = os.path.join(output_dir, book_slug)
    audio_output_dir = os.path.join(book_output_dir, "audio")
    os.makedirs(audio_output_dir, exist_ok=True)
    
    # Initialize general metadata structure
    structured_book["book_id"] = book_slug
    structured_book["total_chapters"] = len(structured_book.get("chapters", []))
    structured_book["total_duration_seconds"] = 0.0
    structured_book["cover_url"] = f"/books/{book_slug}/cover.jpg"
    structured_book["status"] = "processing"
    structured_book["progress"] = 0

    # Ensure images output directory exists
    images_dir = os.path.join(book_output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Reopen extractor to extract page images
    extractor.open()

    # Pre-initialize lessons to empty fields and store text transcript/pages
    for chapter in structured_book.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            lesson_id = lesson["lesson_id"]
            lesson["text"] = lesson_texts.get(lesson_id, "")
            lesson["audio_file"] = ""
            lesson["duration_seconds"] = 0.0
            
            # Map page ranges and extract images
            start = lesson.get("start_page", 0)
            end = lesson.get("end_page", 0)
            lesson["pages"] = []
            
            if start > 0 and end >= start:
                for p_num in range(start, end + 1):
                    p_text = ""
                    if p_num <= len(pages):
                        p_text = pages[p_num - 1]["full_text"]
                    
                    p_images = extractor.extract_page_images(p_num, images_dir, book_slug)
                    
                    lesson["pages"].append({
                        "page_number": p_num,
                        "text": p_text,
                        "images": p_images
                    })
            else:
                # Fallback if no page ranges are present
                lesson["pages"].append({
                    "page_number": 1,
                    "text": lesson["text"],
                    "images": []
                })
                
    extractor.close()

    # Write initial cover placeholder
    cover_path = os.path.join(book_output_dir, "cover.jpg")
    if not os.path.exists(cover_path):
        with open(cover_path, "wb") as f:
            f.write(b"")

    # Write initial metadata.json (status: processing)
    metadata_json_path = os.path.join(book_output_dir, "metadata.json")
    with open(metadata_json_path, "w") as f:
        json.dump(structured_book, f, indent=2)

    # Register in global books.json manifest immediately
    manifest_path = os.path.join(output_dir, "books.json")
    books_manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                books_manifest = json.load(f)
        except Exception:
            books_manifest = []

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
    print(f"[+] Book registered in manifest immediately: {book_slug}")

    print("[+] Synthesizing lessons into audio tracks...")
    
    total_duration = 0.0
    total_lessons = sum(len(c.get("lessons", [])) for c in structured_book.get("chapters", []))
    completed_lessons = 0

    # Add timing/track information to structured metadata incrementally
    for chapter in structured_book.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            lesson_id = lesson["lesson_id"]
            text_to_speak = lesson_texts.get(lesson_id, "")
            
            # Fallback if no text segment was found
            if not text_to_speak.strip():
                text_to_speak = f"This is the section titled: {lesson['title']}"
            
            track_filename = f"{lesson_id}.mp3"
            track_path = os.path.join(audio_output_dir, track_filename)
            
            # Synthesize audio and get duration
            print(f"    -> Synthesizing track: {lesson['title']}...")
            duration = await synthesizer.synthesize_async(text_to_speak, track_path)
            
            # Update lesson details
            lesson["audio_file"] = f"/books/{book_slug}/audio/{track_filename}"
            lesson["duration_seconds"] = round(duration, 2)
            total_duration += duration
            completed_lessons += 1
            
            # Update incremental progress
            progress = int((completed_lessons / total_lessons) * 100)
            structured_book["progress"] = progress
            structured_book["total_duration_seconds"] = round(total_duration, 2)
            
            # Write updated metadata to disk immediately
            with open(metadata_json_path, "w") as f:
                json.dump(structured_book, f, indent=2)
            sys.stdout.flush()

    # Finalize metadata state
    structured_book["status"] = "completed"
    structured_book["progress"] = 100
    with open(metadata_json_path, "w") as f:
        json.dump(structured_book, f, indent=2)
        
    print(f"[+] Book metadata fully compiled and completed: {metadata_json_path}")
    print("[*] VoxBook pipeline completed successfully!")

def main():
    parser = argparse.ArgumentParser(description="VoxBook audiobook generator CLI pipeline")
    parser.add_argument("pdf_path", help="Path to input PDF book")
    parser.add_argument(
        "--output-dir", 
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "public", "books"),
        help="Target output directory for assets (default: frontend/public/books/)"
    )
    parser.add_argument(
        "--voice",
        default="en-US-EmmaMultilingualNeural",
        help="Voice identifier for edge-tts (default: en-US-EmmaMultilingualNeural)"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"Error: Input PDF not found at {args.pdf_path}")
        sys.exit(1)
        
    asyncio.run(process_book_pipeline(args.pdf_path, args.output_dir, args.voice))

if __name__ == "__main__":
    main()
