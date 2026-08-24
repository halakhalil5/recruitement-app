"""The one object you talk to: `DriveClient`.

    drive.list_files(folder_id)   -> list[DriveFile]
    drive.latest(folder_id)       -> DriveFile | None   (most recently modified)
    drive.fetch_bytes(file_id)    -> bytes
    drive.fetch_text(file)        -> str   (works for pdf/docx/xlsx and Google Docs)

Read-only on purpose: this app only ever reads resumes and job descriptions
from Drive, never writes to it. `latest()` is also how this app handles a JD
being edited or a new resume being dropped in mid-demo - just re-list, the
newest file wins, no special-casing needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from markitdown import MarkItDown

from .auth import get_credentials


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str


class DriveClient:
    def __init__(self, credentials=None) -> None:
        self._service = build("drive", "v3", credentials=credentials or get_credentials())
        self._converter = MarkItDown()

    def list_files(self, folder_id: str) -> list[DriveFile]:
        """Every file directly inside a Drive folder, newest-modified first."""
        files: list[DriveFile] = []
        page_token = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                    orderBy="modifiedTime desc",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(
                DriveFile(f["id"], f["name"], f["mimeType"], f["modifiedTime"])
                for f in response.get("files", [])
            )
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files

    def latest(self, folder_id: str) -> DriveFile | None:
        """The most recently modified file in a folder, e.g. the current JD."""
        files = self.list_files(folder_id)
        return files[0] if files else None

    def fetch_bytes(self, file_id: str) -> bytes:
        """A file's raw bytes, nothing saved to disk."""
        request = self._service.files().get_media(fileId=file_id)
        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def fetch_text(self, file: DriveFile) -> str:
        """A file's content as text, whatever format it started in."""
        if file.mime_type.startswith("application/vnd.google-apps"):
            # Google Docs/Sheets/Slides have no raw bytes to download; export instead.
            request = self._service.files().export_media(fileId=file.id, mimeType="text/plain")
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue().decode("utf-8", errors="ignore")

        raw = self.fetch_bytes(file.id)
        ext = "." + file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ".txt"
        text = self._converter.convert_stream(BytesIO(raw), file_extension=ext).text_content
        if len(raw) > 2000 and len(text.strip()) < 20:
            # a real, non-trivial file that converted to almost nothing is a red flag,
            # not a valid empty document - most often a scanned/image-only PDF (no OCR
            # in this pipeline) or a corrupted file. Fail loudly here instead of letting
            # near-empty text silently reach extract_candidate/extract_job_description.
            raise ValueError(
                f"{file.name} converted to almost no text ({len(text.strip())} chars from "
                f"{len(raw)} bytes). It's likely a scanned image PDF or a corrupted file - "
                "re-export it as a text-based PDF/DOCX and re-upload."
            )
        return text
