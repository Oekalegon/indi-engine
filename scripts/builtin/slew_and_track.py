"""Slew the telescope to RA/DEC coordinates and start tracking.

params:
  ra     (float): Right Ascension in hours, e.g. 10.5
  dec    (float): Declination in degrees, e.g. 45.0
  device (str):   Telescope device name (default: 'Telescope Simulator')
"""

ra = params["ra"]
dec = params["dec"]
device = params.get("device", "Telescope Simulator")

# Connect if not already connected
conn = indi.get_property(device, "CONNECTION")
if conn is None or indi.get_value(device, "CONNECTION", "CONNECT") != "On":
    log("Connecting to telescope…")
    indi.connect_device(device)
    indi.wait_for_state(device, "CONNECTION", "Ok", timeout=15.0)

log(f"Slewing to RA={ra:.4f}h  DEC={dec:.4f}°")

# Enable tracking
indi.set_switch(device, "TELESCOPE_TRACK_STATE", {"TRACK_ON": "On"})

# Command the slew
indi.set_number(device, "EQUATORIAL_EOD_COORD", {"RA": ra, "DEC": dec})

# Wait for the mount to start moving
indi.wait_for_state(device, "EQUATORIAL_EOD_COORD", "Busy", timeout=10.0)

# Wait for the slew to finish
log("Slewing…", progress=0.1)
ok = indi.wait_for_state(device, "EQUATORIAL_EOD_COORD", "Ok", timeout=300.0)

if ok:
    log(f"Slew complete — tracking at RA={ra:.4f}h  DEC={dec:.4f}°", progress=1.0)
else:
    log("Slew timed out or failed", progress=1.0)
