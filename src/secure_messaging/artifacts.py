from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


@dataclass(frozen=True)
class ArtifactLocation:
    provider: str
    locator: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if not self.provider or not self.locator:
            raise ValueError("artifact location provider and locator are required")
        return {"provider": self.provider, "locator": self.locator, "attributes": self.attributes}


@dataclass(frozen=True)
class ArtifactReference:
    sha256_hex: str
    size: int
    media_type: str | None = None
    logical_name: str | None = None
    locations: tuple[ArtifactLocation, ...] = ()

    def validate(self) -> None:
        if not _valid_sha256(self.sha256_hex):
            raise ValueError("sha256_hex must be a 64-character hexadecimal digest")
        if self.size < 0:
            raise ValueError("size must be non-negative")
        for location in self.locations:
            location.to_dict()

    @property
    def artifact_id(self) -> str:
        self.validate()
        return f"sha256:{self.sha256_hex.lower()}"

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256_hex.lower(),
            "size": self.size,
            "media_type": self.media_type,
            "logical_name": self.logical_name,
            "locations": [loc.to_dict() for loc in self.locations],
        }

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        media_type: str | None = None,
        logical_name: str | None = None,
        locations: tuple[ArtifactLocation, ...] = (),
    ) -> "ArtifactReference":
        p = Path(path)
        digest = sha256()
        size = 0
        with p.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        return cls(digest.hexdigest(), size, media_type, logical_name or p.name, locations)

    def verify_file(self, path: str | Path) -> bool:
        observed = ArtifactReference.from_file(path)
        return observed.size == self.size and observed.sha256_hex.lower() == self.sha256_hex.lower()
