"""Import every ORM model here so Alembic autogenerate can see them."""
from app.core.db import Base  # noqa: F401

# One line per module as its tables are written.
from app.modules.ccm.models import CCMResult, CCMUnion, Cyclone  # noqa: F401,E402
