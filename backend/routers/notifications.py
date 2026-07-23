"""In-app notifications API."""

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..database import get_all_notifications, mark_notification_read

router = APIRouter(tags=["notifications"])


@router.get("/api/notifications")
def fetch_notifications(current_user: User = Depends(get_current_user)):
    return get_all_notifications()


@router.put("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int, current_user: User = Depends(get_current_user)):
    result = mark_notification_read(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result
