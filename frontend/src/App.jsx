import React, { useState, useEffect, useRef } from 'react';

function App() {
  const [books, setBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState(null);
  const [activeLesson, setActiveLesson] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(() => {
    const saved = localStorage.getItem('voxbook_speed');
    return saved !== null ? parseFloat(saved) : 1.0;
  });
  const [volume, setVolume] = useState(() => {
    const saved = localStorage.getItem('voxbook_volume');
    return saved !== null ? parseFloat(saved) : 0.8;
  });
  const [showLibrary, setShowLibrary] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [activeSentenceIndex, setActiveSentenceIndex] = useState(-1);
  const [expandedImage, setExpandedImage] = useState(null);
  const [transcriptWidth, setTranscriptWidth] = useState(320);
  const [isResizing, setIsResizing] = useState(false);
  const lightboxRef = useRef(null);

  const audioRef = useRef(null);
  if (audioRef.current === null) {
    const audio = new Audio();
    audio.volume = volume;
    audio.playbackRate = playbackSpeed;
    audioRef.current = audio;
  }

  // 2. Bind listeners dynamically to prevent stale closures while preserving the single Audio instance
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
      if (selectedBook && activeLesson) {
        savePlaybackState(selectedBook.book_id, activeLesson.lesson_id, audio.currentTime);
      }
    };

    const handleLoadedMetadata = () => {
      setDuration(audio.duration || 0);
    };

    const handleEnded = () => {
      playNextTrack();
    };

    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('ended', handleEnded);

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('ended', handleEnded);
    };
  }, [selectedBook, activeLesson]);

  // 2b. High-frequency smooth time updates for fast playback speeds (e.g. 1.5x, 2x)
  useEffect(() => {
    if (!isPlaying) return;

    let animFrameId;
    const updateSmoothTime = () => {
      if (audioRef.current) {
        setCurrentTime(audioRef.current.currentTime);
      }
      animFrameId = requestAnimationFrame(updateSmoothTime);
    };

    animFrameId = requestAnimationFrame(updateSmoothTime);
    return () => cancelAnimationFrame(animFrameId);
  }, [isPlaying]);

  // 3. Poll for metadata updates if the selected book is still processing
  useEffect(() => {
    if (!selectedBook || selectedBook.status !== 'processing') return;

    const pollInterval = setInterval(async () => {
      try {
        const metadataPath = `/books/${selectedBook.book_id}/metadata.json`;
        const res = await fetch(metadataPath);
        if (res.ok) {
          const freshMetadata = await res.json();
          
          setSelectedBook(prev => {
            if (!prev || prev.book_id !== freshMetadata.book_id) return prev;
            return freshMetadata;
          });

          // Sync active lesson with fresh metadata once duration is populated
          if (activeLesson) {
            const flatTracks = getFlatTracks(freshMetadata);
            const freshActiveTrack = flatTracks.find(t => t.lesson_id === activeLesson.lesson_id);
            if (freshActiveTrack && freshActiveTrack.duration_seconds > 0 && activeLesson.duration_seconds === 0) {
              setActiveLesson(freshActiveTrack);
              if (audioRef.current && (!audioRef.current.src || audioRef.current.src.endsWith('/'))) {
                audioRef.current.src = freshActiveTrack.audio_file;
                audioRef.current.load();
              }
            }
          }

          if (freshMetadata.status === 'completed') {
            clearInterval(pollInterval);
            fetchBooksManifest();
          }
        }
      } catch (e) {
        console.error('Failed to poll metadata:', e);
      }
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [selectedBook, activeLesson]);

  // Helper to split text into sentences
  const splitSentences = (text) => {
    if (!text) return [];
    // Split by sentence endings (. ! ?) followed by space or end of string
    const matches = text.match(/[^.!?]+[.!?]+(?=\s|$)/g);
    return matches || [text];
  };

  // Construct page-wise sentence blocks
  const pageBlocks = React.useMemo(() => {
    if (!activeLesson) return [];
    
    if (activeLesson.pages && activeLesson.pages.length > 0) {
      let cumulativeLength = 0;
      let globalIdx = 0;
      return activeLesson.pages.map((p) => {
        const pageSentences = splitSentences(p.text);
        const sentenceBlocks = pageSentences.map((sentence) => {
          const start = cumulativeLength;
          const end = cumulativeLength + sentence.length;
          cumulativeLength = end;
          return { text: sentence, start, end, index: globalIdx++ };
        });
        return {
          page_number: p.page_number,
          images: p.images || [],
          sentences: sentenceBlocks
        };
      });
    }
    return [];
  }, [activeLesson]);

  // Construct a flat list of sentences for matching activeIndex
  const sentenceBlocks = React.useMemo(() => {
    if (pageBlocks.length > 0) {
      const flat = [];
      pageBlocks.forEach((pb) => {
        pb.sentences.forEach((s) => {
          flat.push(s);
        });
      });
      return flat;
    }
    
    // Fallback for older books with only lesson.text
    const sentences = activeLesson?.text ? splitSentences(activeLesson.text) : [];
    let cumulativeLength = 0;
    return sentences.map((sentence, index) => {
      const start = cumulativeLength;
      const end = cumulativeLength + sentence.length;
      cumulativeLength = end;
      return { text: sentence, start, end, index };
    });
  }, [pageBlocks, activeLesson]);

  // Determine active sentence index based on playback progress
  useEffect(() => {
    if (!activeLesson?.text || sentenceBlocks.length === 0 || duration === 0) {
      setActiveSentenceIndex(-1);
      return;
    }

    const L = activeLesson.text.length;
    const progress = currentTime / duration;
    const targetCharIndex = L * progress;

    let activeIdx = -1;
    for (let i = 0; i < sentenceBlocks.length; i++) {
      const s = sentenceBlocks[i];
      if (targetCharIndex >= s.start && targetCharIndex <= s.end) {
        activeIdx = i;
        break;
      }
    }

    if (activeIdx !== -1 && activeIdx !== activeSentenceIndex) {
      setActiveSentenceIndex(activeIdx);
      
      // Auto-scroll the active sentence into view inside the transcript sidebar
      const activeEl = document.querySelector('.transcript-sentence.active');
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentTime, duration, sentenceBlocks, activeLesson?.text, activeSentenceIndex]);

  const handleSentenceClick = (sentence) => {
    if (!audioRef.current || !duration || !activeLesson?.text) return;
    const L = activeLesson.text.length;
    const seekTime = (sentence.start / L) * duration;
    audioRef.current.currentTime = seekTime;
    setCurrentTime(seekTime);
  };

  const handleResizeMouseDown = (e) => {
    e.preventDefault();
    setIsResizing(true);
  };

  // Drag resizing effect to ensure clean event listener registration and removal
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e) => {
      const minWidth = 240;
      const maxWidth = window.innerWidth * 0.6; // Max 60% of viewport
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= minWidth && newWidth <= maxWidth) {
        setTranscriptWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  // Synchronize dialog open/close states
  useEffect(() => {
    const dialog = lightboxRef.current;
    if (!dialog) return;

    if (expandedImage) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else {
      if (dialog.open) {
        dialog.close();
      }
    }
  }, [expandedImage]);

  // Handle dialog events and compatibility fallbacks
  useEffect(() => {
    const dialog = lightboxRef.current;
    if (!dialog) return;

    const handleClose = () => {
      setExpandedImage(null);
    };

    dialog.addEventListener('close', handleClose);

    // Light-dismiss click outside content fallback for older/Safari browsers
    let handleFallbackClick;
    if (!('closedBy' in HTMLDialogElement.prototype)) {
      handleFallbackClick = (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent = (
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width
        );
        if (isDialogContent) return;
        dialog.close();
      };
      dialog.addEventListener('click', handleFallbackClick);
    }

    return () => {
      dialog.removeEventListener('close', handleClose);
      if (handleFallbackClick) {
        dialog.removeEventListener('click', handleFallbackClick);
      }
    };
  }, []);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      alert("Only PDF files are supported!");
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        alert("Upload successful! Compilation started. The book will appear in your Library immediately.");
        
        // Refresh manifest so the processing book appears in the library overlay
        await fetchBooksManifest();
        
        // Auto-load the processing book metadata
        const metadataPath = `/books/${data.book_id}/metadata.json`;
        setTimeout(() => {
          loadBook(metadataPath);
        }, 1500);
      } else {
        const errData = await res.json();
        alert(`Upload failed: ${errData.detail || 'Server error'}`);
      }
    } catch (err) {
      console.error("Upload failed:", err);
      alert("Upload failed. Make sure the local backend server (port 8000) is running.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteBook = async (bookId) => {
    if (!window.confirm("Are you sure you want to permanently delete this book and all its audio files?")) {
      return;
    }

    try {
      const res = await fetch(`/api/books/${bookId}`, {
        method: 'DELETE'
      });

      if (res.ok) {
        // Clear cached playback state if it matches the deleted book
        const cached = localStorage.getItem('voxbook_playback_state');
        if (cached) {
          const { bookId: cachedId } = JSON.parse(cached);
          if (cachedId === bookId) {
            localStorage.removeItem('voxbook_playback_state');
          }
        }

        // If the deleted book is currently selected/playing, reset the player state
        let wasActive = false;
        if (selectedBook && selectedBook.book_id === bookId) {
          wasActive = true;
          if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.src = "";
          }
          setIsPlaying(false);
          setSelectedBook(null);
          setActiveLesson(null);
          setCurrentTime(0);
          setDuration(0);
        }

        // Update books list in UI
        const manifestRes = await fetch('/books/books.json');
        if (manifestRes.ok) {
          const data = await manifestRes.json();
          setBooks(data);
          
          // If we deleted the active book and there are other books, load the first one
          if (wasActive && data.length > 0) {
            loadBook(data[0].path);
          }
        } else {
          setBooks([]);
        }
      } else {
        const errData = await res.json();
        alert(`Failed to delete book: ${errData.detail || 'Server error'}`);
      }
    } catch (err) {
      console.error("Delete failed:", err);
      alert("Failed to delete book. Make sure the local backend server is running.");
    }
  };

  // Load Library books on mount
  useEffect(() => {
    fetchBooksManifest(true);
  }, []);

  const fetchBooksManifest = async (shouldAutoLoad = false) => {
    try {
      const res = await fetch('/books/books.json');
      if (res.ok) {
        const data = await res.json();
        setBooks(data);
        
        // Auto-load last read book if cached
        if (shouldAutoLoad || !selectedBook) {
          const cached = localStorage.getItem('voxbook_playback_state');
          if (cached) {
            const { bookId, lessonId, position } = JSON.parse(cached);
            const matchedBook = data.find(b => b.id === bookId);
            if (matchedBook) {
              loadBook(matchedBook.path, lessonId, position);
            } else if (data.length > 0) {
              loadBook(data[0].path);
            }
          } else if (data.length > 0) {
            loadBook(data[0].path);
          }
        }
      } else {
        console.warn('books.json manifest not found. Playing demo mode.');
      }
    } catch (e) {
      console.error('Error fetching manifest:', e);
    }
  };

  const loadBook = async (metadataPath, startLessonId = null, startPosition = 0) => {
    setIsLoading(true);
    try {
      const res = await fetch(metadataPath);
      if (res.ok) {
        const metadata = await res.json();
        setSelectedBook(metadata);
        
        // Find default active track
        let defaultTrack = null;
        if (metadata.chapters && metadata.chapters.length > 0) {
          // Flatten tracks
          const flatTracks = getFlatTracks(metadata);
          if (startLessonId) {
            defaultTrack = flatTracks.find(t => t.lesson_id === startLessonId);
          }
          if (!defaultTrack && flatTracks.length > 0) {
            // Find first playable track or fall back to the first track
            defaultTrack = flatTracks.find(t => t.duration_seconds > 0) || flatTracks[0];
          }
        }
        
        if (defaultTrack) {
          setActiveLesson(defaultTrack);
          if (audioRef.current) {
            audioRef.current.src = defaultTrack.audio_file || "";
            if (defaultTrack.audio_file) {
              audioRef.current.load();
              if (startPosition > 0) {
                audioRef.current.currentTime = startPosition;
                setCurrentTime(startPosition);
              }
            } else {
              setCurrentTime(0);
              setDuration(0);
            }
          }
        }
        setShowLibrary(false);
      }
    } catch (e) {
      console.error('Failed to load book metadata:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const getFlatTracks = (bookMetadata) => {
    if (!bookMetadata) return [];
    const tracks = [];
    bookMetadata.chapters.forEach(ch => {
      ch.lessons.forEach(l => {
        tracks.push(l);
      });
    });
    return tracks;
  };

  const savePlaybackState = (bookId, lessonId, position) => {
    localStorage.setItem('voxbook_playback_state', JSON.stringify({
      bookId,
      lessonId,
      position
    }));
  };

  const selectTrack = (lesson) => {
    if (!lesson.audio_file || lesson.duration_seconds === 0) return;
    
    setActiveLesson(lesson);
    if (audioRef.current) {
      audioRef.current.src = lesson.audio_file;
      audioRef.current.load();
      audioRef.current.currentTime = 0;
      setCurrentTime(0);
      audioRef.current.playbackRate = playbackSpeed;
      if (isPlaying) {
        audioRef.current.play().catch(e => console.log("Play failed: ", e));
      }
    }
  };

  const togglePlayPause = () => {
    if (!audioRef.current || !activeLesson) return;
    
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play()
        .then(() => setIsPlaying(true))
        .catch(err => console.error("Playback error:", err));
    }
  };

  const skipTime = (amount) => {
    if (!audioRef.current) return;
    let newTime = audioRef.current.currentTime + amount;
    if (newTime < 0) newTime = 0;
    if (newTime > duration) newTime = duration;
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const handleScrub = (e) => {
    if (!audioRef.current) return;
    const seekVal = parseFloat(e.target.value);
    audioRef.current.currentTime = seekVal;
    setCurrentTime(seekVal);
  };

  const handleSpeedChange = (e) => {
    const spd = parseFloat(e.target.value);
    setPlaybackSpeed(spd);
    localStorage.setItem('voxbook_speed', spd);
    if (audioRef.current) {
      audioRef.current.playbackRate = spd;
    }
  };

  const handleVolumeChange = (e) => {
    const vol = parseFloat(e.target.value);
    setVolume(vol);
    localStorage.setItem('voxbook_volume', vol);
    if (audioRef.current) {
      audioRef.current.volume = vol;
    }
  };

  const playNextTrack = () => {
    if (!selectedBook || !activeLesson) return;
    const flatTracks = getFlatTracks(selectedBook);
    const currIdx = flatTracks.findIndex(t => t.lesson_id === activeLesson.lesson_id);
    if (currIdx !== -1 && currIdx < flatTracks.length - 1) {
      selectTrack(flatTracks[currIdx + 1]);
    } else {
      setIsPlaying(false);
    }
  };

  const playPrevTrack = () => {
    if (!selectedBook || !activeLesson) return;
    const flatTracks = getFlatTracks(selectedBook);
    const currIdx = flatTracks.findIndex(t => t.lesson_id === activeLesson.lesson_id);
    if (currIdx > 0) {
      selectTrack(flatTracks[currIdx - 1]);
    }
  };

  const formatTime = (secs) => {
    if (isNaN(secs)) return '0:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <div className="app-container">
      {/* Sidebar Table of Contents */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">V</div>
            <span>VoxBook</span>
          </div>
        </div>
        
        <div className="toc-container">
          {selectedBook ? (
            selectedBook.chapters.map((chapter) => (
              <div key={chapter.chapter_number} className="chapter-group">
                <h4 className="chapter-title">{chapter.chapter_title}</h4>
                <ul className="lesson-list">
                  {chapter.lessons.map((lesson) => {
                    const isPlayable = lesson.audio_file && lesson.duration_seconds > 0;
                    return (
                      <li key={lesson.lesson_id}>
                        <button
                          onClick={() => isPlayable && selectTrack(lesson)}
                          className={`lesson-item ${activeLesson?.lesson_id === lesson.lesson_id ? 'active' : ''} ${!isPlayable ? 'disabled' : ''}`}
                          style={{
                            opacity: isPlayable ? 1 : 0.5,
                            cursor: isPlayable ? 'pointer' : 'not-allowed'
                          }}
                          disabled={!isPlayable}
                        >
                          <span>{lesson.title}</span>
                          <span className="lesson-duration">
                            {isPlayable ? formatTime(lesson.duration_seconds) : '🕒 Processing...'}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: '14px', padding: '20px', textAlign: 'center' }}>
              No book loaded
            </div>
          )}
        </div>
      </aside>

      {/* Main player area */}
      <main className="main-content">
        <header className="header">
          <div className="header-title">
            {selectedBook ? `${selectedBook.book_title}` : 'VoxBook Player'}
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button className={`library-btn ${showTranscript ? 'active' : ''}`} onClick={() => setShowTranscript(!showTranscript)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              Transcript
            </button>
            <button className="library-btn" onClick={() => setShowLibrary(true)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              Library
            </button>
          </div>
        </header>

        {selectedBook && activeLesson ? (
          <div className="player-container">
            {/* Real-time Compilation Progress Bar */}
            {selectedBook.status === 'processing' && (
              <div className="glass-panel" style={{ width: '100%', padding: '16px', marginBottom: '24px', border: '1px solid var(--border-focus)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                  <span style={{ color: 'var(--accent-primary)', fontWeight: '600' }}>⚡ Compiling Audiobook...</span>
                  <span>{selectedBook.progress}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', background: 'var(--bg-hover)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ width: `${selectedBook.progress}%`, height: '100%', background: 'var(--accent-gradient)', transition: 'width 0.5s ease' }}></div>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  Early tracks are playable in the sidebar immediately. Later tracks will activate as they finish.
                </div>
              </div>
            )}

            {/* Book Cover */}
            <div className="cover-wrapper glass-panel">
              <div className="cover-art">
                <span className="cover-art-icon">📖</span>
                <div className="book-title-fallback">{selectedBook.book_title}</div>
                <div className="book-author-fallback">{selectedBook.author}</div>
              </div>
            </div>

            {/* Track Info */}
            <div className="track-info">
              <h2 className="track-title">{activeLesson.title}</h2>
              <p className="track-author">{selectedBook.author}</p>
            </div>

            {/* Progress / Seek bar */}
            <div className="progress-container">
              <input
                type="range"
                className="scrub-bar"
                min="0"
                max={duration || 100}
                value={currentTime}
                onChange={handleScrub}
              />
              <div className="time-row">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>
            </div>

            {/* Main Playback Controls */}
            <div className="controls-container">
              <button className="control-btn" onClick={playPrevTrack} title="Previous Section">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="19 20 9 12 19 4 19 20"></polygon>
                  <line x1="5" y1="4" x2="5" y2="20"></line>
                </svg>
              </button>
              
              <button className="control-btn" onClick={() => skipTime(-15)} title="Rewind 15s">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
                  <polyline points="3 3 3 8 8 8"></polyline>
                  <text x="7" y="15" fontSize="8" fontWeight="bold" fill="currentColor" strokeWidth="0">15</text>
                </svg>
              </button>

              <button className="control-btn play-pause-btn" onClick={togglePlayPause}>
                {isPlaying ? (
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="6" y="4" width="4" height="16"></rect>
                    <rect x="14" y="4" width="4" height="16"></rect>
                  </svg>
                ) : (
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                  </svg>
                )}
              </button>

              <button className="control-btn" onClick={() => skipTime(15)} title="Forward 15s">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
                  <polyline points="21 3 21 8 16 8"></polyline>
                  <text x="9" y="15" fontSize="8" fontWeight="bold" fill="currentColor" strokeWidth="0">15</text>
                </svg>
              </button>

              <button className="control-btn" onClick={playNextTrack} title="Next Section">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="5 4 15 12 5 20 5 4"></polygon>
                  <line x1="19" y1="4" x2="19" y2="20"></line>
                </svg>
              </button>
            </div>

            {/* Speed & Volume control */}
            <div className="secondary-controls glass-panel">
              <div>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginRight: '8px' }}>Speed:</label>
                <select className="speed-select" value={playbackSpeed} onChange={handleSpeedChange}>
                  <option value="0.5">0.5x</option>
                  <option value="0.75">0.75x</option>
                  <option value="1">1.0x (Normal)</option>
                  <option value="1.25">1.25x</option>
                  <option value="1.5">1.5x</option>
                  <option value="1.75">1.75x</option>
                  <option value="2">2.0x</option>
                  <option value="2.5">2.5x</option>
                  <option value="3">3.0x</option>
                </select>
              </div>

              <div className="volume-container">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                  <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                </svg>
                <input
                  type="range"
                  className="volume-slider"
                  min="0"
                  max="1"
                  step="0.01"
                  value={volume}
                  onChange={handleVolumeChange}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">📚</div>
            <h1 className="empty-state-title">Welcome to VoxBook</h1>
            <p className="empty-state-text">
              Generate an audiobook by running the Python preprocessing pipeline on your computer. Place your PDF in the workspace and run the compiler:
            </p>
            <div className="empty-state-code">
              uv run backend/main.py path/to/your/book.pdf
            </div>
          </div>
        )}
      </main>

      {/* Library Selection Overlay */}
      {showLibrary && (
        <div className="library-overlay">
          <div className="library-header">
            <h2>Your Local Library</h2>
            <button className="library-btn" onClick={() => setShowLibrary(false)}>
              Close
            </button>
          </div>
          
          {/* Upload PDF Section */}
          <div className="glass-panel" style={{ padding: '24px', marginBottom: '32px', textAlign: 'center', width: '100%', maxWidth: '1000px', margin: '0 auto 32px auto' }}>
            <h3 style={{ marginBottom: '8px' }}>Compile a New PDF Book</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Upload a local PDF book. The pipeline will automatically parse chapters, synthesize audio, and register it to your library.
            </p>
            <label className="library-btn" style={{ display: 'inline-flex', cursor: isUploading ? 'not-allowed' : 'pointer', margin: '0 auto' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '8px' }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              {isUploading ? 'Uploading & Processing...' : 'Select PDF File'}
              <input type="file" accept=".pdf" onChange={handleFileUpload} style={{ display: 'none' }} disabled={isUploading} />
            </label>
          </div>

          {books.length > 0 ? (
            <div className="library-grid">
              {books.map((book) => (
                <div
                  key={book.id}
                  className="book-card"
                  onClick={() => loadBook(book.path)}
                >
                  <button
                    className="delete-book-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteBook(book.id);
                    }}
                    title="Delete Permanently"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      <line x1="10" y1="11" x2="10" y2="17"></line>
                      <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                  </button>
                  <div className="book-card-cover">
                    <span style={{ fontSize: '32px' }}>📖</span>
                  </div>
                  <div className="book-card-title">{book.title}</div>
                  <div className="book-card-author">{book.author}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', marginTop: '60px', color: 'var(--text-secondary)' }}>
              <p>No audiobooks have been compiled yet.</p>
              <p style={{ marginTop: '12px', fontSize: '14px' }}>
                Run the backend pipeline to generate your first audiobook.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Transcript Sidebar */}
      {showTranscript && (
        <aside className="transcript-sidebar" style={{ width: `${transcriptWidth}px` }}>
          {/* Resize Handle */}
          <div className="resize-handle" onMouseDown={handleResizeMouseDown}></div>
          <div className="sidebar-header">
            <h3>Transcript</h3>
            <button className="library-btn" style={{ padding: '6px' }} onClick={() => setShowTranscript(false)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
          <div className="transcript-content">
            {activeLesson && (activeLesson.pages || activeLesson.text) ? (
              pageBlocks.length > 0 ? (
                pageBlocks.map((pb) => (
                  <div key={pb.page_number} className="transcript-page-group">
                    <div className="transcript-page-divider">
                      <span>Page {pb.page_number}</span>
                    </div>
                    <div className="transcript-page-sentences">
                      {pb.sentences.map((s) => (
                        <span
                          key={s.index}
                          className={`transcript-sentence ${s.index === activeSentenceIndex ? 'active' : ''}`}
                          onClick={() => handleSentenceClick(s)}
                        >
                          {s.text}
                        </span>
                      ))}
                    </div>
                    {pb.images && pb.images.map((imgUrl, imgIdx) => (
                      <div key={imgIdx} className="transcript-figure glass-panel clickable" onClick={() => setExpandedImage(imgUrl)}>
                        <img src={imgUrl} alt={`Page ${pb.page_number} Figure ${imgIdx}`} />
                        <div className="figure-caption">Figure on Page {pb.page_number} (Click to expand)</div>
                      </div>
                    ))}
                  </div>
                ))
              ) : (
                // Fallback for older books
                sentenceBlocks.map((s) => (
                  <span
                    key={s.index}
                    className={`transcript-sentence ${s.index === activeSentenceIndex ? 'active' : ''}`}
                    onClick={() => handleSentenceClick(s)}
                  >
                    {s.text}
                  </span>
                ))
              )
            ) : (
              <div className="transcript-empty">
                {activeLesson ? "No transcript available. Re-compile this book to generate transcripts." : "Select a track to start listening."}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* Lightbox / Expanded Image Modal */}
      <dialog
        ref={lightboxRef}
        closedby="any"
        className="lightbox-dialog"
        aria-label="Expanded Image View"
      >
        <button className="lightbox-close-btn" onClick={() => setExpandedImage(null)}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <div className="lightbox-container">
          {expandedImage && <img src={expandedImage} alt="Expanded Figure" />}
        </div>
      </dialog>
    </div>
  );
}

export default App;
