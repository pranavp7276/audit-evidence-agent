"""The evidence pack and its downloads, and scoring a run against an answer key."""

import io
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from agent.services.pack import build_pack
from agent.web.common import _PACK_FILES, GAP_KEYS, _completed

router = APIRouter()


def _pack(run_id: UUID) -> Path:
    _completed(run_id)
    return Path(build_pack(run_id))


@router.get("/api/runs/{run_id}/index")
def pack_index(run_id: UUID) -> dict:
    return {"markdown": (_pack(run_id) / "index.md").read_text(encoding="utf-8")}


@router.get("/api/runs/{run_id}/files/{name}")
def pack_file(run_id: UUID, name: str) -> FileResponse:
    if name not in _PACK_FILES:
        raise HTTPException(404)
    return FileResponse(_pack(run_id) / name, media_type=_PACK_FILES[name], filename=f"{name.rsplit('.', 1)[0]}_{str(run_id)[:8]}.{name.rsplit('.', 1)[1]}")


@router.get("/api/runs/{run_id}/pack.zip")
def pack_zip(run_id: UUID) -> Response:
    folder = _pack(run_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="evidence_pack_{run_id}.zip"'})


@router.post("/api/runs/{run_id}/score")
async def score_run(run_id: UUID, key_name: str = Form(""), account_col: str = Form("account_id"),
                    check_col: str = Form("question_ref"), file: UploadFile | None = File(None)) -> JSONResponse:
    from eval.score import load_gap_key, load_reported, score

    _completed(run_id)
    if file is not None and file.filename:
        path = Path(tempfile.mkdtemp(prefix="gapkey-")) / "key.csv"
        path.write_bytes(await file.read())
    elif key_name:
        path = GAP_KEYS / Path(key_name).name
        if not path.is_file():
            raise HTTPException(404, "Unknown gap key")
    else:
        raise HTTPException(400, "Choose a gap key or upload one.")
    try:
        truth = load_gap_key(path, account_col, check_col, None, "gap")
    except SystemExit as exc:
        raise HTTPException(400, str(exc))
    reported, unsupported = load_reported(str(run_id), "question_ref")
    s = score(truth, reported, unsupported)
    return JSONResponse({**asdict(s), "passes": s.passes})


