import asyncio
import os
from typing import Optional
from pydub import AudioSegment
import edge_tts

class SpeechSynthesizer:
    """Synthesizes text into high-quality MP3 audio files using free/local engines."""

    def __init__(self, voice: str = "en-US-EmmaMultilingualNeural"):
        """Initializes the synthesizer.

        Args:
            voice: The voice string to use for synthesis.
        """
        self.voice = voice

    async def _synthesize_local_fallback(self, text: str, output_path: str) -> None:
        """Fallback to local offline pyttsx3 synthesis."""
        print("[*] edge-tts synthesis failed. Falling back to local offline TTS engine...")
        try:
            import pyttsx3
            # Initialize offline TTS engine inside a threadpool executor because it is synchronous/blocking
            def _run():
                engine = pyttsx3.init()
                engine.setProperty('rate', 150)
                engine.save_to_file(text, output_path)
                engine.runAndWait()
                engine.stop()
                
            await asyncio.get_event_loop().run_in_executor(None, _run)
        except Exception as e:
            raise RuntimeError(f"Offline local TTS fallback also failed: {e}")

    async def synthesize_async(self, text: str, output_path: str) -> float:
        """Asynchronously synthesizes text into an MP3 file and calculates its duration.

        Args:
            text: Text to synthesize.
            output_path: Path where MP3 will be saved.

        Returns:
            float: Duration of the synthesized audio in seconds.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Run edge-tts synthesis with local pyttsx3 fallback
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(output_path)
        except Exception as tts_err:
            print(f"[!] edge-tts failed: {tts_err}")
            try:
                await self._synthesize_local_fallback(text, output_path)
            except Exception as fallback_err:
                raise RuntimeError(
                    f"TTS Synthesis failed. Both edge-tts and local offline TTS engines failed.\n"
                    f"edge-tts error: {tts_err}\n"
                    f"Local fallback error: {fallback_err}"
                )

        # Get audio duration using pydub
        try:
            audio = AudioSegment.from_mp3(output_path)
            duration_seconds = len(audio) / 1000.0  # length in milliseconds / 1000
            return duration_seconds
        except Exception as e:
            print(f"Failed to read audio duration for {output_path}: {e}")
            return 0.0

    def synthesize(self, text: str, output_path: str) -> float:
        """Synchronous wrapper for the async synthesize method.

        Args:
            text: Text to synthesize.
            output_path: Output file path.

        Returns:
            float: Audio duration in seconds.
        """
        try:
            # Run the async loop to completion
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # If the loop is already running (e.g. inside another async context), 
            # we run it using a future or run_coroutine_threadsafe.
            # But in our pipeline CLI, we run sequentially.
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self.synthesize_async(text, output_path))
        else:
            return loop.run_until_complete(self.synthesize_async(text, output_path))

if __name__ == "__main__":
    # Test synthesis
    import sys
    test_text = "Welcome to VoxBook, your local and free AI-powered smart audiobook player."
    synth = SpeechSynthesizer()
    out = "test_synthesis.mp3"
    print(f"Synthesizing test audio to {out}...")
    duration = synth.synthesize(test_text, out)
    print(f"Synthesis complete! Duration: {duration} seconds.")
    if os.path.exists(out):
        os.remove(out)
