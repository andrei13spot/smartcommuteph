# rainfall source

the engine reads the 24-hour rainfall total for metro manila from the met
norway locationforecast 2.0 api (api.met.no, norwegian meteorological
institute). the panel approved this as the rainfall source in october 2026.

## what the engine does

- request: `GET https://api.met.no/weatherapi/locationforecast/2.0/compact`
  with `lat=14.62`, `lon=121.05` (cubao quadrant)
- no api key. met norway's terms ask every client to send an identifying
  `User-Agent`, so the engine sends
  `smartcommuteph-thesis/1.0 github.com/andrei13spot/smartcommuteph`
- the response gives precipitation per time block. the engine adds up the next
  24 hours: hourly blocks first, then 6-hour blocks if the hourly ones run out
  (`_metno_rainfall_24h` in `backend/app/ml/flood.py`)
- that total (mm) is the `rainfall_mm` feature of the rfr flood model, unless
  the request sends its own `rainfall_mm`
- a successful fetch is cached for one hour
- if the api cannot be reached the engine uses an offline default of 8 mm and
  tries again after about two minutes
- `/api/status` reports the value and where it came from (`rainfall_mm`,
  `rainfall_source`)

## settings

`SCPH_RAINFALL_PROVIDER=off` turns off the network fetch, so the engine always
uses the 8 mm default. the tests set this so they never touch the network.

## licence and credit

met norway data is free to use under the norwegian licence for open
government data (nlod) 2.0 and creative commons attribution 4.0 (cc by 4.0).
credit line: "weather data from met norway (api.met.no)". the tool names the
source on the researcher dashboard and on the safest profile card.

## limits

- it is a forecast, not a measured reading
- it is one value for the whole study area, not one per road
- the forecast runs about nine days ahead, the engine only uses the next 24 hours
