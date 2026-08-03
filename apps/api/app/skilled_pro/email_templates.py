"""
Branded transactional email — one layout, used by every workflow email.

Design (mirrors the product's ElevenLabs-clean contract):
  * near-white ground (#fcfcfb), one white card, hairline border (#e7e5e2)
  * "SKILLED Nation" text wordmark — no images, nothing to block or lazy-load
  * ink text (#17171c), muted slate for secondary lines (#5c5a55)
  * exactly one button, brand maroon (#9E1B32), fully-rounded pill
  * table-based layout + inline styles so it renders in Outlook/Gmail/Apple
  * every email also carries a plaintext alternative part

`branded_email()` returns (html, text) — callers pass both to
`senders.send_email(to, subject, text, html)`.
"""
from __future__ import annotations

from html import escape
from typing import Optional, Sequence

_INK = "#17171c"
_SLATE = "#5c5a55"
_CANVAS = "#fcfcfb"
_HAIRLINE = "#e7e5e2"
_MAROON = "#9E1B32"
_FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
)


def branded_email(
    *,
    preheader: str,
    heading: str,
    paragraphs: Sequence[str],
    cta_label: str,
    cta_url: str,
    meta_lines: Sequence[str] = (),
    footer_note: Optional[str] = None,
) -> tuple[str, str]:
    """Render the one-card branded email. All inputs are plain text (escaped).

    ``meta_lines`` render as a quiet detail block between the body and the
    button (e.g. "Role: Admin" / "Expires Aug 10").
    ``footer_note`` is the honest fine print ("If you weren't expecting
    this…"). The raw URL is always printed under the button so the email
    works even when buttons/links are rewritten or images blocked.
    """
    body_html = "".join(
        f'<p style="margin:0 0 14px; font-size:15px; line-height:1.6; color:{_INK};">{escape(p)}</p>'
        for p in paragraphs
    )
    meta_html = ""
    if meta_lines:
        rows = "".join(
            f'<p style="margin:0 0 4px; font-size:13px; line-height:1.5; color:{_SLATE};">{escape(m)}</p>'
            for m in meta_lines
        )
        meta_html = (
            f'<div style="margin:18px 0 0; padding:14px 16px; border:1px solid {_HAIRLINE};'
            f' border-radius:10px; background:#ffffff;">{rows}</div>'
        )
    footer_html = (
        f'<p style="margin:16px 0 0; font-size:12px; line-height:1.6; color:{_SLATE};">{escape(footer_note)}</p>'
        if footer_note
        else ""
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(heading)}</title>
</head>
<body style="margin:0; padding:0; background:{_CANVAS}; font-family:{_FONT};">
  <div style="display:none; max-height:0; overflow:hidden; mso-hide:all;">{escape(preheader)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_CANVAS};">
    <tr>
      <td align="center" style="padding:40px 16px 48px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;">
          <tr>
            <td style="padding:0 4px 18px;">
              <span style="font-size:16px; font-weight:600; letter-spacing:-0.02em; color:{_INK};">SKILLED Nation</span>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff; border:1px solid {_HAIRLINE}; border-radius:14px; padding:32px;">
              <h1 style="margin:0 0 16px; font-size:21px; line-height:1.35; font-weight:600; letter-spacing:-0.02em; color:{_INK};">{escape(heading)}</h1>
              {body_html}
              {meta_html}
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0;">
                <tr>
                  <td style="border-radius:999px; background:{_MAROON};">
                    <a href="{escape(cta_url, quote=True)}"
                       style="display:inline-block; padding:11px 24px; font-size:14px; font-weight:600; color:#ffffff; text-decoration:none; border-radius:999px;">{escape(cta_label)}</a>
                  </td>
                </tr>
              </table>
              <p style="margin:18px 0 0; font-size:12px; line-height:1.6; color:{_SLATE};">
                If the button doesn't work, copy this link into your browser:<br>
                <a href="{escape(cta_url, quote=True)}" style="color:{_SLATE}; word-break:break-all;">{escape(cta_url)}</a>
              </p>
              {footer_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 4px 0;">
              <p style="margin:0; font-size:12px; line-height:1.6; color:{_SLATE};">SKILLED Nation · Skilled-trades hiring, done honestly.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    text_lines = [heading, ""]
    text_lines += list(paragraphs)
    if meta_lines:
        text_lines += [""] + list(meta_lines)
    text_lines += ["", f"{cta_label}: {cta_url}"]
    if footer_note:
        text_lines += ["", footer_note]
    text_lines += ["", "SKILLED Nation"]
    text = "\n".join(text_lines)

    return html, text
