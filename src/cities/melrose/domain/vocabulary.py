"""The closed set of results the department prints after a call type.

The PDF has no columns: a call line reads "26-11102 0858 MOTOR VEHICLE STOP Citation/Warning Issued",
so the result is found by matching the end of the line against this list. A result not listed
quarantines its document, which is how a change in the format shows up. Extend the list only with
a fixture that shows the new result in a published log.
"""

from __future__ import annotations

import re

KNOWN_RESULTS: frozenset[str] = frozenset(
    {
        "* Report taken",
        "Alarm-Medical Device",
        "Building Checked - Secure",
        "Citation/Warning Issued",
        "Could Not Locate",
        "Extinguished",
        "False Alarm",
        "Field Interrogation",
        "No Action Required",
        "Notification Made",
        "Notified Agency (Gas,Elec,etc)",
        "Parking Ticket Issued",
        "Peace Restored",
        "Removed Hazard",
        "Restraining Order Not Served",
        "Restraining Order Served",
        "Secured Building",
        "Services Rendered",
        "Summons Not Served",
        "Summons Served",
        "Taken to Family/Guardian/Other",
        "Taken/Referred to Other Agency",
        "Transported to Hospital",
        "Unfounded",
        "Unit Clear",
        "Vehicle Towed",
        "Verbal Warning",
    }
)

# Results printed cut short in published logs, kept verbatim. Each was seen in a log collected from
# January 2025 onward; the full form is in KNOWN_RESULTS where it is known.
TRUNCATED_RESULTS: frozenset[str] = frozenset(
    {
        "*",
        "* Report",
        "Building Checked -",
        "Citation/Warning",
        "False Alarm/Cancelled Alarm Co",
        "Notification",
        "Restraining",
        "Restraining Order",
        "Restraining Order Not",
        "Services",
        "Summons",
        "Summons Not",
        "Taken/Referred to Other",
        "Transported to",
        "Unit",
    }
)

# Arrest results carry an age band and sex, and are sometimes printed without them.
ARREST_RESULT = re.compile(r"\* Arrest(?: Under 17| 17 and Over| 17)?(?: Male| Female)?")

# The call type design R7 ranks and AC2 measures. Phase 3's categories.toml groups call types for the map.
STOP_CALL_TYPE = "MOTOR VEHICLE STOP"
