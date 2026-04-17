"""Split large audio files into sub-25MB MP3 chunks via ffmpeg."""

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT_SECONDS = 600
CHUNK_SECONDS = 600  # 10 minutes per chunk
BITRATE = "64k"


class AudioSplitError(RuntimeError):
    """Raised when ffmpeg fails to split an audio file."""


async def split_audio(
    content: bytes,
    original_filename: str,
    chunk_seconds: int = CHUNK_SECONDS,
) -> list[bytes]:
    """Re-encode input audio to mp3 64k mono and split it into chunks.

    Args:
        content: Raw bytes of the input audio file.
        original_filename: Original filename (used only for a temp extension).
        chunk_seconds: Desired duration of each chunk in seconds.

    Returns:
        Ordered list of MP3 chunk bytes.

    Raises:
        AudioSplitError: If ffmpeg returns non-zero exit code or times out.
    """
    suffix = Path(original_filename).suffix or ".bin"

    with tempfile.TemporaryDirectory(prefix="media_split_") as tmpdir:
        tmp_path = Path(tmpdir)
        input_path = tmp_path / f"input{suffix}"
        input_path.write_bytes(content)

        output_pattern = str(tmp_path / "chunk_%03d.mp3")

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-acodec",
            "libmp3lame",
            "-ab",
            BITRATE,
            "-ac",
            "1",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            output_pattern,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=FFMPEG_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise AudioSplitError("ffmpeg timed out") from exc

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")
            logger.error("ffmpeg split failed: %s", err)
            raise AudioSplitError(f"ffmpeg exited with {proc.returncode}")

        chunk_paths = sorted(tmp_path.glob("chunk_*.mp3"))
        if not chunk_paths:
            raise AudioSplitError("ffmpeg produced no chunks")

        chunks = [p.read_bytes() for p in chunk_paths]
        logger.info(
            "Split %d bytes into %d chunks (%s each, ~%ds)",
            len(content),
            len(chunks),
            BITRATE,
            chunk_seconds,
        )
        return chunks
