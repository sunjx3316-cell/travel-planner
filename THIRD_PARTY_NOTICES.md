# Third-party data and assets

Licensed photographs: Wikimedia Commons, with per-image author, source URL, license and attribution stored in `spot_media` and shown in attraction details. Different images have different licenses; preserve their credits when redistributing. Verification is an import ledger status, not a new copyright grant.

Scenic reference photographs: 18 user-selected Xiaohongshu photo crops are included at the user's explicit request, separately listed in `bundled_data/reference-photos.json`. They retain `rights_status=pending`: public redistribution authorization has not been verified and the request is not a grant from the original rights holders. Source links and credits remain attached. Crops remove browser/site controls, not copyright notices or creator attribution; no scenery is generated or inpainted. Full research pages, comment screenshots and login QR codes are excluded. The app displays these assets only through its loopback-only reference endpoint. Their presence in this repository/download does not grant third-party reuse rights.

Review evidence: user-supplied curated summaries and linked references. Weak evidence remains labeled; no promise of comprehensive or current coverage. Source articles are not redistributed as a raw scraping archive. Platform and author rights remain with their owners. Public availability of a link is not permission to reproduce its contents.

Railway data and attribution: see [frontend/rail/NOTICE.md](frontend/rail/NOTICE.md) and the provenance metadata in `frontend/rail/data/`. Static schedules are not live availability or a ticket purchase service. Prices are only references. Confirm service, stations, transfers and tickets through 12306.

The embedded Python runtime retains its LICENSE.txt. Dependency distributions retain their own license files. ECharts and other vendored frontend assets retain their upstream notices.
