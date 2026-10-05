"""Worker endpoint invoked by Cloud Tasks (production only).

Defence in depth:
1. The worker Cloud Run service does not allow unauthenticated invocations;
   only the Cloud Tasks invoker service account holds ``roles/run.invoker``.
2. This handler additionally checks the OIDC token: full signature
   verification when the signature is present, otherwise (Cloud Run may strip
   the signature after validating it at the edge) the audience, issuer, expiry
   and service-account e-mail claims are checked.
Response codes drive Cloud Tasks redelivery: 2xx = done, 429/503/5xx = retry.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from google.auth.transport import requests as grequests
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from app.harness.resilience import LeaseHeldError, RetryableStepError
from app.logging_setup import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/internal")
_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class TaskBody(BaseModel):
    caseId: str = Field(pattern=r"^c[0-9a-f]{12}$")
    runId: str = Field(pattern=r"^[rq][0-9a-f]{12}$")  # r = analysis run, q = "ask the council" run
    stepId: str = Field(pattern=r"^[a-z]{3,16}(--[A-Za-z0-9_-]{1,64})?$")
    generation: int = Field(ge=1, le=10_000)


def _b64json(seg: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def _verify(request: Request) -> None:
    s = request.app.state.container.settings
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = auth[7:].strip()
    audience = s.worker_url.rstrip("/")
    parts = token.split(".")
    try:
        if len(parts) == 3 and parts[2]:
            claims = id_token.verify_oauth2_token(token, grequests.Request(), audience=audience)
        elif len(parts) >= 2 and os.environ.get("K_SERVICE"):
            # Signature already validated and stripped by Cloud Run's IAM front end.
            claims = _b64json(parts[1])
            if claims.get("aud") != audience or claims.get("iss") not in _ISSUERS or float(claims.get("exp", 0)) < time.time():
                raise ValueError("invalid claims")
        else:
            raise ValueError("unsigned token outside Cloud Run")
    except Exception as exc:  # noqa: BLE001
        log.warning("rejected task token: %s", exc)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid token") from exc
    if claims.get("email") != s.tasks_invoker_sa or not claims.get("email_verified", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caller not allowed")


@router.post("/tasks/execute")
async def execute(body: TaskBody, request: Request) -> Response:
    _verify(request)
    orch = request.app.state.container.orchestrator
    try:
        result = await orch.execute_step(body.caseId, body.runId, body.stepId, body.generation)
    except LeaseHeldError:
        return Response(status_code=status.HTTP_429_TOO_MANY_REQUESTS)  # another worker holds it; retry later
    except RetryableStepError:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)  # Cloud Tasks backs off and redelivers
    return Response(content=json.dumps({"result": result}), media_type="application/json")
