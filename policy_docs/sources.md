# Policy Document Sources

Official sources for the TransitWise Replanner's RAG knowledge base.

| File | Source | Link |
|---|---|---|
| access_in_motion.pdf | MBTA (via mass.gov) | https://www.mass.gov/doc/mbta-access-in-motion-english/download |
| boston_closure_shuttle_policy.pdf | City of Boston | https://www.boston.gov/departments/transportation/accessibility-during-mbta-closures |
| mbta_accessibility_overview.pdf | MBTA | https://www.mbta.com/accessibility |
| the_ride.pdf | MBTA | https://www.mbta.com/accessibility/the-ride/on-demand-pilot |

## Notes
- Web pages were saved with Chrome (Ctrl + P → Save as PDF). `pipeline/build_db.py` strips the
  printed page chrome (headers, menus, footer links) before chunking.
- Only `policy_docs/*.pdf` is indexed. Live status (which elevators are out right now) must come
  only from the MBTA V3 API, never from saved pages.
- `archive/` holds two October 2026 snapshots of live-status pages (`mbta_elevator_alerts.pdf`,
  `station_downtown_crossing.pdf`). They were removed from the index because the LLM quoted their
  outdated elevator status as current fact.
- Downloaded: October 2026.