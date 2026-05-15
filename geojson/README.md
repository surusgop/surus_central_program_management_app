# District GeoJSON

Place your district boundary file here as `districts.geojson`.

## Required format

Standard GeoJSON FeatureCollection with Polygon or MultiPolygon geometries:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "district-001",
      "properties": {
        "id": "district-001",
        "name": "District 1"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lng, lat], ...]]
      }
    }
  ]
}
```

## Connecting to Databricks data

The `properties.id` value (or whichever property you set as `GEOJSON_ID_PROPERTY`
in `pages/map_view.py`) must exactly match the `district_id` values returned
by your Databricks queries in `data/queries.py`.

## Tips

- Keep file size under ~10 MB for reasonable browser performance. Simplify
  geometry with mapshaper.org if needed.
- Coordinate system must be WGS84 (EPSG:4326).
- Set `MAP_CENTER` and `MAP_ZOOM` in `pages/map_view.py` to your region.
