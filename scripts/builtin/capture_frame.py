"""Capture one or more frames with a CCD camera.

Supports light, dark, flat, bias, and dark-flat frame types.
Applies binning, gain, offset, sub-frame, filter, and cooler
settings before exposing. Optionally embeds target and image-train
metadata for FITS headers and later plate-solving.
"""

# ── Core ────────────────────────────────────────────────────────────────────
device   = params.get("device",   "CCD Simulator")
count    = params.get("count",    1)
exposure = params.get("exposure", 10.0)
delay    = params.get("delay",    0.0)

# ── Frame ────────────────────────────────────────────────────────────────────
frame_type  = params.get("frame_type", "light")   # light|dark|flat|bias|dark_flat
gain        = params.get("gain",   None)
offset      = params.get("offset", None)
bin_x       = params.get("bin_x",  1)
bin_y       = params.get("bin_y",  1)

# Sub-frame (None = full sensor)
frame_x = params.get("frame_x", None)
frame_y = params.get("frame_y", None)
frame_w = params.get("frame_w", None)
frame_h = params.get("frame_h", None)

# ── Format ──────────────────────────────────────────────────────────────────
format_ = params.get("format", None)    # e.g. "FITS", "NATIVE" — driver-dependent

# ── Filter ──────────────────────────────────────────────────────────────────
filter_device = params.get("filter_device", None)
filter_name   = params.get("filter_name",   None)

# ── Cooler ──────────────────────────────────────────────────────────────────
cooler_temp = params.get("cooler_temp", None)   # °C; None = don't touch cooler

# ── Image-train metadata (telescope + camera) ────────────────────────────────
telescope_name    = params.get("telescope_name",    None)
focal_length      = params.get("focal_length",      None)   # mm
aperture          = params.get("aperture",          None)   # mm
pixel_size_x      = params.get("pixel_size_x",      None)   # µm
pixel_size_y      = params.get("pixel_size_y",      None)   # µm
sensor_width_px   = params.get("sensor_width_px",   None)
sensor_height_px  = params.get("sensor_height_px",  None)
camera_name       = params.get("camera_name",       None)

# ── Target metadata (optional, for FITS headers / plate solving) ─────────────
target_name  = params.get("target_name",  None)
target_ra    = params.get("target_ra",    None)   # hours
target_dec   = params.get("target_dec",   None)   # degrees
target_epoch = params.get("target_epoch", "J2000")

# ── Map frame type to INDI switch element ────────────────────────────────────
FRAME_MAP = {
    "light":     "FRAME_LIGHT",
    "dark":      "FRAME_DARK",
    "flat":      "FRAME_FLAT",
    "bias":      "FRAME_BIAS",
    "dark_flat": "FRAME_DARK",   # no universal INDI element for dark-flat
}
indi_frame_type = FRAME_MAP.get(frame_type, "FRAME_LIGHT")

# ── Connect camera ───────────────────────────────────────────────────────────
conn = indi.get_property(device, "CONNECTION")
if conn is None or indi.get_value(device, "CONNECTION", "CONNECT") != "On":
    log("Connecting to camera…")
    indi.connect_device(device)
    indi.wait_for_state(device, "CONNECTION", "Ok", timeout=15.0)

# ── Enable BLOB reception ─────────────────────────────────────────────────────
# Called once here to activate BLOB mode on the INDI server and register this
# run as the owner of incoming BLOBs. capture_params (including frame_index)
# are updated via update_blob_params() before each exposure inside the loop.
indi.enable_blobs(device, capture_params={"exposure": exposure, "frame_type": frame_type, "count": count})

# ── Cooler ───────────────────────────────────────────────────────────────────
if cooler_temp is not None:
    cooler_tolerance = params.get("cooler_tolerance", 0.5)   # °C
    cooler_timeout   = params.get("cooler_timeout",   300.0) # seconds

    log(f"Setting cooler target to {cooler_temp}°C…")
    indi.set_switch(device, "CCD_COOLER", {"COOLER_ON": "On"})
    indi.set_number(device, "CCD_TEMPERATURE", {"CCD_TEMPERATURE_VALUE": cooler_temp})

    # Wait until the sensor temperature is within tolerance
    elapsed = 0.0
    poll = 5.0
    while elapsed < cooler_timeout:
        current = indi.get_value(device, "CCD_TEMPERATURE", "CCD_TEMPERATURE_VALUE")
        if current is not None and math.fabs(current - cooler_temp) <= cooler_tolerance:
            log(f"Cooler at {current:.1f}°C — ready", progress=0.0)
            break
        log(
            f"Cooling… current {current:.1f}°C, target {cooler_temp}°C"
            if current is not None else "Waiting for cooler…",
            progress=0.0,
        )
        time_utils.sleep(poll)
        elapsed += poll
    else:
        temp_str = f"{current:.1f}°C" if current is not None else "unknown"
        raise RuntimeError(
            f"Cooler did not reach {cooler_temp}°C within {cooler_timeout}s "
            f"(current: {temp_str}). Aborting to protect data quality."
        )

# ── Binning ──────────────────────────────────────────────────────────────────
# Must be applied (and confirmed) before sub-frame, because binning changes
# the effective pixel grid and can reset the readout region.
if bin_x != 1 or bin_y != 1:
    indi.set_number(device, "CCD_BINNING", {"HOR_BIN": bin_x, "VER_BIN": bin_y})
    indi.wait_for_state(device, "CCD_BINNING", "Ok", timeout=10.0)

