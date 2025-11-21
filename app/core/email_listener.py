# app/core/email_listener.py

import asyncio
import imaplib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from urllib.parse import quote
from typing import Dict, List

from app.database.user_db import UserRepository
from app.core.websocket_notif import ws_manager


class EmailListener:
    """
    Слушатель почты для нескольких пользователей.

    — Берёт из БД всех пользователей с настроенной рабочей почтой (work_email + work_email_app_pass).
    — Для каждого user_id запускает отдельный асинхронный watcher.
    — Watcher раз в poll_interval секунд:
        * логинится в IMAP (Gmail),
        * читает UNSEEN-письма в INBOX,
        * берёт только TOP_LIMIT самых новых,
        * находит кандидата по from через find_candidate_by_email(user_id, email),
        * пишет уведомление в БД и шлёт его по WebSocket.
    """

    def __init__(self, poll_interval: int = 10, top_limit: int = 5):
        self.user_repo = UserRepository()
        self.imap_host = "imap.gmail.com"
        self.imap_port = 993

        self.poll_interval = poll_interval
        self.top_limit = top_limit

        # user_id -> asyncio.Task watcher'а
        self._tasks: Dict[int, asyncio.Task] = {}

        # флаг глобальной остановки
        self._stopping = False

        # лок для безопасного старта/рестарта
        self._lock = asyncio.Lock()

    # ================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==================

    @staticmethod
    def _decode_mime_words(s: str) -> str:
        """Декодирование MIME-заголовков (Subject и т.п.)."""
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
        """
        Возвращает чистый email отправителя из From.
        'Имя <user@example.com>' -> 'user@example.com'
        """
        raw_from = msg.get("From", "") or ""
        _name, addr = parseaddr(raw_from)
        return addr.strip().lower()

    @staticmethod
    def _extract_text_from_message(msg: Message) -> str:
        """Достаём текстовое содержимое письма (text/plain без вложений)."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                        return body
                    except Exception:
                        continue
            return ""
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
                return body
            except Exception:
                return ""

    @staticmethod
    def _build_work_email_link(email_addr: str) -> str:
        """
        Строим ссылку на веб-почту рабочего ящика.
        Для Gmail — откроет интерфейс Gmail для этого пользователя.
        """
        email_addr = (email_addr or "").strip()
        if not email_addr:
            return ""
        # authuser подставляем как email — Gmail сам разрулит актуальный аккаунт
        return f"https://mail.google.com/mail/?authuser={quote(email_addr)}"

    # ================== СИНХРОННАЯ ЧАСТЬ: ЧТЕНИЕ IMAP ==================

    def _fetch_unseen_messages_for_user(
        self,
        email_addr: str,
        app_pass: str,
    ) -> List[dict]:
        """
        Синхронный проход по INBOX конкретного ящика:
        — логинимся по email_addr + app_pass,
        — ищем UNSEEN,
        — берём только TOP_LIMIT самых новых,
        — для каждого письма вытаскиваем from / subject / snippet,
        — помечаем письмо как Seen,
        — возвращаем list[dict].
        """
        messages: List[dict] = []
        mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)

        try:
            mail.login(email_addr, app_pass)
            mail.select("INBOX")

            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                return messages

            email_ids = data[0].split()
            if not email_ids:
                return messages

            # Берём только top_limit самых новых
            if self.top_limit > 0 and len(email_ids) > self.top_limit:
                top_ids = email_ids[-self.top_limit:]
            else:
                top_ids = email_ids

            # Идём от самого нового к более старым
            for email_id in reversed(top_ids):
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                msg: Message = email.message_from_bytes(msg_data[0][1])
                from_addr = self._get_sender_email(msg)
                subject = self._decode_mime_words(msg.get("Subject", ""))
                body = self._extract_text_from_message(msg)

                snippet = (body or "").strip().replace("\r", " ").replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."

                messages.append(
                    {
                        "from_addr": from_addr,
                        "subject": subject,
                        "snippet": snippet,
                    }
                )

                # Помечаем прочитанным, чтобы второй раз не ловить
                try:
                    mail.store(email_id, "+FLAGS", "\\Seen")
                except Exception:
                    pass

            return messages

        except Exception:
            return messages

        finally:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

    # ================== ASYNC-ЧАСТЬ: WATCHER ДЛЯ ОДНОГО USER_ID ==================

    async def _watch_mailbox(self, user_id: int, email_addr: str, app_pass: str):
        """
        Асинхронный watcher конкретного рекрутёра:
        — каждые poll_interval секунд забирает UNSEEN через to_thread,
        — находит кандидата по from через find_candidate_by_email(user_id, email),
        — создаёт уведомление в БД и шлёт его по WebSocket
          ТОЛЬКО если найден кандидат.
        """
        try:
            while not self._stopping:
                # 1. Забираем письма из IMAP в отдельном потоке
                messages = await asyncio.to_thread(
                    self._fetch_unseen_messages_for_user,
                    email_addr,
                    app_pass,
                )

                # 2. Для каждого письма — ищем кандидата и создаём уведомление
                for msg in messages:
                    from_addr = msg["from_addr"]
                    subject = msg["subject"]
                    snippet = msg["snippet"]

                    try:
                        candidate = await self.user_repo.find_candidate_by_email(
                            user_id=user_id,
                            email=from_addr,
                        )
                    except Exception:
                        candidate = None

                    # Если кандидат не найден — полностью игнорируем письмо
                    if not candidate:
                        continue

                    vacancy_id = candidate.vacancy_id or ""
                    candidate_fullname = candidate.candidate_fullname or ""
                    text_for_db = (
                        f"Новое письмо от {candidate_fullname} "
                        f"по вакансии {vacancy_id}"
                    )

                    # ссылка на рабочую почту рекрутёра (из БД, т.е. email_addr)
                    work_email_link = self._build_work_email_link(email_addr)

                    notification = {
                        "type": "email_message",
                        "vacancy_id": vacancy_id,
                        "candidate_fullname": candidate_fullname,
                        "message": text_for_db,
                        "from_email": from_addr,
                        "subject": subject,
                        "snippet": snippet,
                        # ссылка, которая уйдёт на фронт и подставится в уведомление
                        "url": work_email_link,
                    }

                    # единственный лог: совпала отслеживаемая почта
                    print(
                        f"[email_listener] matched candidate email={from_addr} "
                        f"user_id={user_id}, vacancy_id={vacancy_id}"
                    )

                    # 3. Пишем в user_notification (пока только текст)
                    try:
                        await self.user_repo.add_user_notification(user_id, text_for_db, work_email_link)
                    except Exception:
                        pass

                    # 4. Шлём WS на фронт
                    try:
                        await ws_manager.send_to_user(user_id, notification)
                    except Exception:
                        pass

                await asyncio.sleep(self.poll_interval)

        except asyncio.CancelledError:
            # тихо выходим
            pass

    # ================== ПУБЛИЧНЫЕ МЕТОДЫ: START/RESTART/STOP/SHUTDOWN ==================

    async def start_all(self):
        """
        Стартуем слушателей для всех пользователей с настроенной почтой.
        Вызывается один раз из FastAPI @startup.
        """
        async with self._lock:
            self._stopping = False

            users = await self.user_repo.get_users_with_work_email()

            for user in users:
                user_id = user.id
                email_addr = user.work_email
                app_pass = user.work_email_app_pass

                if user_id in self._tasks and not self._tasks[user_id].done():
                    continue

                task = asyncio.create_task(
                    self._watch_mailbox(user_id, email_addr, app_pass),
                    name=f"email-watch-{user_id}",
                )
                self._tasks[user_id] = task

    async def restart_for_user(self, user_id: int):
        """
        Перезапуск листенера для одного пользователя (если он сменил почту/пароль).
        """
        async with self._lock:
            old_task = self._tasks.pop(user_id, None)
            if old_task and not old_task.done():
                old_task.cancel()

            user = await self.user_repo.get_by_id(user_id)
            if not user or not user.work_email or not user.work_email_app_pass:
                return

            task = asyncio.create_task(
                self._watch_mailbox(user_id, user.work_email, user.work_email_app_pass),
                name=f"email-watch-{user_id}",
            )
            self._tasks[user_id] = task

    async def stop_for_user(self, user_id: int):
        async with self._lock:
            task = self._tasks.pop(user_id, None)
            if task and not task.done():
                task.cancel()

    async def shutdown(self):
        """
        Останавливаем всех слушателей (вызывается в @shutdown FastAPI).
        """
        self._stopping = True

        async with self._lock:
            items = list(self._tasks.items())
            for _, task in items:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*(t for _, t in items), return_exceptions=True)
            self._tasks.clear()


# Глобальный экземпляр
email_listener = EmailListener()
