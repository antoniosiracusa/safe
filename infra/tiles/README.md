# TileServer-GL

In M4 questa cartella conterrà:

- `data/planet.pmtiles` — base OpenMapTiles generata con Planetiler (estratto Italia/Alpi)
- `data/terrain.pmtiles` — terrain-RGB da Copernicus DEM GLO-30
- `data/contours.pmtiles` — isoipse da TINITALY
- `data/slopes.pmtiles` — piste e impianti generati da PostGIS con tippecanoe (job `rebuild_tiles`)
- `styles/winter.json`, `styles/summer.json`, `styles/satellite.json`
- `fonts/`, `sprites/`

Fino ad allora il servizio parte con configurazione vuota e risponde su http://localhost:8081.
