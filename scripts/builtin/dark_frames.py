"""Take a series of dark frames with a CCD camera.

params:
  count    (int):   number of frames to take (default: 5)
  exposure (float): exposure duration in seconds (default: 30.0)
  device   (str):   CCD device name (default: 'CCD Simulator')
"""

count = params.get("count", 5)
exposure = params.get("exposure", 30.0)
device = params.get("device", "CCD Simulator")

log(f"Starting dark sequence: {count} frames at {exposure}s each")

for i in range(count):
    log(f"Taking frame {i + 1}/{count}", progress=i / count)

    # Close the shutter (dark frame)
    indi.set_switch(device, "CCD_FRAME_TYPE", {"FRAME_DARK": "On"})

    # Trigger the exposure
    indi.set_number(device, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": exposure})

    # Wait for the exposure to finish (state: Busy → Ok)
    ok = indi.wait_for_state(device, "CCD_EXPOSURE", "Ok", timeout=exposure + 60)
    if not ok:
        log(f"Frame {i + 1} timed out — skipping")
        continue

    log(f"Frame {i + 1}/{count} saved", progress=(i + 1) / count)

log("Dark sequence complete", progress=1.0)