# ── Sub-frame ────────────────────────────────────────────────────────────────
if all(v is not None for v in (frame_x, frame_y, frame_w, frame_h)):
    indi.set_number(device, "CCD_FRAME", {
        "X": frame_x, "Y": frame_y, "WIDTH": frame_w, "HEIGHT": frame_h,
    })
    indi.wait_for_state(device, "CCD_FRAME", "Ok", timeout=10.0)

# ── Gain / offset ────────────────────────────────────────────────────────────
if gain is not None:
    indi.set_number(device, "CCD_GAIN", {"GAIN": gain})
    indi.wait_for_state(device, "CCD_GAIN", "Ok", timeout=10.0)
if offset is not None:
    indi.set_number(device, "CCD_OFFSET", {"OFFSET": offset})
    indi.wait_for_state(device, "CCD_OFFSET", "Ok", timeout=10.0)

# ── Format ───────────────────────────────────────────────────────────────────
if format_ is not None:
    indi.set_switch(device, "CCD_TRANSFER_FORMAT", {format_: "On"})

# ── Frame type ───────────────────────────────────────────────────────────────
indi.set_switch(device, "CCD_FRAME_TYPE", {indi_frame_type: "On"})

# ── Filter wheel ─────────────────────────────────────────────────────────────
if filter_device and filter_name:
    fw_conn = indi.get_property(filter_device, "CONNECTION")
    if fw_conn is None or indi.get_value(filter_device, "CONNECTION", "CONNECT") != "On":
        log(f"Connecting to filter wheel {filter_device}…")
        indi.connect_device(filter_device)
        indi.wait_for_state(filter_device, "CONNECTION", "Ok", timeout=15.0)
    log(f"Selecting filter: {filter_name}")
    indi.set_switch(filter_device, "FILTER_SLOT", {filter_name: "On"})
    indi.wait_for_state(filter_device, "FILTER_SLOT", "Ok", timeout=30.0)

# ── Capture loop ─────────────────────────────────────────────────────────────
for i in range(count):
    # Checkpoint before the exposure: if paused here (or mid-exposure with
    # finish_current=False), the resume command re-does this frame.
    indi.checkpoint({
        "device": device, "count": count - i, "exposure": exposure,
        "delay": delay, "frame_type": frame_type,
        "gain": gain, "offset": offset, "bin_x": bin_x, "bin_y": bin_y,
        "frame_x": frame_x, "frame_y": frame_y, "frame_w": frame_w, "frame_h": frame_h,
        "format": format_, "filter_device": filter_device, "filter_name": filter_name,
        "cooler_temp": cooler_temp,
        "telescope_name": telescope_name, "focal_length": focal_length,
        "aperture": aperture, "pixel_size_x": pixel_size_x, "pixel_size_y": pixel_size_y,
        "sensor_width_px": sensor_width_px, "sensor_height_px": sensor_height_px,
        "camera_name": camera_name,
        "target_name": target_name, "target_ra": target_ra,
        "target_dec": target_dec, "target_epoch": target_epoch,
    })

    frame_label = f"frame {i + 1}/{count}" if count > 1 else "frame"
    log(f"Capturing {frame_label} — {exposure}s {frame_type}…", progress=i / count)

    # Update per-frame capture metadata without re-sending setBLOBMode to the
    # INDI server (re-sending mid-sequence delays BLOB delivery).
    indi.update_blob_params(device, {
        "exposure":     exposure,
        "frame_type":   frame_type,
        "frame_index":  i + 1,
        "count":        count,
        "gain":         gain,
        "offset":       offset,
        "bin_x":        bin_x,
        "bin_y":        bin_y,
        "frame_x":      frame_x,
        "frame_y":      frame_y,
        "frame_w":      frame_w,
        "frame_h":      frame_h,
        "filter_name":  filter_name,
        "cooler_temp":  cooler_temp,
        "sensor_temp":  indi.get_value(device, "CCD_TEMPERATURE", "CCD_TEMPERATURE_VALUE"),
    })

    indi.set_number(device, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": exposure})
    indi.wait_for_state(device, "CCD_EXPOSURE", "Busy", timeout=10.0)
    ok = indi.wait_for_state(device, "CCD_EXPOSURE", "Ok", timeout=exposure + 60)

    if not ok:
        log(f"Exposure {i + 1} timed out or failed", progress=(i + 1) / count)
        break

    log(f"Captured {frame_label}", progress=(i + 1) / count)

    if i + 1 < count:
        # Checkpoint after completing this frame: if paused during the delay
        # (or at the start of the next iteration), resume skips to the next frame.
        indi.checkpoint({
            "device": device, "count": count - (i + 1), "exposure": exposure,
            "delay": delay, "frame_type": frame_type,
            "gain": gain, "offset": offset, "bin_x": bin_x, "bin_y": bin_y,
            "frame_x": frame_x, "frame_y": frame_y, "frame_w": frame_w, "frame_h": frame_h,
            "format": format_, "filter_device": filter_device, "filter_name": filter_name,
            "cooler_temp": cooler_temp,
            "telescope_name": telescope_name, "focal_length": focal_length,
            "aperture": aperture, "pixel_size_x": pixel_size_x, "pixel_size_y": pixel_size_y,
            "sensor_width_px": sensor_width_px, "sensor_height_px": sensor_height_px,
            "camera_name": camera_name,
            "target_name": target_name, "target_ra": target_ra,
            "target_dec": target_dec, "target_epoch": target_epoch,
        })

    if delay > 0 and i < count - 1:
        log(f"Waiting {delay}s before next frame…", progress=(i + 1) / count)
        time_utils.sleep(delay)

log("Done", progress=1.0)
