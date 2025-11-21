import re
import mimetypes
from typing import Optional, List
from email.message import EmailMessage
import aiosmtplib
import html as _html

def _looks_like_html(s: str) -> bool:
    return bool(re.search(r'</?[a-z][\s\S]*?>', s or '', re.I))

def _plain_to_html_preserve_breaks(text: str) -> str:
    """Преобразует обычный текст в HTML, сохранив переносы строк."""
    if text is None:
        text = ""
    # Экраним HTML-символы и превращаем \n в <br>
    esc = _html.escape(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")
    return f"<!doctype html><html><body>{esc}</body></html>"

def _html_to_plain_fallback(html: str) -> str:
    """Делаем читаемый plain из HTML, сохраняя переносы."""
    if not html:
        return "(пустое письмо)"
    text = re.sub(r'(?i)</(p|div|h[1-6]|li|br)\s*>', '\n', html)
    text = re.sub(r'(?i)<li\s*>', '• ', text)
    text = re.sub(r'(?is)<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                  lambda m: f"{m.group(2)} ({m.group(1)})", text)
    text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', '', text)
    text = re.sub(r'(?is)<[^>]+>', '', text)
    text = _html.unescape(text)
    # ВАЖНО: не схлопывать одиночные \n
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text).strip()
    return text or "(пустое письмо)"

def sanitize_header(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r'[\r\n\t]+', ' ', value)
    value = re.sub(r'\s{2,}', ' ', value).strip()
    return value

async def send_email_gmail(
    sender_email: str,
    app_password: str,
    recipient_email: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: Optional[List[str]] = None
) -> bool:
    msg = EmailMessage()
    msg['From'] = sanitize_header(sender_email)
    msg['To'] = sanitize_header(recipient_email)
    msg['Subject'] = sanitize_header(subject)

    is_html = _looks_like_html(body)
    use_html = html or is_html

    if use_html:
        # Plain-часть: если тело изначально HTML — делаем читабельный фоллбэк,
        # если тело было plain — кладём его как есть (переносы сохранятся).
        plain_part = _html_to_plain_fallback(body) if is_html else (body or "(пустое письмо)")
        msg.set_content(plain_part, charset='utf-8')

        # HTML-часть: если body был plain — конвертируем \n в <br>, иначе берём как есть
        html_part = body if is_html else _plain_to_html_preserve_breaks(body or "")
        msg.add_alternative(html_part or "(пустое письмо)", subtype='html', charset='utf-8')
    else:
        # Обычное текстовое письмо — переносы сохранятся
        msg.set_content(body or "(пустое письмо)", charset='utf-8')

    # Вложения
    if attachments:
        for file_path in attachments:
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

    try:
        resp = await aiosmtplib.send(
            msg,
            hostname='smtp.gmail.com',
            port=465,
            username=sender_email,
            password=app_password,
            use_tls=True
        )
        print("Ответ SMTP:", resp)

        # Устойчивая проверка успеха
        if isinstance(resp, tuple):
            code_part = resp[0] if len(resp) > 0 else None
            msg_part = resp[1] if len(resp) > 1 else None

            code = None
            if isinstance(code_part, int):
                code = code_part
            elif isinstance(code_part, (bytes, str)):
                s = code_part.decode() if isinstance(code_part, bytes) else code_part
                m = re.search(r'\b(\d{3})\b', s)
                if m: code = int(m.group(1))
            if code is None and isinstance(msg_part, (bytes, str)):
                s = msg_part.decode() if isinstance(msg_part, bytes) else msg_part
                m = re.search(r'\b(\d{3})\b', s)
                if m: code = int(m.group(1))

            if code is not None:
                return 200 <= code < 300

            s = '' if msg_part is None else (msg_part.decode() if isinstance(msg_part, bytes) else str(msg_part))
            u = s.upper()
            return u.startswith('2') or ' 2.0.0 ' in u or ' OK ' in u or u.startswith('OK')

        code_attr = getattr(resp, 'code', None)
        if code_attr is not None:
            try:
                return 200 <= int(code_attr) < 300
            except Exception:
                pass

        return True

    except Exception as e:
        print(f"Ошибка при отправке письма: {e}")
        return False
