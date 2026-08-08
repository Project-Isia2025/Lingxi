"""ROI 报表邮件发送。"""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import bootstrap
from services.roi_export import export_roi_csv


def email_report_enabled() -> bool:
    return os.environ.get("ROI_REPORT_EMAIL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def _smtp_config() -> dict[str, Any]:
    return {
        "host": (os.environ.get("SMTP_HOST") or "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "465") or 465),
        "user": (os.environ.get("SMTP_USER") or "").strip(),
        "password": (os.environ.get("SMTP_PASSWORD") or "").strip(),
        "from_addr": (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip(),
        "to_addrs": [a.strip() for a in (os.environ.get("ROI_REPORT_EMAIL_TO") or "").split(",") if a.strip()],
        "use_ssl": os.environ.get("SMTP_USE_SSL", "1").strip().lower() not in ("0", "false", "no"),
    }


def save_report_to_disk(*, days: int = 30) -> Path:
    """保存 CSV 到 data/reports/。"""
    csv_text = export_roi_csv(days=days)
    out_dir = bootstrap.project_root() / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"roi_report_{days}d_{ts}.csv"
    path.write_text(csv_text, encoding="utf-8-sig")
    return path


def send_roi_report_email(*, days: int = 30) -> dict[str, Any]:
    """发送 ROI CSV 邮件；未配置 SMTP 时仅保存本地。"""
    path = save_report_to_disk(days=days)
    result: dict[str, Any] = {"ok": True, "saved_path": str(path), "days": days, "emailed": False}

    if not email_report_enabled():
        result["mode"] = "file_only"
        return result

    cfg = _smtp_config()
    if not cfg["host"] or not cfg["to_addrs"]:
        result["mode"] = "file_only"
        result["hint"] = "配置 SMTP_HOST 与 ROI_REPORT_EMAIL_TO 以启用邮件"
        return result

    csv_bytes = path.read_bytes()
    msg = MIMEMultipart()
    msg["Subject"] = f"矩阵 Agent ROI 报表 ({days}日) - {datetime.now():%Y-%m-%d}"
    msg["From"] = cfg["from_addr"]
    msg["To"] = ", ".join(cfg["to_addrs"])
    msg.attach(MIMEText(f"附件为近 {days} 日 ROI 指标报表。\n生成时间：{datetime.now()}", "plain", "utf-8"))
    att = MIMEApplication(csv_bytes, Name=path.name)
    att["Content-Disposition"] = f'attachment; filename="{path.name}"'
    msg.attach(att)

    try:
        if cfg["use_ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30) as smtp:
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["from_addr"], cfg["to_addrs"], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
                smtp.starttls()
                if cfg["user"]:
                    smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["from_addr"], cfg["to_addrs"], msg.as_string())
        result["emailed"] = True
        result["mode"] = "email"
        result["to"] = cfg["to_addrs"]
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)[:300]
        result["mode"] = "email_failed"
    return result
