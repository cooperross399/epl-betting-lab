from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from epl_betting_lab.providers.base import (
    BaseStagingProvider,
    ProviderRunRequest,
    UnknownProviderError,
)
from epl_betting_lab.providers.manual_staging_provider import (
    run_manual_staging_provider,
)
from epl_betting_lab.providers.odds_api_staging_provider import (
    OddsApiStagingProvider,
)


ProviderFactory = Callable[..., BaseStagingProvider]


class ManualStagingProviderAdapter(BaseStagingProvider):
    """Expose the existing controlled manual provider through the registry."""

    provider_key = "manual"
    provider_name = "manual_reviewed"
    provider_type = "manual_upload"

    def __init__(
        self,
        *,
        odds_source_path: Path | None = None,
        fixtures_source_path: Path | None = None,
        provider_name: str = "manual_reviewed",
    ) -> None:
        self.odds_source_path = odds_source_path
        self.fixtures_source_path = fixtures_source_path
        self.provider_name = provider_name.strip() or "manual_reviewed"

    def run(self, request: ProviderRunRequest) -> dict[str, object]:
        return run_manual_staging_provider(
            odds_source_path=self.odds_source_path,
            fixtures_source_path=self.fixtures_source_path,
            provider_name=self.provider_name,
            generated_by=request.generated_by,
            notes=request.notes,
            dry_run=request.dry_run,
            overwrite_staging=request.overwrite_staging,
            repository_root=request.repository_root,
            run_at=request.run_at,
        )


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "manual": ManualStagingProviderAdapter,
    "odds_api": OddsApiStagingProvider,
}


def available_provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDER_FACTORIES))


def create_provider(provider_name: str, **kwargs: object) -> BaseStagingProvider:
    key = provider_name.strip().lower().replace("-", "_")
    factory = _PROVIDER_FACTORIES.get(key)
    if factory is None:
        available = ", ".join(available_provider_names())
        raise UnknownProviderError(
            f"Unknown provider `{provider_name}`. Available providers: {available}."
        )
    return factory(**kwargs)
