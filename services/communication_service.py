

import uuid
from fastapi import HTTPException, status
from datetime import datetime
from beanie import PydanticObjectId

from models.message import (
    Message, Announcement,
    MessageDirection, MessageStatus,
    AnnouncementStatus, AnnouncementPriority,
)
from models.notification import Notification, NotificationType, NotificationPriority
from repository.message_repository import (
    find_messages_for_tenant,
    find_thread,
    find_unread_for_user,
    count_unread_for_user,
    save_message,
    mark_message_read,
    mark_thread_read,
    delete_message,
    find_all_announcements,
    find_published_announcements,
    find_announcements_for_tenant,
    find_announcement_by_id,
    save_announcement,
    mark_announcement_read,
    delete_announcement,
)
from repository.notification_repository import create_notification


# ============================================================================
# MESSAGE SERVICE
# ============================================================================

class CommunicationService:

    # ── Sending messages ──────────────────────────────────────────────────

    async def send_message(
        self,
        sender_id:   str,
        receiver_id: str,
        tenant_id:   str,
        body:        str,
        direction:   MessageDirection,
        subject:     str | None = None,
        thread_id:   str | None = None,
    ) -> Message:
        """
        Send a message between tenant and management.
        If thread_id is None, starts a new conversation thread.
        """
        if not body.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message body cannot be empty.",
            )

        # Generate thread ID for new conversations
        if not thread_id:
            thread_id = str(uuid.uuid4())

        message = Message(
            sender_id   = PydanticObjectId(sender_id),
            receiver_id = PydanticObjectId(receiver_id),
            tenant_id   = PydanticObjectId(tenant_id),
            subject     = subject,
            body        = body.strip(),
            direction   = direction,
            thread_id   = thread_id,
        )
        saved = await save_message(message)

        # Notify the receiver. Wrapped so a notification failure never
        # bubbles up as a 500 *after* the message was already persisted —
        # which is what caused the "message saves but request returns 500"
        # behaviour the manager saw in the UI.
        try:
            notif_title = (
                "New message from "
                + ("Tenant" if direction == MessageDirection.TENANT_TO_MANAGEMENT else "Management")
            )
            preview = body.strip()
            preview = preview[:100] + ("..." if len(preview) > 100 else "")
            await create_notification(
                Notification(
                    recipient_id      = receiver_id,
                    sender_id         = sender_id,
                    notification_type = NotificationType.NEW_MESSAGE,
                    priority          = NotificationPriority.NORMAL,
                    title             = notif_title,
                    message           = preview,
                    reference_id      = str(saved.id),
                    reference_type    = "message",
                )
            )
        except Exception:
            # Best-effort: log silently. The message itself is already saved.
            import logging
            logging.getLogger(__name__).warning(
                "send_message: failed to create notification for receiver=%s",
                receiver_id,
                exc_info=True,
            )

        return saved

    # ── Reading messages ──────────────────────────────────────────────────

    async def get_tenant_inbox(self, tenant_id: str) -> list[Message]:
        """All messages for a tenant — both sent and received."""
        return await find_messages_for_tenant(tenant_id)

    async def get_thread(self, thread_id: str) -> list[Message]:
        """Full conversation thread ordered oldest → newest."""
        messages = await find_thread(thread_id)
        if not messages:
            raise HTTPException(404, "Thread not found.")
        return messages

    async def get_unread_messages(self, user_id: str) -> list[Message]:
        """Unread messages for a user."""
        return await find_unread_for_user(user_id)

    async def get_unread_count(self, user_id: str) -> int:
        """Unread message count for badge display."""
        return await count_unread_for_user(user_id)

    # ── Marking as read ───────────────────────────────────────────────────

    async def read_thread(self, thread_id: str, user_id: str) -> dict:
        """Mark all messages in a thread as read."""
        count = await mark_thread_read(thread_id, user_id)
        return {"marked_read": count}

    # ── Deleting ──────────────────────────────────────────────────────────

    async def delete_message(self, message_id: str) -> dict:
        """Delete a message by ID."""
        try:
            message = await Message.get(PydanticObjectId(message_id))
        except Exception:
            raise HTTPException(404, "Message not found.")
        await delete_message(message)
        return {"message": "Message deleted."}

    # ============================================================================
    # ANNOUNCEMENT SERVICE
    # ============================================================================

    async def create_announcement(
        self,
        author_id:         str,
        title:             str,
        body:              str,
        priority:          AnnouncementPriority = AnnouncementPriority.NORMAL,
        target_tenant_ids: list[str] | None = None,
        expires_at:        datetime | None = None,
        publish_now:       bool = False,
    ) -> Announcement:
        """
        Create a new announcement (draft or immediately published).
        If target_tenant_ids is empty → broadcast to all tenants.
        """
        announcement = Announcement(
            author_id          = PydanticObjectId(author_id),
            title              = title.strip(),
            body               = body.strip(),
            priority           = priority,
            target_tenant_ids  = [PydanticObjectId(tid) for tid in (target_tenant_ids or [])],
            expires_at         = expires_at,
            status             = AnnouncementStatus.PUBLISHED if publish_now else AnnouncementStatus.DRAFT,
            published_at       = datetime.utcnow() if publish_now else None,
        )
        return await save_announcement(announcement)

    async def publish_announcement(self, announcement_id: str) -> Announcement:
        """Publish a draft announcement."""
        announcement = await find_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(404, "Announcement not found.")
        if announcement.status == AnnouncementStatus.PUBLISHED:
            raise HTTPException(400, "Announcement is already published.")

        announcement.status       = AnnouncementStatus.PUBLISHED
        announcement.published_at = datetime.utcnow()
        announcement.updated_at   = datetime.utcnow()
        return await save_announcement(announcement)

    async def archive_announcement(self, announcement_id: str) -> Announcement:
        """Archive a published announcement."""
        announcement = await find_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(404, "Announcement not found.")

        announcement.status     = AnnouncementStatus.ARCHIVED
        announcement.updated_at = datetime.utcnow()
        return await save_announcement(announcement)

    async def get_all_announcements(self) -> list[Announcement]:
        """All announcements — for manager/admin view."""
        return await find_all_announcements()

    async def get_published_announcements(self) -> list[Announcement]:
        """Published announcements — for tenant view."""
        return await find_published_announcements()

    async def get_announcements_for_tenant(self, tenant_id: str) -> list[Announcement]:
        """Announcements relevant to a specific tenant."""
        return await find_announcements_for_tenant(tenant_id)

    async def mark_announcement_read(
        self, announcement_id: str, tenant_id: str
    ) -> Announcement:
        """Track that a tenant has read an announcement."""
        announcement = await find_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(404, "Announcement not found.")
        return await mark_announcement_read(announcement, tenant_id)

    async def delete_announcement(self, announcement_id: str) -> dict:
        """Delete an announcement."""
        announcement = await find_announcement_by_id(announcement_id)
        if not announcement:
            raise HTTPException(404, "Announcement not found.")
        await delete_announcement(announcement)
        return {"message": "Announcement deleted."}


# Singleton
communication_service = CommunicationService()