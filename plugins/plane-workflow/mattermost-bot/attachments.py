"""Stage Mattermost DM files for the existing Plane attachment workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import BotConfig
from mattermost import MattermostClient, MattermostError
from workflow_adapter import WorkflowAdapter, WorkflowAdapterError


class AttachmentService:
    def __init__(self, config: BotConfig, client: MattermostClient, workflow: WorkflowAdapter) -> None:
        self.config = config
        self.client = client
        self.workflow = workflow

    def preview(self, *, work_item_id: str, file_id: str, max_size_mb: int = 25) -> dict[str, Any]:
        if not 1 <= max_size_mb <= 100:
            raise WorkflowAdapterError("max_size_mb must be a whole number from 1 to 100.")
        try:
            info = self.client.file_info(file_id)
        except MattermostError as error:
            raise WorkflowAdapterError(str(error)) from error
        name = Path(str(info.get("name") or "attachment")).name
        size = int(info.get("size") or 0)
        if size > max_size_mb * 1024 * 1024:
            raise WorkflowAdapterError(f"The Mattermost attachment is larger than the {max_size_mb} MB limit.")
        return {
            "status": "preview",
            "work_item_id": work_item_id,
            "attachment": {"name": name, "size": size, "mime_type": info.get("mime_type")},
            "file_id": file_id,
            "message": "No file was uploaded to Plane. Confirm the draft to attach this Mattermost file.",
        }

    def upload(self, *, work_item_id: str, file_id: str, max_size_mb: int = 25) -> dict[str, Any]:
        preview = self.preview(work_item_id=work_item_id, file_id=file_id, max_size_mb=max_size_mb)
        attachment = preview["attachment"]
        target = self.config.attachment_dir / f"{file_id}-{attachment['name']}"
        try:
            target.write_bytes(self.client.download_file(file_id))
            result = self.workflow.execute_confirmed(
                "upload_work_item_attachment",
                {
                    "work_item_id": work_item_id,
                    "file_path": str(target),
                    "max_size_mb": max_size_mb,
                },
            )
        except (OSError, MattermostError, WorkflowAdapterError) as error:
            raise WorkflowAdapterError(str(error)) from error
        finally:
            target.unlink(missing_ok=True)
        return result

