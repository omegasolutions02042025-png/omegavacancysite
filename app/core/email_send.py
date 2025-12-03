import re
import mimetypes
from typing import Optional, List
from email.message import EmailMessage
import aiosmtplib
import html as _html
import logging

# --- базовая настройка логгера (при желании перенеси в main) ---
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG / INFO / WARNING
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
# ---------------------------------------------------------------


def _looks_like_html(s: str) -> bool:
    """
    Проверить, выглядит ли строка как HTML.
    
    Args:
        s: Строка для проверки
        
    Returns:
        bool: True если строка содержит HTML теги
    """
    return bool(re.search(r'</?[a-z][\s\S]*?>', s or '', re.I))


def _plain_to_html_preserve_breaks(text: str) -> str:
    """
    Преобразовать обычный текст в HTML с сохранением переносов строк.
    
    Args:
        text: Обычный текст
        
    Returns:
        str: HTML строка с экранированными символами и сохраненными переносами
    """
    if text is None:
        text = ""
    esc = _html.escape(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")
    return f"<!doctype html><html><body>{esc}</body></html>"


def _html_to_plain_fallback(html: str) -> str:
    """
    Преобразовать HTML в обычный текст для plain-text версии письма.
    
    Удаляет HTML теги, конвертирует ссылки в формат "текст (url)".
    
    Args:
        html: HTML строка
        
    Returns:
        str: Обычный текст или "(пустое письмо)" если HTML пустой
    """
    if not html:
        return "(пустое письмо)"
    text = re.sub(r'(?i)</(p|div|h[1-6]|li|br)\s*>', '\n', html)
    text = re.sub(r'(?i)<li\s*>', '• ', text)
    text = re.sub(
        r'(?is)<a[^>]*href=[\"\\\']([^\"\\\']+)[\"\\\'][^>]*>(.*?)</a>',
        lambda m: f"{m.group(2)} ({m.group(1)})",
        text
    )
    text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', '', text)
    text = re.sub(r'(?is)<[^>]+>', '', text)
    text = _html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text).strip()
    return text or "(пустое письмо)"


def sanitize_header(value: Optional[str]) -> str:
    """
    Очистить заголовок email от недопустимых символов.
    
    Удаляет переносы строк и лишние пробелы.
    
    Args:
        value: Значение заголовка
        
    Returns:
        str: Очищенное значение или пустая строка
    """
    if not value:
        return ""
    value = re.sub(r'[\r\n\t]+', ' ', value)
    value = re.sub(r'\s{2,}', ' ', value).strip()
    return value


