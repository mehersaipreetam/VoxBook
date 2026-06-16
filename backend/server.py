import os
import sys
import shutil
import json
import asyncio
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Adjust path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import process_book_pipeline, slugify

app = FastAPI(title="VoxBook API Server")

# Enable CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In local development, we allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "frontend", "public", "books")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def run_compilation_background(file_path: str):
    """Asynchronous background task to run the compilation pipeline."""
    try:
        # Default voice
        voice = "en-US-EmmaMultilingualNeural"
        await process_book_pipeline(file_path, OUTPUT_DIR, voice)
    except Exception as e:
        print(f"[!] Background compilation failed for {file_path}: {e}")
    finally:
        # Optionally clean up the uploaded PDF file to save space
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

@app.post("/api/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Receives a PDF book file and triggers the compilation pipeline in the background."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    # Save the file locally
    temp_file_path = os.path.join(INPUT_DIR, file.filename)
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")
    
    # Infer book ID from the filename as preliminary target slug
    filename_without_ext = os.path.splitext(file.filename)[0]
    # Clean up name to construct target slug
    book_slug = slugify(filename_without_ext)
    
    # Start the compilation pipeline in the background
    background_tasks.add_task(run_compilation_background, temp_file_path)
    
    return {
        "message": "Upload successful. Compilation started in the background.",
        "book_id": book_slug,
        "filename": file.filename
    }

@app.delete("/api/books/{book_id}")
async def delete_book(book_id: str):
    """Deletes a book directory permanently and removes it from the books manifest."""
    clean_book_id = slugify(book_id)
    if not clean_book_id:
        raise HTTPException(status_code=400, detail="Invalid book ID format.")
    
    book_folder = os.path.join(OUTPUT_DIR, clean_book_id)
    manifest_path = os.path.join(OUTPUT_DIR, "books.json")
    
    deleted_folder = False
    if os.path.exists(book_folder):
        try:
            shutil.rmtree(book_folder)
            deleted_folder = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete book files: {str(e)}")
            
    deleted_manifest_entry = False
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                books_manifest = json.load(f)
            
            initial_count = len(books_manifest)
            books_manifest = [b for b in books_manifest if b.get("id") != clean_book_id]
            
            if len(books_manifest) < initial_count:
                deleted_manifest_entry = True
                with open(manifest_path, "w") as f:
                    json.dump(books_manifest, f, indent=2)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update manifest: {str(e)}")

    if not deleted_folder and not deleted_manifest_entry:
        raise HTTPException(status_code=404, detail="Book not found.")
        
    return {
        "message": f"Book '{clean_book_id}' has been permanently deleted.",
        "book_id": clean_book_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
