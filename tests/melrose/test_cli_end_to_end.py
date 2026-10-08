"""The real composition behind the CLI, with the site replaced by recorded responses and the archived PDFs."""

from __future__ import annotations

import io
import json
import shutil
from functools import partial
from pathlib import Path

import httpx
from support import ALL_LOGS, FIXTURES, REPO, archived, archived_pdf

from cities.melrose import composition
from cities.melrose.adapters.inbound import cli
from cities.melrose.settings import load_settings

LISTING = json.loads((FIXTURES / "media_listing.json").read_text())
PDF_BY_URL = {archived(m).log.source_url: archived_pdf(m) for m in ALL_LOGS}


def site(refuse: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if refuse:
            return httpx.Response(403)
        if request.url.path.endswith("/wp-json/wp/v2/media"):
            return httpx.Response(200, json=LISTING, headers={"X-WP-TotalPages": "1"})
        return httpx.Response(200, content=PDF_BY_URL[str(request.url)])

    return httpx.MockTransport(handler)


def run(tmp_path: Path, *argv: str, transport: httpx.BaseTransport | None = None) -> tuple[int, str]:
    reference = tmp_path / "melrose" / "reference"
    if not reference.exists():
        shutil.copytree(REPO / "data" / "melrose" / "reference", reference)
    settings = load_settings({"CITIES_DATA_DIR": str(tmp_path)})
    use_cases = cli.UseCases(
        collect=partial(composition.collect_logs, settings, transport, pause=False),
        rebuild=partial(composition.rebuild_from_archive, settings),
        fetch_reference=partial(composition.fetch_reference, settings, transport),
        sample=partial(composition.sample_placements, settings),
    )
    out = io.StringIO()
    return cli.run(argv, use_cases, out), out.getvalue()


def test_collect_then_collect_again_then_rebuild(tmp_path: Path) -> None:
    code, out = run(tmp_path, "collect", transport=site())
    assert code == cli.EXIT_OK, out
    assert "Documents: 11   new entries: 1959" in out
    assert "442380 out_of_scope" in out
    assert len(list((tmp_path / "melrose" / "raw").glob("*.json"))) == 11

    code, out = run(tmp_path, "collect", transport=site())
    assert (code, out.splitlines()[0]) == (cli.EXIT_OK, "No new logs; nothing written.")

    code, out = run(tmp_path, "rebuild")
    assert code == cli.EXIT_OK, out
    assert "new entries: 0" in out
    assert "Stops placed: 331 of 332" in out
    assert "Boundary streets (rule 5)" in out

    code, out = run(tmp_path, "sample", "--n", "3", "--seed", "7", "--type", "MOTOR VEHICLE STOP")
    assert code == cli.EXIT_OK, out
    assert out.startswith("3 placed entries, seed 7")
    assert out.count("https://www.openstreetmap.org/?mlat=") == 3


def test_a_refused_request_exits_2_and_writes_nothing(tmp_path: Path) -> None:
    code, out = run(tmp_path, "collect", transport=site(refuse=True))
    assert code == cli.EXIT_NETWORK
    assert "403" in out
    assert not (tmp_path / "melrose" / "raw").exists()


def test_a_quarantined_log_exits_1(tmp_path: Path) -> None:
    broken = archived(ALL_LOGS[-1]).log
    pdfs = PDF_BY_URL | {broken.source_url: b"%PDF-1.4 truncated"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wp-json/wp/v2/media"):
            return httpx.Response(200, json=LISTING, headers={"X-WP-TotalPages": "1"})
        return httpx.Response(200, content=pdfs[str(request.url)])

    code, out = run(tmp_path, "collect", transport=httpx.MockTransport(handler))
    assert code == cli.EXIT_QUARANTINED
    assert f"QUARANTINED {broken.media_id}: unreadable" in out
