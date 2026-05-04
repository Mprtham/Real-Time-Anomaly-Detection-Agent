from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import uuid


EVENT_TYPES = Literal["purchase", "page_view", "add_to_cart", "checkout_start", "error"]
DEVICES = Literal["mobile", "desktop", "tablet"]
REFERRERS = Literal["organic", "paid", "email", "direct"]

PAGES = ["/", "/products", "/product/detail", "/cart", "/checkout", "/confirmation", "/account", "/api/pay"]
COUNTRIES = ["US", "US", "US", "GB", "DE", "CA", "AU", "FR", "IN", "BR"]
PRODUCTS = [f"prod_{name}" for name in [
    "sneaker_001", "tshirt_002", "jacket_003", "bag_004", "watch_005",
    "shoes_006", "pants_007", "hat_008", "belt_009", "scarf_010"
]]


@dataclass
class Event:
    event_id: str
    timestamp: str
    event_type: str
    session_id: str
    user_id: str
    page: str
    product_id: str | None
    amount_usd: float | None
    latency_ms: int
    status_code: int
    country: str
    device: str
    referrer: str

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "page": self.page,
            "product_id": self.product_id,
            "amount_usd": self.amount_usd,
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "country": self.country,
            "device": self.device,
            "referrer": self.referrer,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(**d)
