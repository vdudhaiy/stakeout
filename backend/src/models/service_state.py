from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from database import Base


class ServiceState(Base):
    """Small key/value store for process state that must survive a restart.

    Everything in cache.py is deliberately in-process and cheap to lose. A
    backoff is the opposite: it is the record of a refusal we already
    received, and forgetting it is actively harmful. On a host that recycles
    many times a day, a cooldown held only in memory means the next boot
    walks straight back into the same rate limit — and the boot is itself
    triggered by a user's page load, so the throttle renews exactly when the
    app can least afford it.

    Deliberately generic rather than a `yf_cooldown` table: this is the third
    time a scalar has needed to outlive the process, and a one-row-per-fact
    table each time is worse than one table with a key.
    """

    __tablename__ = "service_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
    # Wall-clock, UTC-aware. The consumers of this table compare against
    # real time, not time.monotonic() — monotonic clocks restart with the
    # process, which is precisely the case this table exists to survive.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
