"""Frame store: saves incoming INDI image BLOBs to disk and tracks metadata.

Each captured frame is stored as a pair of files in the data directory:
  {frame_id}.fits   — the image data (decompressed if the driver sent .fits.z)
  {frame_id}.json   — metadata: device, run_id, timestamp, hash, size, format

The SHA-256 hash covers the bytes written to disk (after decompression).
Clients must supply the correct hash to delete a frame.
"""

import gzip
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameStore:
    def __init__(self, data_dir: str) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        device: str,
        data: bytes,
        blob_format: str,
        run_id: str | None = None,
        capture_params: dict | None = None,
    ) -> dict:
        """Save image data and return its metadata dict.

        If ``blob_format`` ends with ``.z``, the data is gzip-decompressed
        before storage and the stored format has the ``.z`` suffix stripped.

        Returns:
            Metadata dict with keys: frame_id, device, run_id, timestamp,
            hash, size, format.
        """
        # Decompress gzipped FITS (INDI cameras often compress on-the-fly)
        fmt = blob_format.lower()
        if fmt.endswith(".z"):
            try:
                data = gzip.decompress(data)
            except Exception:
                logger.warning("Failed to decompress BLOB for device %s; storing as-is", device)
            fmt = fmt[:-2]  # strip .z  →  .fits.z → .fits

        if not fmt:
            fmt = ".fits"

        frame_id = str(uuid.uuid4())
        hash_ = hashlib.sha256(data).hexdigest()
        size = len(data)
        timestamp = datetime.now(timezone.utc).isoformat()

        image_path = self._dir / (frame_id + fmt)
        meta_path  = self._dir / (frame_id + ".json")

        image_path.write_bytes(data)

        meta = {
            "frame_id":      frame_id,
            "device":        device,
            "run_id":        run_id,
            "timestamp":     timestamp,
            "hash":          hash_,
            "size":          size,
            "format":        fmt,
            "capture":       capture_params or {},
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info("Saved frame %s for %s (%d bytes, %s)", frame_id, device, size, fmt)
        return meta

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self) -> list[dict]:
        """Return metadata for all stored frames, newest first."""
        frames = []
        for p in self._dir.glob("*.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                frames.append(meta)
            except Exception:
                logger.warning("Failed to read frame metadata: %s", p)
        frames.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        return frames

    def get(self, frame_id: str) -> tuple[bytes, dict]:
        """Return (image bytes, metadata) for the given frame.

        Raises:
            FileNotFoundError: If no frame with that ID exists.
        """
        meta_path = self._dir / (frame_id + ".json")
        if not meta_path.exists():
            raise FileNotFoundError(f"Frame '{frame_id}' not found")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        image_path = self._dir / (frame_id + meta["format"])
        data = image_path.read_bytes()
        return data, meta

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, frame_id: str, hash_: str) -> None:
        """Delete a frame after verifying the supplied SHA-256 hash.

        The hash must match the stored hash to guard against accidental
        deletion before the client has actually verified the download.

        Raises:
            FileNotFoundError: If no frame with that ID exists.
            ValueError: If the supplied hash does not match.
        """
        meta_path = self._dir / (frame_id + ".json")
        if not meta_path.exists():
            raise FileNotFoundError(f"Frame '{frame_id}' not found")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["hash"] != hash_:
            raise ValueError(
                f"Hash mismatch for frame '{frame_id}': "
                f"expected {meta['hash'][:8]}…, got {hash_[:8]}…"
            )

        image_path = self._dir / (frame_id + meta["format"])
        if image_path.exists():
            image_path.unlink()
        meta_path.unlink()
        logger.info("Deleted frame %s (%s)", frame_id, meta["device"])
