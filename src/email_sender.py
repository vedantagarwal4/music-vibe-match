"""
email_sender.py

Sends a formatted Gmail digest with two sections:
  1. Songs worth your time  (above score threshold) - full table with reasoning
  2. Songs not worth it     (below threshold)       - compact list, just in case

Each song has Like and Dislike mailto buttons. Clicking one sends a feedback
email that the nightly script reads on the next run to improve future scoring.

Setup:
  1. Go to https://myaccount.google.com/apppasswords
  2. Create an App Password (needs 2FA enabled on your account)
  3. Use your Gmail address as GMAIL_ADDRESS
  4. Use the 16-character app password (no spaces) as GMAIL_APP_PASSWORD
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import quote


DIGEST_SUBJECT_PREFIX = "Shazam Nightly Digest"


def send_digest(
    gmail_address: str,
    gmail_app_password: str,
    to_address: str,
    scored_songs: list[dict],
    skipped_songs: list[dict],
    all_processed_count: int,
    duplicate_count: int,
    score_threshold: int,
    debug: bool = False,
) -> None:
    today   = datetime.now().strftime("%d %B %Y")
    subject = f"{DIGEST_SUBJECT_PREFIX} - {today} | {len(scored_songs)} recommended"

    html_body = _build_html(
        scored_songs=scored_songs,
        skipped_songs=skipped_songs,
        all_processed_count=all_processed_count,
        duplicate_count=duplicate_count,
        score_threshold=score_threshold,
        date_str=today,
        feedback_address=to_address,
    )
    text_body = _build_text(
        scored_songs=scored_songs,
        skipped_songs=skipped_songs,
        all_processed_count=all_processed_count,
        score_threshold=score_threshold,
        date_str=today,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = to_address
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if debug:
        print(f"[Email] Sending to {to_address}...")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())
        if debug:
            print("[Email] Sent successfully.")
    except smtplib.SMTPAuthenticationError:
        raise PermissionError(
            "[Email] Gmail authentication failed. "
            "Use an App Password from https://myaccount.google.com/apppasswords"
        )
    except Exception as e:
        raise RuntimeError(f"[Email] Failed to send: {e}")


# --- HTML helpers ---

def _score_color(score: int) -> str:
    if score >= 8:
        return "#27ae60"
    if score >= 6:
        return "#f39c12"
    return "#e74c3c"


def _feedback_buttons(title: str, artist: str, feedback_address: str) -> str:
    """Generate Like / Dislike mailto buttons for a song."""
    song_str     = f"{title} by {artist}"
    like_subject = quote(f"SHAZAM-FEEDBACK: {song_str} | LIKE")
    dis_subject  = quote(f"SHAZAM-FEEDBACK: {song_str} | DISLIKE")
    like_href    = f"mailto:{feedback_address}?subject={like_subject}"
    dis_href     = f"mailto:{feedback_address}?subject={dis_subject}"
    return (
        f'<a href="{like_href}" style="background:#27ae60; color:white; padding:4px 10px; '
        f'border-radius:4px; text-decoration:none; font-size:11px; margin-right:4px;">👍 Like</a>'
        f'<a href="{dis_href}" style="background:#e74c3c; color:white; padding:4px 10px; '
        f'border-radius:4px; text-decoration:none; font-size:11px;">👎 Dislike</a>'
    )


def _build_html(
    scored_songs: list[dict],
    skipped_songs: list[dict],
    all_processed_count: int,
    duplicate_count: int,
    score_threshold: int,
    date_str: str,
    feedback_address: str,
) -> str:

    scored_total = len(scored_songs) + len(skipped_songs)
    stats = f"""
    <div style="background:#f9f9f9; border-radius:6px; padding:12px 16px;
                margin-bottom:24px; font-size:13px; color:#555; line-height:1.8;">
      <strong>{all_processed_count}</strong> new Shazam songs detected
      &nbsp;&rarr;&nbsp;
      <strong>{duplicate_count}</strong> already in your playlists
      &nbsp;&rarr;&nbsp;
      <strong>{scored_total}</strong> sent to AI
      &nbsp;&rarr;&nbsp;
      <span style="color:#27ae60; font-weight:bold;">{len(scored_songs)} recommended</span>
      &nbsp;+&nbsp;
      <span style="color:#aaa;">{len(skipped_songs)} skipped</span>
    </div>"""

    feedback_note = """
    <div style="background:#fff8e1; border:1px solid #ffe082; border-radius:6px;
                padding:10px 14px; margin-bottom:20px; font-size:12px; color:#666;">
      <strong>Teach the AI your taste:</strong> Hit 👍 or 👎 on any song below.
      Clicking opens a pre-filled email - just send it. The AI learns from your ratings
      every night and improves future scores. You can also reply to this email with
      detailed thoughts on any song.
    </div>"""

    # --- Section 1: Recommended ---
    if not scored_songs:
        top_section = "<p style='color:#666;'>No songs crossed the threshold tonight.</p>"
    else:
        rows = ""
        for s in scored_songs:
            score = s["score"]
            b     = s.get("breakdown", {})
            breakdown_str = (
                f"artist {b.get('artist_affinity','?')}/3 &nbsp;"
                f"vibe {b.get('vibe_match','?')}/3 &nbsp;"
                f"quality {b.get('track_quality','?')}/2 &nbsp;"
                f"discovery {b.get('discovery_fit','?')}/2"
            )
            buttons = _feedback_buttons(s['title'], s['artist'], feedback_address)
            rows += f"""
            <tr>
              <td style="padding:14px 10px; border-bottom:1px solid #eee; vertical-align:top;">
                <strong style="font-size:14px;">{s['title']}</strong><br>
                <span style="color:#777; font-size:13px;">{s['artist']}</span><br>
                <div style="margin-top:6px;">{buttons}</div>
              </td>
              <td style="padding:14px 10px; border-bottom:1px solid #eee; color:#888;
                          font-size:12px; vertical-align:top;">{s['genre']}</td>
              <td style="padding:14px 10px; border-bottom:1px solid #eee;
                          text-align:center; vertical-align:top; white-space:nowrap;">
                <span style="background:{_score_color(score)}; color:white; padding:4px 11px;
                              border-radius:12px; font-weight:bold; font-size:14px;">
                  {score}/10
                </span><br>
                <span style="color:#aaa; font-size:11px; display:block; margin-top:4px;">
                  {breakdown_str}
                </span>
              </td>
              <td style="padding:14px 10px; border-bottom:1px solid #eee; font-size:13px;
                          color:#555; vertical-align:top;">{s['reasoning']}</td>
              <td style="padding:14px 10px; border-bottom:1px solid #eee;
                          vertical-align:top; text-align:center;">
                <a href="{s['yt_search_link']}"
                   style="background:#e62117; color:white; padding:5px 12px; border-radius:4px;
                           text-decoration:none; font-size:12px; white-space:nowrap;">
                  ▶ Listen
                </a>
              </td>
            </tr>"""

        top_section = f"""
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="background:#f0f0f0; color:#444; font-size:12px; text-transform:uppercase;">
              <th style="padding:10px; text-align:left; width:24%;">Song</th>
              <th style="padding:10px; text-align:left; width:16%;">Genre</th>
              <th style="padding:10px; text-align:center; width:18%;">Score</th>
              <th style="padding:10px; text-align:left;">Why</th>
              <th style="padding:10px; width:80px;"></th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    # --- Section 2: Skipped ---
    if not skipped_songs:
        skip_section = "<p style='color:#aaa; font-size:13px;'>All scored songs made the cut.</p>"
    else:
        skip_rows = ""
        for s in skipped_songs:
            score   = s["score"]
            buttons = _feedback_buttons(s['title'], s['artist'], feedback_address)
            skip_rows += f"""
            <tr>
              <td style="padding:8px 10px; border-bottom:1px solid #f0f0f0; font-size:13px;">
                {s['title']}<br>
                <div style="margin-top:4px;">{buttons}</div>
              </td>
              <td style="padding:8px 10px; border-bottom:1px solid #f0f0f0;
                          font-size:13px; color:#888;">{s['artist']}</td>
              <td style="padding:8px 10px; border-bottom:1px solid #f0f0f0;
                          font-size:13px; color:#aaa;">{s['genre']}</td>
              <td style="padding:8px 10px; border-bottom:1px solid #f0f0f0;
                          text-align:center;">
                <span style="color:#bbb; font-size:13px; font-weight:bold;">{score}/10</span>
              </td>
              <td style="padding:8px 10px; border-bottom:1px solid #f0f0f0; text-align:center;">
                <a href="{s['yt_search_link']}"
                   style="color:#aaa; font-size:12px; text-decoration:none;">Listen</a>
              </td>
            </tr>"""

        skip_section = f"""
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="color:#aaa; font-size:11px; text-transform:uppercase;">
              <th style="padding:8px 10px; text-align:left;">Song</th>
              <th style="padding:8px 10px; text-align:left;">Artist</th>
              <th style="padding:8px 10px; text-align:left;">Genre</th>
              <th style="padding:8px 10px; text-align:center;">Score</th>
              <th style="padding:8px 10px;"></th>
            </tr>
          </thead>
          <tbody>{skip_rows}</tbody>
        </table>"""

    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:840px; margin:0 auto; padding:24px; color:#333; background:#fff;">

  <h2 style="color:#1a1a1a; border-bottom:3px solid #e62117;
              padding-bottom:10px; margin-bottom:16px; font-size:20px;">
    Shazam Picks &mdash; {date_str}
  </h2>

  {stats}
  {feedback_note}

  <h3 style="color:#1a1a1a; font-size:15px; margin:0 0 10px 0; padding:10px 14px;
              background:#eafaf1; border-left:4px solid #27ae60; border-radius:2px;">
    Worth your time &nbsp;
    <span style="font-weight:normal; color:#666; font-size:13px;">
      ({len(scored_songs)} song{"s" if len(scored_songs) != 1 else ""} above {score_threshold}/10)
    </span>
  </h3>
  {top_section}

  <div style="height:32px;"></div>

  <h3 style="color:#999; font-size:14px; margin:0 0 10px 0; padding:10px 14px;
              background:#fafafa; border-left:4px solid #ddd; border-radius:2px;">
    Not worth it &nbsp;
    <span style="font-weight:normal; font-size:13px;">
      ({len(skipped_songs)} song{"s" if len(skipped_songs) != 1 else ""} below {score_threshold}/10 - listed for reference)
    </span>
  </h3>
  {skip_section}

  <p style="font-size:11px; color:#ccc; margin-top:32px; border-top:1px solid #f0f0f0;
             padding-top:12px;">
    Scored by Gemini 2.5 Flash against your full YouTube Music library ({scored_total + duplicate_count} songs).
    Threshold: {score_threshold}/10. Reply to this email with feedback to teach the AI your taste.
  </p>

