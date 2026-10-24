import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header
from backend.config import settings

logger = logging.getLogger("radar.email")

def send_verification_email(to_email: str, code: str) -> bool:
    """
    Отправляет 6-значный код верификации на email через Яндекс SMTP (SSL: 465).
    """
    raw_user = settings.SMTP_USER.strip()
    smtp_pass = settings.SMTP_PASSWORD.strip()
    smtp_host = settings.SMTP_HOST.strip()
    smtp_port = settings.SMTP_PORT

    if not raw_user or not smtp_pass:
        logger.warning(f"[EMAIL DEV MODE] SMTP_USER не задан. Код для {to_email}: {code}")
        print(f"\n=======================================================")
        print(f" [DEV EMAIL OTP] Получатель: {to_email}")
        print(f" [DEV EMAIL OTP] Код подтверждения: {code}")
        print(f"=======================================================\n")
        return True

    # Для Яндекса логин для login() передается без @yandex.ru, а адрес в From - полный email
    username = raw_user.split("@")[0]
    email_addr = raw_user if "@" in raw_user else f"{raw_user}@yandex.ru"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"{code} — код для входа в Кассовый радар Центр-инвест", "utf-8")
    msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME, "utf-8")), email_addr))
    msg["To"] = to_email

    text_body = f"Здравствуйте!\n\nВаш код для входа в Кассовый радар Центр-инвест: {code}\nКод действителен 10 минут.\n\nЕсли вы не запрашивали код, проигнорируйте это сообщение."
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Код подтверждения</title>
    </head>
    <body style="margin: 0; padding: 24px; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
      <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #065f46 0%, #047857 100%); padding: 24px; text-align: center; color: #ffffff;">
          <h1 style="margin: 0; font-size: 20px; font-weight: 800; letter-spacing: -0.5px;">Центр-инвест</h1>
          <p style="margin: 4px 0 0 0; font-size: 12px; color: #a7f3d0; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">Кассовый радар для бизнеса</p>
        </div>

        <!-- Body -->
        <div style="padding: 32px 24px; text-align: center;">
          <h2 style="margin: 0 0 8px 0; font-size: 18px; color: #0f172a; font-weight: 800;">Вход в систему</h2>
          <p style="margin: 0 0 24px 0; font-size: 14px; color: #64748b; line-height: 1.5;">
            Используйте одноразовый код для подтверждения входа в аккаунт <b>{to_email}</b>:
          </p>

          <!-- OTP Badge -->
          <div style="display: inline-block; background: #f0fdf4; border: 2px dashed #059669; border-radius: 16px; padding: 14px 28px; margin-bottom: 20px;">
            <span style="font-size: 32px; font-weight: 900; letter-spacing: 6px; color: #065f46; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">
              {code}
            </span>
          </div>

          <p style="margin: 0; font-size: 12px; color: #94a3b8; line-height: 1.5;">
            ⏱ Код действителен <b>10 минут</b>.<br>Никому не сообщайте данный код.
          </p>
        </div>

        <!-- Footer -->
        <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 11px; color: #94a3b8;">
          ПАО КБ «Центр-инвест» • Защита корпоративной ликвидности
        </div>

      </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=12) as server:
            server.login(username, smtp_pass)
            server.sendmail(email_addr, [to_email], msg.as_string())
        logger.info(f"OTP email успешно отправлен на {to_email}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки почты через SMTP {smtp_host}:{smtp_port}: {e}")
        print(f"\n[SMTP ERROR]: {e}")
        print(f"[OTP FALLBACK] Код для {to_email}: {code}\n")
        return False
