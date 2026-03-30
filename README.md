# EV Charging + PQ Demonstrator

This project is a lightweight browser-based demonstrator for simulating EV charging at a site and showing a few simple power quality (PQ) indicators.

It is intentionally simple:

- Two canned scenarios: `Office Charging` and `Public Fast Hub`
- Four charging policies: uncontrolled, equal sharing, deadline-aware, and grid-aware
- A local Python web server
- No third-party Python dependencies for the MVP

## What "PQ" means here

For this demonstrator, PQ is shown through a few simple indicators:

- `Transformer loading`: are we pushing the site too hard?
- `Feeder loading`: same idea, but for the cable/feed into the site
- `Voltage`: does the local voltage sag too far when charging is heavy?
- `Power factor`: are we using power cleanly or inefficiently?
- `Phase imbalance`: are the three phases being used unevenly?
- `THD`: a simple harmonic distortion estimate

These calculations are intentionally approximate.

![Alt text](doc/screen1.png?raw=true "screenshot")

## Run it

From the project root:

```bash
python3 run_demo.py
```

Then open the local URL shown in the terminal, usually:

```text
http://127.0.0.1:8000
```

Stop with `Ctrl+C`.

## Run tests

```bash
python3 -m unittest discover -s tests
```

## Project layout

- `run_demo.py`: simple launch script
- `src/ev_pq_demo/server.py`: HTTP server and API endpoints
- `src/ev_pq_demo/scenarios.py`: canned EV charging scenarios
- `src/ev_pq_demo/simulator.py`: charging and PQ simulation engine
- `src/ev_pq_demo/static/`: browser UI
- `tests/`: small simulation tests

## Potential TODOs

- Add CSV import for real charging data
- Replace the simple PQ formulas with a power-flow engine
- Add cost signals or tariff-aware charging
- Save scenario runs to SQLite for history