</body>
</html>"""


def _build_text(
    scored_songs: list[dict],
    skipped_songs: list[dict],
    all_processed_count: int,
    score_threshold: int,
    date_str: str,
) -> str:
    lines = [f"Shazam Picks - {date_str}", "=" * 40, ""]
    lines.append("Reply to this email with thoughts on any song to teach the AI your taste.")
    lines.append("")
    lines.append(f"WORTH YOUR TIME ({len(scored_songs)} songs >= {score_threshold}/10)")
    lines.append("-" * 40)
    if scored_songs:
        for s in scored_songs:
            lines.append(f"{s['score']}/10 - {s['title']} by {s['artist']}")
            lines.append(f"  Genre:  {s['genre']}")
            lines.append(f"  Why:    {s['reasoning']}")
            lines.append(f"  Listen: {s['yt_search_link']}")
            lines.append("")
    else:
        lines.append("None tonight.")
        lines.append("")

    lines.append(f"NOT WORTH IT ({len(skipped_songs)} songs below {score_threshold}/10)")
    lines.append("-" * 40)
    for s in skipped_songs:
        lines.append(f"{s['score']}/10 - {s['title']} by {s['artist']}  |  {s['yt_search_link']}")

    lines.append("")
    lines.append(f"({all_processed_count} total new Shazam songs processed tonight)")
    return "\n".join(lines)
