import httpx
import pytest

from app.jolpica import JolpicaClient


@pytest.mark.asyncio
async def test_circuit_results_keeps_first_page_when_later_page_fails():
    client = JolpicaClient.__new__(JolpicaClient)

    async def fake_get(path, params=None, ttl=0):
        assert path == "circuits/monza/results.json"
        offset = params["offset"]
        if offset:
            raise httpx.ReadTimeout("timeout")
        return {
            "MRData": {
                "total": "1001",
                "limit": "1000",
                "RaceTable": {
                    "Races": [
                        {
                            "season": "2024",
                            "round": "16",
                            "raceName": "Italian Grand Prix",
                            "Results": [{"position": "1"}],
                        }
                    ]
                },
            }
        }

    client.get = fake_get

    rows = await client.circuit_results("monza")

    assert rows == [
        {
            "season": "2024",
            "round": "16",
            "raceName": "Italian Grand Prix",
            "Results": [{"position": "1"}],
        }
    ]
