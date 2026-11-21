---
title: TransitWise Boston
emoji: 🚇
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
startup_duration_timeout: 1h
pinned: false
short_description: Step-free door-to-door MBTA trips with live elevator checks
---

# TransitWise Boston

Step-free, door-to-door trip planning for wheelchair users on the MBTA. Trips combine rolling,
buses, subway, Commuter Rail and ferries, and every leg is checked against live MBTA elevator
and service alerts.

Code, docs and setup: https://github.com/monu4959/transitwise-boston

This Space runs OpenTripPlanner and the website in one container. It sleeps after two days
without visitors; the first visit after that takes a few minutes while it wakes up.

Before you travel, confirm elevator status at https://www.mbta.com/alerts/access.
TransitWise is not affiliated with or endorsed by the MBTA.