async def send_email_smtp(
    sender_email: str,
    recipient_email: str,
    subject: str,
    body: str,
    *,
    html: bool = False,
    attachments: Optional[List[str]] = None,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    use_tls: bool = True,
    use_starttls: bool = False,
) -> bool:
    """
    Универсальная отправка письма через любой SMTP-сервер с логами.
    
    Поддерживает HTML и plain-text письма, вложения, автоматически определяет HTML.
    Создает multipart письмо с альтернативными версиями (HTML и plain-text).
    
    Args:
        sender_email: Email отправителя
        recipient_email: Email получателя
        subject: Тема письма
        body: Тело письма (может быть HTML или plain-text)
        html: Принудительно использовать HTML (если False, определяется автоматически)
        attachments: Список путей к файлам для вложения
        smtp_host: Хост SMTP сервера
        smtp_port: Порт SMTP сервера
        smtp_username: Имя пользователя для SMTP
        smtp_password: Пароль для SMTP
        use_tls: Использовать TLS (для порта 465)
        use_starttls: Использовать STARTTLS (для порта 587)
        
    Returns:
        bool: True если письмо успешно отправлено, False в случае ошибки
    """

    # --- входные параметры (без пароля) ---
    logger.debug(
        "send_email_smtp: from=%s, to=%s, subject=%s",
        sender_email,
        recipient_email,
        subject,
    )
    logger.debug(
        "send_email_smtp SMTP: host=%s, port=%s, username=%s, use_tls=%s, use_starttls=%s",
        smtp_host,
        smtp_port,
        smtp_username,
        use_tls,
        use_starttls,
    )
    logger.debug("send_email_smtp: html_flag=%s, body_len=%s, attachments=%s",
                 html, len(body or ""), len(attachments or []))

    msg = EmailMessage()
    msg['From'] = sanitize_header(sender_email)
    msg['To'] = sanitize_header(recipient_email)
    msg['Subject'] = sanitize_header(subject)

    is_html = _looks_like_html(body)
    use_html = html or is_html
    logger.debug("send_email_smtp: is_html_detected=%s, use_html=%s", is_html, use_html)

    # Формирование тела
    if use_html:
        plain_part = _html_to_plain_fallback(body) if is_html else (body or "(пустое письмо)")
        msg.set_content(plain_part, charset='utf-8')

        html_part = body if is_html else _plain_to_html_preserve_breaks(body or "")
        msg.add_alternative(html_part or "(пустое письмо)", subtype='html', charset='utf-8')
    else:
        msg.set_content(body or "(пустое письмо)", charset='utf-8')

    # Вложения
    if attachments:
        for file_path in attachments:
            logger.debug("send_email_smtp: attach file %s", file_path)
            ctype, encoding = mimetypes.guess_type(file_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(file_path, 'rb') as f:
                msg.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=file_path.split('/')[-1],
                )

    # Можно раскомментировать для отладки структуры письма (ОСТОРОЖНО в проде)
    # logger.debug("send_email_smtp: full message:\n%s", msg.as_string())

    try:
        logger.debug("send_email_smtp: sending via aiosmtplib...")
        if use_starttls:
            resp = await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                start_tls=True,
            )
        else:
            resp = await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                use_tls=use_tls,
            )

        logger.info("send_email_smtp: raw SMTP response: %r", resp)

        # Разбор ответа
        success = False
        code = None
        msg_part = None

        if isinstance(resp, tuple):
            code_part = resp[0] if len(resp) > 0 else None
            msg_part = resp[1] if len(resp) > 1 else None

            if isinstance(code_part, int):
                code = code_part
            elif isinstance(code_part, (bytes, str)):
                s = code_part.decode() if isinstance(code_part, bytes) else code_part
                m = re.search(r'\b(\d{3})\b', s)
                if m:
                    code = int(m.group(1))

            if code is None and isinstance(msg_part, (bytes, str)):
                s = msg_part.decode() if isinstance(msg_part, bytes) else str(msg_part)
                m = re.search(r'\b(\d{3})\b', s)
                if m:
                    code = int(m.group(1))

            if code is not None:
                success = 200 <= code < 300
            else:
                s = '' if msg_part is None else (msg_part.decode() if isinstance(msg_part, bytes) else str(msg_part))
                u = s.upper()
                success = u.startswith('2') or ' 2.0.0 ' in u or ' OK ' in u or u.startswith('OK') \
                          or 'ACCEPTED FOR DELIVERY' in u
        else:
            # Попытка взять code как атрибут
            code_attr = getattr(resp, 'code', None)
            if code_attr is not None:
                try:
                    code = int(code_attr)
                    success = 200 <= code < 300
                except Exception:
                    success = False
            else:
                # Фолбэк — если провайдер вернул что-то странное, считаем успехом,
                # но логируем.
                logger.warning("send_email_smtp: unknown resp type %r, treating as success=True", type(resp))
                success = True

        logger.info("send_email_smtp: parsed result success=%s, code=%s", success, code)

        return success

    except Exception as e:
        logger.exception("send_email_smtp: exception while sending email")
        return False


# Пример вызова
# import asyncio
# asyncio.run(send_email_smtp(
#     sender_email='zakaz@omega-solutions.ru',
#     recipient_email='artursimoncik@gmail.com',
#     subject='test',
#     body='test',
#     html=True,
#     smtp_host='mailbe07.hoster.by',
#     smtp_port=465,
#     smtp_username='zakaz@omega-solutions.ru',
#     smtp_password='Zakazomega2025!',
#     use_tls=True,
#     use_starttls=False,
# ))

