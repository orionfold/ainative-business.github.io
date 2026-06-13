# Copyright 2026 Manav Sehgal
# SPDX-License-Identifier: Apache-2.0
"""The Field Edition Docker Compose bundle — `fieldkit field-edition up` step 2.

Implements the §5/§7 packaging shape of ``_SPECS/arena-field-edition-v1.md``:
a **hybrid** install where ``fieldkit[arena]`` rides a pipx wheel (the Arena
cockpit is a host process) and everything that touches **CUDA or Postgres**
runs as a **digest-pinned Docker Compose** stack. This module owns the Compose
side: the three container services that the cockpit drives.

| service    | what it is                              | host port |
|------------|-----------------------------------------|-----------|
| ``cortex-db`` | pgvector Postgres (the corpus store) | 5432      |
| ``embedder``  | the open default embedder            | 8001      |
| ``advisor-lane`` | a llama.cpp CUDA-13/SM121 lane serving the resident GGUF | 8091 |

The Arena sidecar is **not** here — it is the pipx ``fieldkit[arena]`` process
on ``:7866`` (§5), started by ``up`` after the stack is healthy.

Design (the deterministic-scripts invariant, same as :mod:`doctor`):
:func:`render_compose` is a **pure function** — config in, the Compose document
out as a plain ``dict`` — so the whole bundle is unit-testable without Docker.
The only I/O is :func:`write_bundle` (writes the rendered files to disk) and the
lazy ``yaml`` import in :func:`compose_yaml` (``pyyaml`` ships in the ``[arena]``
extra the bootstrap installs; ``import fieldkit.field_edition`` stays
core-only).

**Pin discipline.** Every image carries an :class:`ImagePin`. Upstream images
(pgvector) are real and can be digest-pinned today; the Orionfold-built images
(the open embedder, the llama.cpp CUDA-13 lane) **do not exist yet** — their
pins are :data:`PIN_PENDING` and :func:`unpinned_images` surfaces them so a
``up`` against this bundle fails honestly ("image not yet published") rather
than silently. Re-pin to real ``sha256:`` digests before the M2 clean-wipe /
M4 launch — same "drift is visible, not silent" stance as
``doctor.TESTED_MATRIX``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

__all__ = [
    "PIN_PENDING",
    "ImagePin",
    "EmbedderConfig",
    "LaneConfig",
    "PostgresConfig",
    "FieldEditionConfig",
    "NIM_EMBEDDER",
    "default_config",
    "render_compose",
    "compose_yaml",
    "render_env",
    "unpinned_images",
    "write_bundle",
]

#: Sentinel digest for an Orionfold image that is not yet built/published. An
#: :class:`ImagePin` carrying it renders as ``repo:tag`` (so the file is valid)
#: but :func:`unpinned_images` flags it — the §9 "proven matrix" is only proven
#: once every pin is a real ``sha256:`` digest.
PIN_PENDING = "PENDING"


@dataclass(frozen=True)
class ImagePin:
    """A container image reference that can be pinned by digest.

    ``reference()`` renders ``repo@sha256:…`` once :attr:`digest` is a real
    digest, and ``repo:tag`` while it is still :data:`PIN_PENDING` (or ``None``)
    — so the bundle is always a valid Compose file, and :attr:`pinned` reports
    whether the §9 digest-pin discipline is satisfied.
    """

    repo: str
    tag: str
    digest: str | None = None
    note: str = ""

    @property
    def pinned(self) -> bool:
        return bool(self.digest) and self.digest != PIN_PENDING

    def reference(self) -> str:
        if self.pinned:
            return f"{self.repo}@{self.digest}"
        return f"{self.repo}:{self.tag}"


# --- Service configs ---------------------------------------------------------


@dataclass(frozen=True)
class PostgresConfig:
    """pgvector Postgres — the Cortex corpus store (mirrors the running box:
    ``pgvector/pgvector:pg16`` on ``:5432``, db/user/password ``spark``)."""

    image: ImagePin = field(
        default_factory=lambda: ImagePin(
            "pgvector/pgvector",
            "pg16",
            # The dogfood box's arm64 pull digest. Re-pin the multi-arch
            # manifest-list digest at launch (this one is platform-specific).
            digest="sha256:7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff",
        )
    )
    container_name: str = "of-cortex-db"
    port: int = 5432
    db: str = "vectors"
    user: str = "spark"
    password: str = "spark"
    volume: str = "of-cortex-pgdata"


@dataclass(frozen=True)
class EmbedderConfig:
    """The Cortex embedder. The §5 *default* is an OPEN embedder (no NGC login,
    clean AC-2 offline) — its image is Orionfold-built and not yet published, so
    it ships :data:`PIN_PENDING`. ``NIM_EMBEDDER`` is the optional BYO-NGC-key
    alternate (what the dogfood box runs today; needs ``NGC_API_KEY``)."""

    image: ImagePin = field(
        default_factory=lambda: ImagePin(
            "ghcr.io/orionfold/cortex-embedder",
            "0.1",
            digest=PIN_PENDING,
            note="open embedder image not yet built — §5 GGUF/sentence-transformers default",
        )
    )
    container_name: str = "of-embedder"
    port: int = 8001
    container_port: int = 8000
    model: str = "Orionfold/cortex-embed-open"
    dim: int = 1024
    needs_ngc_key: bool = False
    gpu: bool = True


#: The optional BYO-NGC-key NIM embedder (the §5 "NIM-optional" path). This is
#: the image actually running on the dogfood box; selecting it trades the clean
#: offline story for a real, already-pinned image. ``up --embedder nim`` picks
#: it (and `up` then requires ``~/.nim/secrets.env``).
NIM_EMBEDDER = EmbedderConfig(
    image=ImagePin(
        "nvcr.io/nim/nvidia/llama-nemotron-embed-1b-v2",
        "latest",
        note="BYO NGC key; needs ~/.nim/secrets.env",
    ),
    model="nvidia/llama-nemotron-embed-1b-v2",
    needs_ngc_key=True,
)


@dataclass(frozen=True)
class LaneConfig:
    """The serving lane — a llama.cpp CUDA-13/SM121 container serving the
    resident GGUF. The image is Orionfold-built (no aarch64+CUDA-13 wheel, so we
    ship a prebuilt container, §5) and not yet published → :data:`PIN_PENDING`.
    Defaults mirror the live ``advisor-gguf`` recipe (4B Q4_K_M warm default,
    ``-ngl 99``, ``n_ctx 8192``, ``--jinja`` — see ``arena.launcher``)."""

    image: ImagePin = field(
        default_factory=lambda: ImagePin(
            "ghcr.io/orionfold/llama-server-cuda13",
            "0.1",
            digest=PIN_PENDING,
            note="CUDA-13/SM121 llama.cpp lane image not yet built",
        )
    )
    container_name: str = "of-advisor-lane"
    port: int = 8091
    # The model file *inside the store volume* (mounted read-only at /models).
    gguf_name: str = "advisor-gguf/model-Q4_K_M.gguf"
    ngl: int = 99
    n_ctx: int = 8192


@dataclass(frozen=True)
class FieldEditionConfig:
    """The whole Field Edition install configuration.

    ``home`` is the bundle root (``~/.orionfold``); ``model_store`` is the
    host dir holding pulled GGUFs + embedder weights (mounted into the lane +
    embedder containers). ``network`` is the user-defined bridge the three
    services share (so the cockpit reaches them by container name)."""

    home: Path = field(default_factory=lambda: Path.home() / ".orionfold")
    model_store: Path = field(default_factory=lambda: Path.home() / ".orionfold" / "models")
    network: str = "of-net"
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    lane: LaneConfig = field(default_factory=LaneConfig)

    def with_nim_embedder(self) -> "FieldEditionConfig":
        """Return a copy using the BYO-NGC-key NIM embedder (the box-today path)."""
        return replace(self, embedder=NIM_EMBEDDER)


def default_config() -> FieldEditionConfig:
    """The shipped default: GGUF-default everything, open embedder (§5)."""
    return FieldEditionConfig()


# --- Pure renderer -----------------------------------------------------------


def _gpu_reservation() -> dict:
    """The Compose ``deploy.resources`` block requesting all NVIDIA GPUs.

    Equivalent to ``docker run --gpus all`` — the Container Toolkit DGX OS
    ships preinstalled wires this through (§7)."""
    return {
        "resources": {
            "reservations": {
                "devices": [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]
            }
        }
    }


def render_compose(config: FieldEditionConfig | None = None) -> dict:
    """Render the Compose document as a plain ``dict`` (pure; no I/O).

    The model store is mounted **read-only** into the lane + embedder (the
    cockpit / pulls own writes); the corpus store gets a named volume so
    ``down`` can preserve it and ``down --purge`` can drop it (AC-6)."""
    cfg = config or default_config()
    pg, emb, lane = cfg.postgres, cfg.embedder, cfg.lane
    store = "/models"

    db: dict = {
        "image": pg.image.reference(),
        "container_name": pg.container_name,
        "restart": "unless-stopped",
        "environment": {
            "POSTGRES_DB": pg.db,
            "POSTGRES_USER": pg.user,
            "POSTGRES_PASSWORD": pg.password,
        },
        "ports": [f"127.0.0.1:{pg.port}:5432"],
        "volumes": [f"{pg.volume}:/var/lib/postgresql/data"],
        "networks": [cfg.network],
        "healthcheck": {
            "test": ["CMD-SHELL", f"pg_isready -U {pg.user} -d {pg.db}"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 5,
        },
    }

    embedder: dict = {
        "image": emb.image.reference(),
        "container_name": emb.container_name,
        "restart": "unless-stopped",
        "environment": {"OF_EMBED_MODEL": emb.model, "OF_EMBED_DIM": str(emb.dim)},
        "ports": [f"127.0.0.1:{emb.port}:{emb.container_port}"],
        "volumes": [f"{cfg.model_store}:{store}:ro"],
        "networks": [cfg.network],
    }
    if emb.needs_ngc_key:
        # The NIM image takes its key from the env; the bootstrap sources
        # ~/.nim/secrets.env into the `up` environment (§7 secret handling).
        embedder["environment"]["NGC_API_KEY"] = "${NGC_API_KEY:?set NGC_API_KEY for the NIM embedder}"
        embedder["environment"]["NIM_HTTP_API_PORT"] = str(emb.container_port)
    if emb.gpu:
        embedder["deploy"] = _gpu_reservation()

    advisor_lane: dict = {
        "image": lane.image.reference(),
        "container_name": lane.container_name,
        "restart": "unless-stopped",
        "command": [
            "-m",
            f"{store}/{lane.gguf_name}",
            "--host",
            "0.0.0.0",
            "--port",
            str(lane.port),
            "-ngl",
            str(lane.ngl),
            "-c",
            str(lane.n_ctx),
            "--jinja",
        ],
        "ports": [f"127.0.0.1:{lane.port}:{lane.port}"],
        "volumes": [f"{cfg.model_store}:{store}:ro"],
        "networks": [cfg.network],
        "deploy": _gpu_reservation(),
        "depends_on": {pg.container_name: {"condition": "service_healthy"}},
    }

    return {
        "name": "orionfold-field-edition",
        "services": {
            pg.container_name: db,
            emb.container_name: embedder,
            lane.container_name: advisor_lane,
        },
        "volumes": {pg.volume: {}},
        "networks": {cfg.network: {"driver": "bridge"}},
    }


def render_env(config: FieldEditionConfig | None = None) -> str:
    """Render the ``.env`` the operator can edit beside the bundle (the cockpit
    reads the same values to reach the stack)."""
    cfg = config or default_config()
    lines = [
        "# Orionfold Arena Field Edition — generated by `fieldkit field-edition up`.",
        "# Edit + re-run `up` to apply (the bundle is re-rendered each run).",
        f"OF_MODEL_STORE={cfg.model_store}",
        f"OF_NETWORK={cfg.network}",
        f"OF_CORTEX_DB=postgres://{cfg.postgres.user}:{cfg.postgres.password}"
        f"@127.0.0.1:{cfg.postgres.port}/{cfg.postgres.db}",
        f"OF_EMBED_URL=http://127.0.0.1:{cfg.embedder.port}/v1/embeddings",
        f"OF_EMBED_MODEL={cfg.embedder.model}",
        f"OF_LANE_URL=http://127.0.0.1:{cfg.lane.port}/v1",
    ]
    return "\n".join(lines) + "\n"


def compose_yaml(config: FieldEditionConfig | None = None) -> str:
    """Serialize :func:`render_compose` to a YAML string (lazy ``yaml`` import).

    ``pyyaml`` ships in the ``[arena]`` extra the §7 bootstrap installs; keeping
    the import lazy means ``import fieldkit.field_edition`` stays core-only."""
    import yaml  # lazy: pyyaml is an [arena]-extra dep, not core

    return yaml.safe_dump(render_compose(config), sort_keys=False, default_flow_style=False)


def unpinned_images(config: FieldEditionConfig | None = None) -> list[ImagePin]:
    """Every image still on a placeholder (not digest-pinned) — the §9 gate.

    A non-empty list means the bundle references images that are not yet
    published/proven; ``up`` surfaces it so a live pull fails with a clear
    reason instead of a cryptic registry error."""
    cfg = config or default_config()
    return [p for p in (cfg.postgres.image, cfg.embedder.image, cfg.lane.image) if not p.pinned]


# --- Thin I/O ----------------------------------------------------------------


def write_bundle(config: FieldEditionConfig | None = None) -> Path:
    """Write ``compose.yaml`` + ``.env`` into ``config.home`` and return the
    compose path. Creates the home + model-store dirs. Idempotent — re-running
    re-renders both files (the bundle is regenerated, never hand-patched)."""
    cfg = config or default_config()
    cfg.home.mkdir(parents=True, exist_ok=True)
    cfg.model_store.mkdir(parents=True, exist_ok=True)
    compose_path = cfg.home / "compose.yaml"
    compose_path.write_text(compose_yaml(cfg), encoding="utf-8")
    (cfg.home / ".env").write_text(render_env(cfg), encoding="utf-8")
    return compose_path
