# app/core/email_listener.py

import asyncio
import imaplib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from urllib.parse import quote
from typing import Dict, List, Tuple

from app.database.user_db import UserRepository
from app.core.websocket_notif import ws_manager


class EmailListener:
    def __init__(self, poll_interval: int = 10, top_limit: int = 5):
        self.user_repo = UserRepository()
        self.default_imap_host = "mailbe07.hoster.by"
        self.default_imap_port = 993

        self.poll_interval = poll_interval
        self.top_limit = top_limit
        self._tasks: Dict[int, asyncio.Task] = {}
        self._stopping = False
        self._lock = asyncio.Lock()

    # ================== HELPERS ==================

    @staticmethod
    def _decode_mime_words(s: str) -> str:
        if not s:
            return ""
        decoded_fragments = decode_header(s)
        fragments = []
        for fragment, encoding in decoded_fragments:
            if isinstance(fragment, bytes):
                try:
                    fragment = fragment.decode(encoding or "utf-8", errors="replace")
                except Exception:
                    fragment = fragment.decode("utf-8", errors="replace")
            fragments.append(fragment)
        return "".join(fragments)

    @staticmethod
    def _get_sender_email(msg: Message) -> str:
        raw_from = msg.get("From", "") or ""
        _name, addr = parseaddr(raw_from)
        return addr.strip().lower()

    @staticmethod
    def _extract_text_from_message(msg: Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        return part.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        continue
            return ""
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                return msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                return ""

    @staticmethod
    def _split_domain(addr: str) -> str:
        addr = (addr or "").strip().lower()
        if "@" not in addr:
            return ""
        return addr.split("@", 1)[1]

    def _resolve_imap_server(self, email_addr: str) -> Tuple[str, int]:
        domain = self._split_domain(email_addr)

        if domain in {"gmail.com", "googlemail.com"}:
            return "imap.gmail.com", 993

        if domain == "omega-solutions.ru":
            return "mailbe07.hoster.by", 993

        return self.default_imap_host, self.default_imap_port

    @staticmethod
    def _build_work_email_link(email_addr: str) -> str:
        if not email_addr:
            return ""

        domain = email_addr.split("@")[-1].lower()

        if domain in {"gmail.com", "googlemail.com"}:
            return f"https://mail.google.com/mail/?authuser={quote(email_addr)}"

        if domain == "omega-solutions.ru":
            return "https://mail.omega-solutions.ru/"

        return f"mailto:{quote(email_addr)}"

    # ================== IMAP SYNC FETCH ==================

    def _fetch_unseen_messages_for_user(self, email_addr: str, app_pass: str) -> List[dict]:
        messages: List[dict] = []

        host, port = self._resolve_imap_server(email_addr)

        try:
            mail = imaplib.IMAP4_SSL(host, port)
        except Exception:
            return messages

        try:
            mail.login(email_addr, app_pass)

            status, _ = mail.select("INBOX")
            if status != "OK":
                return messages

            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                return messages

            email_ids = data[0].split()
            if not email_ids:
                return messages

            if self.top_limit > 0 and len(email_ids) > self.top_limit:
                ids = email_ids[-self.top_limit:]
            else:
                ids = email_ids

            for email_id in reversed(ids):
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                try:
                    msg: Message = email.message_from_bytes(msg_data[0][1])
                    from_addr = self._get_sender_email(msg)
                    subject = self._decode_mime_words(msg.get("Subject", ""))
                    body = self._extract_text_from_message(msg)

                    snippet = (body or "").strip().replace("\r", " ").replace("\n", " ")
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."

                    messages.append(
                        {"from_addr": from_addr, "subject": subject, "snippet": snippet}
                    )

                    try:
                        mail.store(email_id, "+FLAGS", "\\Seen")
                    except Exception:
                        pass

                except Exception:
                    continue

            return messages

        except Exception:
            return messages

        finally:
            try: mail.close()
            except Exception: pass
            try: mail.logout()
            except Exception: pass

    # ================== WATCHER ==================

    async def _watch_mailbox(self, user_id: int, email_addr: str, app_pass: str):
        try:
            while not self._stopping:
                try:
                    messages = await asyncio.to_thread(
                        self._fetch_unseen_messages_for_user, email_addr, app_pass
                    )
                except Exception:
                    messages = []

                for msg in messages:
                    from_addr = msg["from_addr"]

                    try:
                        candidate = await self.user_repo.find_candidate_by_email(
                            user_id=user_id,
                            email=from_addr,
                        )
                    except Exception:
                        candidate = None

                    if not candidate:
                        continue

                    vacancy_id = candidate.vacancy_id or ""
                    candidate_fullname = candidate.candidate_fullname or ""
                    text_for_db = (
                        f"Новое письмо от {candidate_fullname} по вакансии {vacancy_id}"
                    )

                    work_email_link = self._build_work_email_link(email_addr)

                    notification = {
                        "type": "email_message",
                        "vacancy_id": vacancy_id,
                        "candidate_fullname": candidate_fullname,
                        "message": text_for_db,
                        "from_email": from_addr,
                        "subject": msg["subject"],
                        "snippet": msg["snippet"],
                        "url": work_email_link,
                    }

                    try:
                        await self.user_repo.add_user_notification(
                            user_id, text_for_db, work_email_link
                        )
                    except Exception:
                        pass

                    try:
                        await ws_manager.send_to_user(user_id, notification)
                    except Exception:
                        pass

                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            raise

    # ================== PUBLIC API ==================

    async def start_all(self):
        async with self._lock:
            self._stopping = False

            try:
                users = await self.user_repo.get_users_with_work_email()
            except Exception:
                return

            for user in users:
                if not user.work_email or not user.work_email_app_pass:
                    continue

                if user.id in self._tasks and not self._tasks[user.id].done():
                    continue

                task = asyncio.create_task(
                    self._watch_mailbox(user.id, user.work_email, user.work_email_app_pass)
                )
                self._tasks[user.id] = task

    async def restart_for_user(self, user_id: int):
        async with self._lock:
            old = self._tasks.pop(user_id, None)
            if old and not old.done():
                old.cancel()

            try:
                user = await self.user_repo.get_by_id(user_id)
            except Exception:
                return

            if not user or not user.work_email or not user.work_email_app_pass:
                return

            task = asyncio.create_task(
                self._watch_mailbox(user.id, user.work_email, user.work_email_app_pass)
            )
            self._tasks[user_id] = task

    async def stop_for_user(self, user_id: int):
        async with self._lock:
            task = self._tasks.pop(user_id, None)
            if task and not task.done():
                task.cancel()

    async def shutdown(self):
        self._stopping = True
        async with self._lock:
            items = list(self._tasks.items())
            for _, task in items:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*(t for _, t in items), return_exceptions=True)
            self._tasks.clear()


email_listener = EmailListener()
