# Model service template

Copy this folder to add a new model:

```bash
cp -r services/_template services/<model-name>
```

Then:
1. Fill in `app/settings.py` (MODEL_NAME, MODEL_VERSION).
2. Implement `app/model/loader.py`, `preprocess.py`, `postprocess.py`.
3. Declare the real input/output shapes in `app/schemas.py`.
4. Add a service block to `docker-compose.yml` (pick the next free host port: 8101, 8102, …).
5. Add `<MODEL>_SERVICE_URL` to `.env.example` and `apps/api/app/core/config.py`.
6. Add a client in `apps/api/app/integrations/<model>_client.py` (3 lines — subclass `ModelServiceClient`).
7. Insert a row into `models.model_registry`.

**The core API must never import this package.** It only talks HTTP.
