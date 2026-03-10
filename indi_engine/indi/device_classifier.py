"""Device type classifier based on INDI standard properties.

Determines all functional roles of an INDI device from the set of property
names it has registered. A device may have multiple roles — for example a
camera with a built-in filter wheel has roles ["camera", "filter_wheel"].

Uses the INDI Standard Properties specification:
https://docs.indilib.org/drivers/standard-properties/

Possible role values: "mount", "camera", "focuser", "filter_wheel",
"rotator", "dome", "weather", "gps".
"""

# For each role, a list of alternative property-name sets that identify it.
# A device matches a role when ANY of its signature sets is a subset of the
# device's registered property names.  Signatures with a single property are
# the most specific; multi-property ones are fallbacks.
_ROLE_SIGNATURES: dict[str, list[frozenset]] = {
    "mount": [
        frozenset({"TELESCOPE_MOTION_NS"}),
        frozenset({"EQUATORIAL_EOD_COORD", "TELESCOPE_SLEW_RATE"}),
    ],
    "camera": [
        frozenset({"CCD_EXPOSURE"}),
        frozenset({"CCD_FRAME", "CCD_TEMPERATURE"}),
    ],
    "focuser": [
        frozenset({"FOCUS_MOTION"}),
        frozenset({"ABS_FOCUS_POSITION"}),
    ],
    "filter_wheel": [
        frozenset({"FILTER_SLOT"}),
    ],
    "rotator": [
        frozenset({"ABS_ROTATOR_ANGLE"}),
    ],
    "dome": [
        frozenset({"DOME_MOTION"}),
        frozenset({"DOME_SHUTTER"}),
    ],
    "weather": [
        frozenset({"WEATHER_STATUS"}),
        frozenset({"WEATHER_UPDATE"}),
    ],
    "gps": [
        frozenset({"GPS_REFRESH"}),
        frozenset({"SYSTEM_TIME_UPDATE"}),
    ],
}

# Canonical display order — most "primary" role listed first
_ROLE_ORDER = [
    "mount", "camera", "focuser", "filter_wheel",
    "rotator", "dome", "weather", "gps",
]


def classify_device(property_names: set[str]) -> list[str]:
    """Return all functional roles detected in the given property names.

    Args:
        property_names: Set of property names registered on the device
                        (i.e. the keys of IDevice.properties).

    Returns:
        A list of role strings in canonical priority order.  The list is
        empty when no known roles are detected.  A device with a built-in
        filter wheel, for example, returns ["camera", "filter_wheel"].
    """
    roles = []
    for role in _ROLE_ORDER:
        for required in _ROLE_SIGNATURES[role]:
            if required.issubset(property_names):
                roles.append(role)
                break  # Only add each role once per device
    return roles
