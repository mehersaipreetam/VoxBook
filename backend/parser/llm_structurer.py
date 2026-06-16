import re
import json
from typing import List, Dict, Any, Optional
import ollama

class LLMStructurer:
    """Structures raw book text into chapters and lessons using local LLM, Table of Contents, or regex fallbacks."""

    def __init__(self, model_name: str = "llama3.2"):
        """Initializes the structurer.

        Args:
            model_name: The local Ollama model to use.
        """
        self.model_name = model_name

    def check_ollama_running(self) -> bool:
        """Checks if the local Ollama API server is running and accessible.

        Returns:
            bool: True if Ollama is reachable, False otherwise.
        """
        try:
            ollama.list()
            return True
        except Exception:
            return False

    def structure_with_ollama(self, pages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Invokes a local Ollama model to parse book text into chapters and lessons.

        Args:
            pages: List of dictionaries containing page numbers and text blocks.

        Returns:
            A structured book dictionary, or None if Ollama execution fails.
        """
        if not self.check_ollama_running():
            return None

        # Extract first few pages for TOC analysis
        toc_text = ""
        for p in pages[:min(12, len(pages))]:
            toc_text += f"\n--- Page {p['page_number']} ---\n"
            for b in p["blocks"]:
                toc_text += b["text"] + "\n"

        prompt = f"""
Analyze the following book text (typically the beginning pages or Table of Contents) and generate a JSON mapping of chapters and lessons.
Format your response as a valid JSON object ONLY. Do not wrap in markdown code blocks, do not explain.

Expected JSON format:
{{
  "book_title": "Title of the Book",
  "author": "Author Name (or Unknown)",
  "chapters": [
    {{
      "chapter_number": 1,
      "chapter_title": "Chapter Title",
      "lessons": [
        {{
          "lesson_id": "ch1_l1",
          "title": "Lesson Title"
        }}
      ]
    }}
  ]
}}

Book text to analyze:
{toc_text}
"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={"temperature": 0.1}
            )
            response_text = response['response'].strip()
            
            # Strip markdown formatting
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n', '', response_text)
                response_text = re.sub(r'\n```$', '', response_text)
            
            return json.loads(response_text)
        except Exception as e:
            print(f"Ollama generation failed: {e}. Trying Table of Contents parser.")
            return None

    def parse_toc_from_pages(self, pages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Scans the first 15 pages for a Table of Contents and builds page-indexed tracks.
        Handles line-spanning title/page listings gracefully.

        Args:
            pages: List of page objects.

        Returns:
            Structured book dictionary or None if no ToC is found.
        """
        toc_items = []
        toc_page_regex = re.compile(r'\b(contents|table\s+of\s+contents|index)\b', re.IGNORECASE)
        only_dots_regex = re.compile(r'^[\.\s\-\_]+$')
        
        toc_page_found = False
        
        for page in pages[:15]:
            lines = page.get("lines", [])
            page_text = " ".join(lines).lower()
            
            if toc_page_regex.search(page_text):
                # We found a potential TOC page! Let's extract items
                for i in range(len(lines)):
                    line = lines[i].strip()
                    
                    # Look for lines that contain just a page number
                    if line.isdigit():
                        page_num = int(line)
                        
                        # Look backward for the corresponding title
                        if i >= 1:
                            prev_line = lines[i-1].strip()
                            # If the previous line is just dot leaders, look back one more step
                            if only_dots_regex.match(prev_line) and i >= 2:
                                title = lines[i-2].strip()
                            else:
                                title = prev_line
                                
                            # Clean up title (remove trailing dots, numbers, dashes, and spaces)
                            title = re.sub(r'[\.\s\-\_]+$', '', title).strip()
                            
                            # Filter out common page headers and digit entries
                            if title and len(title) > 3 and not title.isdigit() and not title.lower() in ["contents", "table of contents", "index"]:
                                toc_items.append((title, page_num))
                                toc_page_found = True
        
        if not toc_page_found or not toc_items:
            return None
            
        # Sort items by page number
        toc_items.sort(key=lambda x: x[1])
        
        # Build chapter & lesson mapping
        chapters = []
        current_chapter = {
            "chapter_number": 1,
            "chapter_title": "Table of Contents",
            "lessons": []
        }
        chapters.append(current_chapter)
        
        total_pages = len(pages)
        
        # De-duplicate adjacent items with the same page number (e.g. subheadings)
        unique_toc_items = []
        seen_pages = set()
        for title, start_page in toc_items:
            if start_page not in seen_pages:
                unique_toc_items.append((title, start_page))
                seen_pages.add(start_page)
                
        # Try to detect the offset between printed page numbers and PDF page numbers
        offset = 0
        for title, printed_page in unique_toc_items[:min(5, len(unique_toc_items))]:
            clean_title = re.sub(r'[^a-z0-9]', '', title.lower())
            if len(clean_title) < 4:
                continue
                
            found_pdf_page = -1
            for p_idx, page in enumerate(pages):
                # Skip the first few pages containing the TOC itself to prevent false matching inside the TOC
                if p_idx < 2:
                    continue
                # Check text blocks
                for b in page.get("blocks", []):
                    block_text = re.sub(r'[^a-z0-9]', '', b["text"].lower())
                    if block_text.startswith(clean_title) and len(b["text"].strip()) < 100:
                        found_pdf_page = page["page_number"]
                        break
                if found_pdf_page != -1:
                    break
            
            if found_pdf_page != -1:
                offset = found_pdf_page - printed_page
                print(f"[TOC Parser] Detected page offset for '{title}': {offset} (PDF page {found_pdf_page} vs printed page {printed_page})")
                break

        # Adjust start_page and end_page for each item using the detected offset
        adjusted_toc_items = []
        for title, printed_page in unique_toc_items:
            adjusted_page = max(1, printed_page + offset)
            adjusted_toc_items.append((title, adjusted_page))
            
        for idx, (title, start_page) in enumerate(adjusted_toc_items):
            if idx < len(adjusted_toc_items) - 1:
                end_page = adjusted_toc_items[idx+1][1] - 1
            else:
                end_page = total_pages
                
            # Boundary checks
            if start_page > total_pages:
                continue
            if end_page > total_pages:
                end_page = total_pages
            if start_page > end_page:
                end_page = start_page
                
            lesson_id = f"ch1_l{idx + 1}"
            current_chapter["lessons"].append({
                "lesson_id": lesson_id,
                "title": title,
                "start_page": start_page,
                "end_page": end_page
            })
            
        # Try to infer title from the first block
        book_title = "Untitled Book"
        if pages and pages[0]["blocks"]:
            book_title = pages[0]["blocks"][0]["text"]
            if len(book_title) > 60:
                book_title = book_title[:60] + "..."
                
        return {
            "book_title": book_title,
            "author": "Local Compiler",
            "chapters": chapters
        }

    def structure_with_rules(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """A robust heading parser using strict regex matching for numbered chapters.

        Args:
            pages: List of page objects.

        Returns:
            Structured book dictionary.
        """
        chapters = []
        current_chapter = None
        lesson_counter = 1

        # Strict patterns (must contain numbers to prevent random sentence matches)
        chapter_regex = re.compile(
            r'^(?:Chapter|Section|Part)\s+(\d+|[IVXLCDM]+)\b[:.]?\s*(.*)$', 
            re.IGNORECASE
        )
        lesson_regex = re.compile(
            r'^(\d+\.\d+)\s+(.*)$'
        )

        for p in pages:
            for b in p["blocks"]:
                text = b["text"].strip()
                
                # Check for Chapter marker (must be a relatively short line)
                chap_match = chapter_regex.match(text)
                if chap_match and len(text) < 100:
                    chap_num_str = chap_match.group(1)
                    chap_title = chap_match.group(2).strip() or f"Chapter {chap_num_str}"
                    
                    current_chapter = {
                        "chapter_number": len(chapters) + 1,
                        "chapter_title": f"Chapter {chap_num_str}: {chap_title}",
                        "lessons": []
                    }
                    chapters.append(current_chapter)
                    continue

                # Check for Lesson/Subsection marker
                less_match = lesson_regex.match(text)
                if less_match:
                    less_num = less_match.group(1)
                    less_title = less_match.group(2).strip()
                    
                    if not current_chapter:
                        current_chapter = {
                            "chapter_number": 1,
                            "chapter_title": "Chapter 1: Introduction",
                            "lessons": []
                        }
                        chapters.append(current_chapter)

                    current_chapter["lessons"].append({
                        "lesson_id": f"ch{current_chapter['chapter_number']}_l{lesson_counter}",
                        "title": f"{less_num} {less_title}",
                        "start_page": p["page_number"],
                        "end_page": p["page_number"]
                    })
                    lesson_counter += 1
                    continue

        return {
            "book_title": pages[0]["blocks"][0]["text"] if pages and pages[0]["blocks"] else "Untitled Book",
            "author": "Local Compiler",
            "chapters": chapters
        }

    def chunk_pages_fallback(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ultimate fallback: chunks the document pages evenly into audio segments.

        Args:
            pages: List of page objects.

        Returns:
            Structured book dictionary.
        """
        print("[!] Falling back to even page chunking (5 pages per track)...")
        chapters = []
        current_chapter = {
            "chapter_number": 1,
            "chapter_title": "Book Contents",
            "lessons": []
        }
        chapters.append(current_chapter)
        
        chunk_size = 5
        total_pages = len(pages)
        
        for idx in range(0, total_pages, chunk_size):
            start = idx + 1
            end = min(idx + chunk_size, total_pages)
            lesson_id = f"ch1_l{len(current_chapter['lessons']) + 1}"
            
            # Extract first 50 chars of the first page in the chunk as a descriptive label
            first_page_text = pages[idx]["full_text"].strip()
            label_match = re.match(r'^([A-Z][A-Za-z0-9\s\,\'\-\"]{15,40})', first_page_text)
            label = label_match.group(1).strip() if label_match else f"Section {len(current_chapter['lessons']) + 1}"
            
            current_chapter["lessons"].append({
                "lesson_id": lesson_id,
                "title": f"{label} (Pages {start}-{end})",
                "start_page": start,
                "end_page": end
            })
            
        # Try to infer title
        book_title = "Untitled Book"
        if pages and pages[0]["blocks"]:
            book_title = pages[0]["blocks"][0]["text"]
            if len(book_title) > 60:
                book_title = book_title[:60] + "..."
                
        return {
            "book_title": book_title,
            "author": "Local Compiler",
            "chapters": chapters
        }

    def _validate_structure(self, struct: Dict[str, Any]) -> bool:
        """Validates that the structured result has chapters and at least one lesson."""
        if not struct or "chapters" not in struct or not struct["chapters"]:
            return False
        
        total_lessons = 0
        for ch in struct["chapters"]:
            total_lessons += len(ch.get("lessons", []))
            
        return total_lessons > 0

    def structure_book(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Tries to structure the book using LLM, then Table of Contents, then regex headings, then chunk fallback."""
        # 1. Try Ollama first
        result = self.structure_with_ollama(pages)
        if result and self._validate_structure(result):
            print("[+] Structure generated successfully via Ollama LLM.")
            return result
        
        # 2. Try Table of Contents parsing (excellent for standard PDFs with a Contents page)
        result = self.parse_toc_from_pages(pages)
        if result and self._validate_structure(result):
            print("[+] Table of Contents page detected and parsed successfully.")
            return result
            
        # 3. Try strict regex heading parser
        result = self.structure_with_rules(pages)
        if result and self._validate_structure(result):
            print("[+] Document structure extracted via heading regex matches.")
            return result
            
        # 4. Fallback: chunk pages
        return self.chunk_pages_fallback(pages)

if __name__ == "__main__":
    # Test rules structure
    mock_pages = [
        {
            "page_number": 1,
            "lines": ["Contents", "Introduction", ". . . . . . .", "1", "Installation", ". . . . . . .", "2"],
            "blocks": [{"text": "Python for Beginners"}]
        },
        {
            "page_number": 2,
            "lines": ["Chapter 2 Variables", "2.1 Strings", "2.2 Numbers"],
            "blocks": [{"text": "Chapter 2 Variables"}]
        }
    ]
    structurer = LLMStructurer()
    res = structurer.structure_book(mock_pages)
    print(json.dumps(res, indent=2))
