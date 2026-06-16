import os
import fitz  # PyMuPDF
import re
from typing import List, Dict, Any

class PDFExtractor:
    """Extracts text from PDF files while filtering out headers and footers."""

    def __init__(self, filepath: str, margin_percentage: float = 0.12):
        """Initializes the extractor.

        Args:
            filepath: Absolute or relative path to the PDF file.
            margin_percentage: The vertical margin at the top and bottom of each page to ignore (0.12 = 12%).
        """
        self.filepath = filepath
        self.margin_percentage = margin_percentage
        self.doc = None

    def open(self) -> None:
        """Opens the PDF document."""
        try:
            self.doc = fitz.open(self.filepath)
        except Exception as e:
            raise FileNotFoundError(f"Failed to open PDF at {self.filepath}: {str(e)}")

    def close(self) -> None:
        """Closes the PDF document."""
        if self.doc:
            self.doc.close()

    def clean_text(self, text: str) -> str:
        """Cleans and normalizes extracted text, removing metadata line-by-line."""
        # Split block into lines to filter out page numbers, headers, and footers
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            trimmed = line.strip()
            # Skip empty lines
            if not trimmed:
                continue
            # Skip page numbers (e.g. "123", "[123]", "Page 123", "123 of 456")
            if re.match(r'^\[?\d+\]?$', trimmed):
                continue
            if re.match(r'^page\s+\d+(\s+of\s+\d+)?$', trimmed, re.IGNORECASE):
                continue
            if re.match(r'^\d+\s+of\s+\d+$', trimmed):
                continue
            # Skip URLs or email addresses
            if re.match(r'^https?://\S+$', trimmed) or re.match(r'^\S+@\S+\.\S+$', trimmed):
                continue
            # Skip copyright lines
            if re.search(r'copyright|all\s+rights\s+reserved', trimmed, re.IGNORECASE):
                continue
            cleaned_lines.append(trimmed)
            
        text = "\n".join(cleaned_lines)
        # Support both ASCII and Unicode hyphens/dashes (\u2010 = Hyphen, \u2011 = Non-breaking, \u00ad = Soft, \u2012-\u2014 = dashes)
        hyphens_pattern = r'[\-\u2010\u2011\u00ad\u2012\u2013\u2014]'
        
        # Join words split by line hyphenation (loosely matching spaces around hyphens and newlines)
        text = re.sub(r'(\w+)\s*' + hyphens_pattern + r'\s*\n\s*(\w+)', r'\1\2', text)
        text = re.sub(r'(\w+)\s*\n\s*' + hyphens_pattern + r'\s*(\w+)', r'\1\2', text)
        
        # Remove spaces around any remaining hyphens/dashes (e.g., "local - first" -> "local-first")
        text = re.sub(r'(\w+)\s*(' + hyphens_pattern + r')\s*(\w+)', r'\1\2\3', text)
        # Replace multiple spaces/newlines with single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_pages(self, start_page: int = 0, end_page: int = -1) -> List[Dict[str, Any]]:
        """Extracts text content page by page, ignoring top and bottom margins.

        Args:
            start_page: Page index to start (0-indexed).
            end_page: Page index to end (0-indexed), -1 for end of document.

        Returns:
            A list of dictionaries containing page number and text blocks.
        """
        if not self.doc:
            self.open()

        total_pages = len(self.doc)
        if end_page == -1 or end_page >= total_pages:
            end_page = total_pages - 1

        pages_data = []

        for page_idx in range(start_page, end_page + 1):
            page = self.doc[page_idx]
            rect = page.rect
            height = rect.height
            
            # Calculate header/footer boundaries
            top_boundary = height * self.margin_percentage
            bottom_boundary = height * (1 - self.margin_percentage)

            # Get text blocks with structural details (block type 0 is text)
            blocks = page.get_text("blocks")
            page_blocks = []

            for b in blocks:
                x0, y0, x1, y1, text, block_no, block_type = b
                
                # Check if block lies within the vertical text body area
                if y0 >= top_boundary and y1 <= bottom_boundary:
                    cleaned = self.clean_text(text)
                    if cleaned:
                        page_blocks.append({
                            "bbox": (x0, y0, x1, y1),
                            "text": cleaned,
                            "block_no": block_no
                        })

            raw_text = page.get_text("text")
            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

            pages_data.append({
                "page_number": page_idx + 1,
                "blocks": page_blocks,
                "full_text": " ".join([b["text"] for b in page_blocks]),
                "lines": lines
            })

        return pages_data

    def extract_page_images(self, page_number: int, output_dir: str, book_slug: str) -> List[str]:
        """Extracts all images on a given page and saves them to output_dir.

        Args:
            page_number: The 1-based page number.
            output_dir: Folder to save the extracted images.
            book_slug: Slug of the book (for constructing URLs).

        Returns:
            A list of relative image URLs.
        """
        if not self.doc:
            self.open()

        page_idx = page_number - 1
        if page_idx < 0 or page_idx >= len(self.doc):
            return []

        page = self.doc[page_idx]
        image_list = page.get_images(full=True)
        page_images = []

        if image_list:
            os.makedirs(output_dir, exist_ok=True)

        for img_idx, img_info in enumerate(image_list):
            try:
                xref = img_info[0]
                base_image = self.doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                # Name the image file page_{page_num}_{img_idx}.ext
                img_filename = f"page_{page_number}_{img_idx}.{image_ext}"
                img_path = os.path.join(output_dir, img_filename)
                
                with open(img_path, "wb") as f:
                    f.write(image_bytes)

                # Construct the relative asset URL
                img_url = f"/books/{book_slug}/images/{img_filename}"
                page_images.append(img_url)
            except Exception as e:
                print(f"[-] Failed to extract image on page {page_number}: {e}")

        return page_images

if __name__ == "__main__":
    # Quick debug/manual test code
    import sys
    if len(sys.argv) > 1:
        extractor = PDFExtractor(sys.argv[1])
        extractor.open()
        print(f"Total Pages: {len(extractor.doc)}")
        pages = extractor.extract_pages(start_page=0, end_page=2)
        for p in pages:
            print(f"\n--- PAGE {p['page_number']} ---")
            print(p["full_text"][:500] + "...")
        extractor.close()
