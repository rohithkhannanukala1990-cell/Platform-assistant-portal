"""In-app notifications API."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, get_current_user
from ..database import list_notifications, mark_notification_read
from ..services.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamp_page

router = APIRouter(tags=["notifications"])


@router.get("/api/notifications")
def fetch_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
):
    _, size, offset = clamp_page(page, page_size)
    return list_notifications(limit=size, offset=offset)


@router.put("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int, current_user: User = Depends(get_current_user)):
    result = mark_notification_read(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result
