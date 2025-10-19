from fastapi import APIRouter, Depends, Request
from ...api.dependencies import authorize
from ...utils.responses import success_response
from ...utils.metrics import Metrics
from ...config import settings

router = APIRouter(prefix="", tags=["Metrics"], dependencies=[Depends(authorize)])

@router.get("/metrics")
def get_metrics(request: Request):
    """
    Return internal metrics (counters and summaries).
    """
    if not settings.metrics_enabled:
        return success_response(request, {"enabled": False, "message": "Metrics disabled"})
    data = Metrics.snapshot_all()
    return success_response(request, data)