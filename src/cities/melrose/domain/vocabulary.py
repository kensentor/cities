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
        "Building Checked - Secure",
        "Citation/Warning Issued",
        "Could Not Locate",
        "False Alarm",
        "Field Interrogation",
        "No Action Required",
        "Notification Made",
        "Parking Ticket Issued",
        "Peace Restored",
        "Removed Hazard",
        "Restraining Order Served",
        "Services Rendered",
        "Summons Not Served",
        "Summons Served",
        "Taken/Referred to Other Agency",
        "Transported to Hospital",
        "Unfounded",
        "Unit Clear",
        "Vehicle Towed",
        "Verbal Warning",
    }
)

# Results printed cut short in published logs, kept verbatim. Each was seen in a log collected from
# July 2026 onward; the full form is in KNOWN_RESULTS where it is known.
TRUNCATED_RESULTS: frozenset[str] = frozenset(
    {
        "* Report",
        "Citation/Warning",
        "False Alarm/Cancelled Alarm Co",
        "Restraining",
        "Restraining Order",
        "Summons Not",
        "Taken/Referred to Other",
    }
)

# Arrest results carry an age band and sex, and are sometimes printed without them.
ARREST_RESULT = re.compile(r"\* Arrest(?: Under 17| 17 and Over| 17)?(?: Male| Female)?")
