import asyncio
from typing import Any
from urllib.parse import urlencode

import httpx

from .cache import AsyncTTLCache
from .config import settings


class JolpicaClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.jolpica_base_url,
            timeout=httpx.Timeout(30),
            headers={"User-Agent": "f1-companion/0.2"},
        )
        self._cache = AsyncTTLCache()

    async def close(self) -> None:
        await self._http.aclose()

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        ttl: int = 86400,
    ) -> dict[str, Any]:
        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value is not None
        }
        cache_key = f"{path}?{urlencode(sorted(clean_params.items()))}"

        async def fetch() -> dict[str, Any]:
            response = await self._http.get(f"/{path}", params=clean_params)
            response.raise_for_status()
            return response.json()

        return await self._cache.get_or_set(cache_key, fetch, ttl)

    async def circuits(self) -> list[dict[str, Any]]:
        data = await self.get("circuits.json", {"limit": 100}, ttl=86400)
        return data["MRData"]["CircuitTable"]["Circuits"]

    async def circuit_results(self, circuit_id: str) -> list[dict[str, Any]]:
        first = await self.get(
            f"circuits/{circuit_id}/results.json",
            {"limit": 1000, "offset": 0},
            ttl=21600,
        )
        total = int(first["MRData"]["total"])
        page_size = int(first["MRData"]["limit"])
        pages = [first]
        for offset in range(page_size, total, page_size):
            try:
                pages.append(
                    await self.get(
                        f"circuits/{circuit_id}/results.json",
                        {"limit": page_size, "offset": offset},
                        ttl=21600,
                    )
                )
            except httpx.HTTPError:
                continue
        rows = [
            race
            for page in pages
            for race in page["MRData"]["RaceTable"]["Races"]
        ]
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for race in rows:
            key = (race["season"], race["round"])
            target = merged.setdefault(key, {**race, "Results": []})
            target["Results"].extend(race.get("Results", []))
        return sorted(
            merged.values(),
            key=lambda race: int(race["round"]),
        )

    async def season_schedule(self, year: int) -> list[dict[str, Any]]:
        data = await self.get(f"{year}.json", {"limit": 100}, ttl=3600)
        return data["MRData"]["RaceTable"]["Races"]

    async def qualifying_results(
        self,
        year: int,
        round_number: int,
    ) -> list[dict[str, Any]]:
        data = await self.get(
            f"{year}/{round_number}/qualifying.json",
            {"limit": 100},
            ttl=300,
        )
        races = data["MRData"]["RaceTable"].get("Races", [])
        if not races:
            return []
        return races[0].get("QualifyingResults", [])

    async def season_results(self, year: int) -> list[dict[str, Any]]:
        first = await self.get(
            f"{year}/results.json",
            {"limit": 100, "offset": 0},
            ttl=3600,
        )
        total = int(first["MRData"]["total"])
        page_size = int(first["MRData"]["limit"])
        remaining = await asyncio.gather(
            *(
                self.get(
                    f"{year}/results.json",
                    {"limit": page_size, "offset": offset},
                    ttl=3600,
                )
                for offset in range(page_size, total, page_size)
            )
        )
        rows = [
            race
            for page in [first, *remaining]
            for race in page["MRData"]["RaceTable"]["Races"]
        ]
        merged: dict[str, dict[str, Any]] = {}
        for race in rows:
            target = merged.setdefault(
                race["round"], {**race, "Results": []}
            )
            target["Results"].extend(race.get("Results", []))
        return sorted(
            merged.values(),
            key=lambda race: int(race["round"]),
        )
