# app/core/email_listener.py

import asyncio
import imaplib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from urllib.parse import quote
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime
import uuid
import os

from app.database.user_db import UserRepository
from app.database.chat_db import chat_repository
from app.database.vacancy_db import VacancyRepository
from app.database.candidate_db import CandidateRepository
from app.core.websocket_notif import ws_manager
from app.core.chat_websocket import chat_ws_manager

# Директория для хранения вложений из email
MEDIA_DIR = Path("media/email")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class EmailListener:
    def __init__(self, poll_interval: int = 10, top_limit: int = 5):
        self.user_repo = UserRepository()
        self.vacancy_repo = VacancyRepository()
        self.candidate_repo = CandidateRepository()
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
    def _clean_reply_text(text: str) -> str:
        """
        Очищает текст от цитат и служебной информации.
        Оставляет только новое сообщение до первой цитаты.
        """
        if not text:
            return ""
        
        lines = text.split('\n')
        clean_lines = []
        
        # Паттерны для определения начала цитаты
        quote_patterns = [
            'пт,',  # пт, 28 нояб. 2025 г.
            'чт,',  # чт, 27 нояб. 2025 г.
            'ср,',  # ср, 26 нояб. 2025 г.
            'вт,',  # вт, 25 нояб. 2025 г.
            'пн,',  # пн, 24 нояб. 2025 г.
            'сб,',  # сб, 23 нояб. 2025 г.
            'вс,',  # вс, 22 нояб. 2025 г.
            'on ',  # On Mon, Nov 28, 2025
            '----',  # Разделитель
            '___',   # Разделитель
            '> ',    # Цитирование с >
            'from:',  # From: sender
            'sent:',  # Sent: date
            'wrote:',  # User wrote:
            'написал',  # Пользователь написал
        ]
        
        for line in lines:
            line_lower = line.strip().lower()
            
            # Проверяем, является ли строка началом цитаты
            is_quote = False
            for pattern in quote_patterns:
                if line_lower.startswith(pattern):
                    is_quote = True
                    break
            
            # Если нашли цитату - останавливаемся
            if is_quote:
                break
            
            # Добавляем строку, если она не пустая или если уже есть текст
            if line.strip() or clean_lines:
                clean_lines.append(line)
        
        # Убираем пустые строки в конце
        while clean_lines and not clean_lines[-1].strip():
            clean_lines.pop()
        
        result = '\n'.join(clean_lines).strip()
        return result if result else text  # Если ничего не осталось, возвращаем оригинал

    @staticmethod
    def _extract_text_from_message(msg: Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        raw_text = part.get_payload(decode=True).decode(charset, errors="replace")
                        # ✅ Очищаем от цитат
                        return EmailListener._clean_reply_text(raw_text)
                    except Exception:
                        continue
            return ""
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                raw_text = msg.get_payload(decode=True).decode(charset, errors="replace")
                # ✅ Очищаем от цитат
                return EmailListener._clean_reply_text(raw_text)
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

    @staticmethod
    def _extract_attachments(msg: Message, candidate_name: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Извлекает вложения из email сообщения
        Возвращает: (has_media, media_type, media_path, media_filename)
        """
        has_media = False
        media_type = None
        media_path = None
        media_filename = None

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                
                # Проверяем, является ли это вложением
                if "attachment" in content_disposition or part.get_filename():
                    filename = part.get_filename()
                    
                    if filename:
                        # Декодируем имя файла
                        filename = EmailListener._decode_mime_words(filename)
                        
                        # Определяем тип медиа
                        content_type = part.get_content_type().lower()
                        
                        if content_type.startswith('image/'):
                            media_type = 'photo'
                        elif content_type.startswith('video/'):
                            media_type = 'video'
                        elif content_type.startswith('audio/'):
                            media_type = 'audio'
                        else:
                            media_type = 'document'
                        
                        # Генерируем уникальное имя файла
                        unique_id = uuid.uuid4().hex[:8]
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_candidate_name = candidate_name.replace(' ', '_').replace('/', '_')
                        
                        # Получаем расширение файла
                        file_ext = os.path.splitext(filename)[1]
                        new_filename = f"{safe_candidate_name}_{timestamp_str}_{unique_id}{file_ext}"
                        
                        # Сохраняем файл
                        file_path = MEDIA_DIR / new_filename
                        
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                with open(file_path, 'wb') as f:
                                    f.write(payload)
                                
                                has_media = True
                                media_path = f"/media/email/{new_filename}"
                                media_filename = filename
                                
                                print(f"[EMAIL] Сохранено вложение: {new_filename} ({media_type})")
                                break  # Берем только первое вложение
                        except Exception as e:
                            print(f"[EMAIL] Ошибка сохранения вложения: {e}")
                            continue
        
        return has_media, media_type, media_path, media_filename

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

                    messages.append({
                        "from_addr": from_addr,
                        "subject": subject,
                        "snippet": snippet,
                        "msg": msg  # Добавляем полное сообщение для извлечения вложений
                    })

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
                        "message_text": msg["snippet"] or msg["subject"],  # Добавляем текст сообщения
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

                    # Получаем название вакансии
                    vacancy_title = None
                    if vacancy_id:
                        vacancy = await self.vacancy_repo.get_vacancy_by_id(vacancy_id)
                        if vacancy:
                            vacancy_title = vacancy.title
                    
                    # Извлекаем вложения из email
                    has_media = False
                    media_type = None
                    media_path = None
                    media_filename = None
                    
                    if "msg" in msg:
                        try:
                            has_media, media_type, media_path, media_filename = await asyncio.to_thread(
                                self._extract_attachments,
                                msg["msg"],
                                candidate_fullname
                            )
                        except Exception as e:
                            print(f"[EMAIL_LISTENER] Ошибка извлечения вложений: {e}")
                    
                    # Формируем текст сообщения
                    message_text = msg["snippet"] or msg["subject"]
                    if has_media and not message_text:
                        message_text = f"[{media_type.upper()}] {media_filename}"
                    
                    # Получаем ID кандидата по его полному имени
                    candidate_id = None
                    if candidate_fullname:
                        candidate_id = await self.candidate_repo.get_candidate_id_by_fullname(
                            user_id=user_id,
                            candidate_fullname=candidate_fullname
                        )
                    
                    # Сохраняем сообщение в чат
                    saved_message = None
                    try:
                        saved_message = await chat_repository.add_message(
                            user_id=user_id,
                            candidate_id=candidate_id,
                            candidate_fullname=candidate_fullname,
                            vacancy_id=vacancy_id,
                            message_type="email",
                            sender="candidate",
                            message_text=message_text,
                            vacancy_title=vacancy_title,
                            has_media=has_media,
                            media_type=media_type,
                            media_path=media_path,
                            media_filename=media_filename,
                        )
                        print(f"[EMAIL_LISTENER] Сообщение сохранено в БД с ID: {saved_message.id}")
                        if has_media:
                            print(f"[EMAIL_LISTENER] С вложением: {media_filename} ({media_type})")
                    except Exception as e:
                        print(f"[EMAIL_LISTENER] Ошибка сохранения в чат: {e}")

                    # Отправляем уведомление через основной WebSocket
                    try:
                        await ws_manager.send_to_user(user_id, notification)
                    except Exception:
                        pass
                    
                    # Отправляем обновление в чат через WebSocket
                    if saved_message:
                        chat_update = {
                            "type": "new_message",
                            "message": {
                                "id": saved_message.id,
                                "sender": "candidate",
                                "message_text": message_text,
                                "timestamp": saved_message.timestamp,
                                "candidate_fullname": candidate_fullname,
                                "vacancy_id": vacancy_id,
                                "vacancy_title": vacancy_title,
                                "message_type": "email",
                                "has_media": has_media,
                                "media_type": media_type,
                                "media_path": media_path,
                                "media_filename": media_filename,
                            }
                        }
                        await chat_ws_manager.send_personal_message(chat_update, user_id)
                        print(f"[EMAIL_LISTENER] Отправлено обновление чата через WebSocket для user_id={user_id}")
                        if has_media:
                            print(f"[EMAIL_LISTENER] С медиа: {media_filename} ({media_type})")

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
