-- CLEAN layer. Created by pipeline/build_db.py after the first alert snapshot is loaded.

-- Elevators out of service in the latest alert snapshot, one row per affected station.
-- STATION_IDS also holds platform/entrance IDs; the join keeps only parent stations.
CREATE OR REPLACE VIEW TRANSITWISE_DB.CLEAN.CURRENT_ELEVATOR_OUTAGES AS
WITH latest AS (
  SELECT * FROM TRANSITWISE_DB.RAW.ALERTS_HISTORY
  WHERE EFFECT = 'ELEVATOR_CLOSURE'
    AND LOADED_AT = (SELECT MAX(LOADED_AT) FROM TRANSITWISE_DB.RAW.ALERTS_HISTORY)
)
SELECT DISTINCT s.STATION_ID, s.NAME AS STATION, a.FACILITY_IDS AS ELEVATOR, a.HEADER
FROM latest a,
     TABLE(SPLIT_TO_TABLE(a.STATION_IDS, ',')) st,
     TRANSITWISE_DB.RAW.STATIONS s
WHERE s.STATION_ID = st.VALUE;
