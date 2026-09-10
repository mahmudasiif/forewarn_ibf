# CCM model service

The first model integrated into the FOREWARN IBF Portal.

- Runs at `http://ccm:8000` inside the compose network, `http://localhost:8101` on the host.
- Weights are mounted read-only from `./weights` (gitignored — keep the artefacts out of git).
- Speaks the standard contract: `/health`, `/info`, `/predict`, `/predict/async`, `/jobs/{id}`.

## To be filled in before Day 2

| Question | Answer |
|---|---|
| What does CCM stand for / do? | _TBD_ |
| Inputs (variables, units, spatial + temporal resolution) | _TBD_ |
| Outputs (variables, units, format) | _TBD_ |
| Weight/artefact files and their size | _TBD_ |
| Typical inference time | _TBD_ |
| Run cadence (on demand / scheduled) | _TBD_ |

Once these are known: update `app/schemas.py`, implement `app/model/*`, and register the
service in `models.model_registry`. Nothing in `apps/api` changes except one config line.
