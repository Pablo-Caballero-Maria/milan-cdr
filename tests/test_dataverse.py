import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from milan_cdr.dataverse import DataFile, DataverseClient, parse_file_listing, select_days

CONTENT = b"1\t1385938800000\t39\t0.1\t\t\t\t\n"


def _listing() -> dict:
    files = [
        {"dataFile": {"id": 10 + i, "filename": f"sms-call-internet-mi-2013-12-0{i}.txt", "filesize": len(CONTENT)}}
        for i in range(1, 10)
    ]
    files.append({"dataFile": {"id": 99, "filename": "README.pdf", "filesize": 1}})
    return {"data": {"latestVersion": {"files": files}}}


def _transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.startswith("/api/datasets/"):
            return httpx.Response(200, json=_listing())
        if request.method == "POST":
            file_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"data": {"signedUrl": f"https://dv.test/signed/{file_id}"}})
        if request.url.path.startswith("/signed/"):
            return httpx.Response(200, content=CONTENT)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def client_and_requests():
    seen: list[httpx.Request] = []
    http = httpx.Client(base_url="https://dv.test", transport=_transport(seen))
    return DataverseClient(email="alumno@example.org", client=http), seen


def test_parse_listing_ignores_non_daily_files():
    files = parse_file_listing(_listing())
    assert len(files) == 9
    assert files[0] == DataFile(11, "sms-call-internet-mi-2013-12-01.txt", len(CONTENT), date(2013, 12, 1))


def test_select_days():
    files = parse_file_listing(_listing())
    selected = select_days(files, [date(2013, 12, 2), date(2013, 12, 3)])
    assert [f.file_id for f in selected] == [12, 13]
    with pytest.raises(LookupError):
        select_days(files, [date(2014, 1, 5)])


def test_download_sends_guestbook_and_writes_file(tmp_path: Path, client_and_requests):
    client, seen = client_and_requests
    data_file = client.list_files()[1]
    path = client.download(data_file, tmp_path)
    assert path.read_bytes() == CONTENT
    post = next(r for r in seen if r.method == "POST")
    assert json.loads(post.content) == {"guestbookResponse": {"email": "alumno@example.org"}}
    assert not list(tmp_path.glob("*.part"))


def test_download_skips_existing(tmp_path: Path, client_and_requests):
    client, seen = client_and_requests
    data_file = client.list_files()[0]
    (tmp_path / data_file.filename).write_bytes(CONTENT)
    seen.clear()
    client.download(data_file, tmp_path)
    assert seen == []


def test_download_detects_truncated_file(tmp_path: Path, client_and_requests):
    client, _ = client_and_requests
    good = client.list_files()[0]
    wrong = DataFile(good.file_id, good.filename, good.size + 1, good.day)
    with pytest.raises(OSError, match="tamaño"):
        client.download(wrong, tmp_path)
    assert not (tmp_path / good.filename).exists()
