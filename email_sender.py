"""HTML email delivery for generated LinkedIn posts."""

from __future__ import annotations

import html
import logging
import smtplib
import time
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    use_tls: bool
    username: str
    password: str
    from_email: str
    from_name: str
    to_email: str
    max_retries: int = 3
    retry_delay_seconds: int = 5


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be sent."""


class EmailSender:
    """Sends LinkedIn posts as formatted HTML email."""

    def __init__(self, config: EmailConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def send_post(self, post: str, post_date: date | None = None) -> None:
        """Send the generated LinkedIn post by email with retries."""
        post_date = post_date or date.today()
        message = self._build_message(post, post_date)
        self._send_with_retries(message)

    def send_post_choices(self, posts: list[str], post_date: date | None = None) -> None:
        """Send multiple LinkedIn post options in one email."""
        post_date = post_date or date.today()
        message = self._build_choices_message(posts, post_date)
        self._send_with_retries(message)

    def _send_with_retries(self, message: EmailMessage) -> None:
        """Send an email with retry handling."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                self.logger.info("Sending LinkedIn post email to %s", self.config.to_email)
                self._send(message)
                self.logger.info("Email sent successfully")
                return
            except Exception as exc:  # noqa: BLE001 - surfaced with context after retries.
                last_error = exc
                self.logger.warning(
                    "Email delivery attempt %s/%s failed: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay_seconds)

        raise EmailDeliveryError(f"Failed to send email: {last_error}") from last_error

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=60) as server:
            server.ehlo()
            if self.config.use_tls:
                server.starttls()
                server.ehlo()
            if self.config.username:
                server.login(self.config.username, self.config.password)
            server.send_message(message)

    def _build_message(self, post: str, post_date: date) -> EmailMessage:
        formatted_date = format_display_date(post_date)
        subject = f"Your Daily LinkedIn Post - {formatted_date}"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((self.config.from_name, self.config.from_email))
        message["To"] = self.config.to_email
        message.set_content(post)
        message.add_alternative(self._html_body(post, post_date), subtype="html")
        return message

    def _build_choices_message(self, posts: list[str], post_date: date) -> EmailMessage:
        formatted_date = format_display_date(post_date)
        subject = f"Your Daily LinkedIn Post Options - {formatted_date}"
        plain_text = "\n\n".join(f"OPTION {index}\n\n{post}" for index, post in enumerate(posts, start=1))

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((self.config.from_name, self.config.from_email))
        message["To"] = self.config.to_email
        message.set_content(plain_text)
        message.add_alternative(self._choices_html_body(posts, post_date), subtype="html")
        return message

    @staticmethod
    def _html_body(post: str, post_date: date) -> str:
        formatted_date = format_display_date(post_date)
        escaped = html.escape(post).replace("\n", "<br>")
        return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7f9;font-family:Arial,Helvetica,sans-serif;color:#1f2933;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7f9;padding:28px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="680" cellspacing="0" cellpadding="0" style="width:680px;max-width:94%;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;">
            <tr>
              <td style="padding:28px 32px 10px 32px;">
                <div style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#2563eb;">Daily LinkedIn Post</div>
                <h1 style="margin:10px 0 4px 0;font-size:24px;line-height:1.25;color:#111827;">Elizabeth K. Flannery</h1>
                <div style="font-size:14px;color:#6b7280;">{formatted_date}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 32px 32px 32px;">
                <div style="font-size:16px;line-height:1.65;white-space:normal;color:#111827;">{escaped}</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

    @staticmethod
    def _choices_html_body(posts: list[str], post_date: date) -> str:
        formatted_date = format_display_date(post_date)
        options = []
        for index, post in enumerate(posts, start=1):
            escaped = html.escape(post).replace("\n", "<br>")
            options.append(
                f"""
                <div style="margin:0 0 24px 0;padding:20px;border:1px solid #e5e7eb;border-radius:8px;background:#ffffff;">
                  <div style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#2563eb;margin-bottom:12px;">Option {index}</div>
                  <div style="font-size:16px;line-height:1.65;color:#111827;">{escaped}</div>
                </div>
                """
            )

        return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f7f9;font-family:Arial,Helvetica,sans-serif;color:#1f2933;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7f9;padding:28px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="760" cellspacing="0" cellpadding="0" style="width:760px;max-width:94%;">
            <tr>
              <td style="padding:0 0 18px 0;">
                <div style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#2563eb;">Daily LinkedIn Post Options</div>
                <h1 style="margin:10px 0 4px 0;font-size:24px;line-height:1.25;color:#111827;">Elizabeth K. Flannery</h1>
                <div style="font-size:14px;color:#6b7280;">{formatted_date}</div>
              </td>
            </tr>
            <tr>
              <td>{''.join(options)}</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def format_display_date(value: date) -> str:
    """Return a human-readable date without platform-specific strftime flags."""
    return f"{value.strftime('%B')} {value.day}, {value.year}"
