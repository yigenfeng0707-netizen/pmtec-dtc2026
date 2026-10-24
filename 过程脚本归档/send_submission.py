#!/usr/bin/env python3
"""DTC2026 正式提交邮件发送（fengyigen@qq.com -> innobase@qq.com）

用法: python send_submission.py <QQ_SMTP授权码> [--dry]
授权码获取: QQ邮箱网页版 -> 设置 -> 账户 -> POP3/IMAP/SMTP服务 -> 开启 -> 生成授权码

降级链：优先单封全量（56MB 完整离线包，部分账号 SMTP 上限更高）；
被 SMTP 拒收时自动切两封——A: 离线包(不含视频)+技术方案；B: 视频 V3 单发。
"""
import smtplib
import sys
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr

AUTH = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("QQ_SMTP_AUTH", "")
DRY = "--dry" in sys.argv
ROOT = os.path.dirname(os.path.abspath(__file__))

FROM = "fengyigen@qq.com"
TO = "innobase@qq.com"
SUBJECT = ("第八届数字孪生体挑战赛（DTC 2026）赛道二 —— 根深叶茂团队 "
           "正式提交材料（评审整改后终版）")
SUBJECT_VIDEO = ("第八届数字孪生体挑战赛（DTC 2026）赛道二 —— 根深叶茂团队 "
                 "提交材料 2/2：演示视频 V3（314 秒）")
QUOTES = chr(34)
SENDER_NAME = "冯亦根 " + QUOTES + "根深叶茂" + QUOTES + " 团队"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ATTACHMENTS_FULL = [
    ("DTC2026-离线提交包.zip", "application/zip"),
    ("docs/PMTEC-技术方案.docx", DOCX_MIME),
    ("docs/PMTEC-技术方案.pdf", "application/pdf"),
]
ATTACHMENTS_SPLIT_A = [
    ("DTC2026-离线提交包-邮件版.zip", "application/zip"),
    ("docs/PMTEC-技术方案.docx", DOCX_MIME),
    ("docs/PMTEC-技术方案.pdf", "application/pdf"),
]
ATTACHMENTS_SPLIT_B = [
    ("pmtec_system/output/pmtec_demo_video_v3.mp4", "video/mp4"),
]


def build_mail(subject, attach_list, body_override=None):
    m = MIMEMultipart()
    m["From"] = formataddr((str(Header(SENDER_NAME, "utf-8")), FROM))
    m["To"] = TO
    m["Subject"] = Header(subject, "utf-8")
    text = body_override if body_override else open(
        os.path.join(ROOT, "docs", "submission_body.html"), encoding="utf-8").read()
    m.attach(MIMEText(text, "html", "utf-8"))
    total = 0
    for rel, ctype in attach_list:
        full = os.path.join(ROOT, rel)
        size = os.path.getsize(full)
        total += size
        with open(full, "rb") as f:
            part = MIMEApplication(f.read())
        part.add_header("Content-Disposition", "attachment",
                        filename=Header(os.path.basename(rel), "utf-8").encode())
        m.attach(part)
        print(f"  附件: {rel} {size / 1048576:.1f}MB")
    print(f"  附件合计: {total / 1048576:.1f}MB（原始）"
          f"≈ {total * 4 / 3 / 1048576:.1f}MB（base64 后）")
    return m


def try_send(m):
    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=60) as s:
        s.login(FROM, AUTH)
        refuse = s.sendmail(FROM, [TO], m.as_string())
        if refuse:
            print("  收件方拒收:", refuse)
            return False
    return True


def main():
    if not AUTH:
        print("缺少 QQ SMTP 授权码。获取: QQ邮箱网页版 -> 设置 -> 账户 -> "
              "POP3/IMAP/SMTP服务 -> 开启 -> 生成授权码")
        print("用法: python send_submission.py <授权码> [--dry]")
        return 1
    body_html = open(os.path.join(ROOT, "docs", "submission_body.html"),
                     encoding="utf-8").read()

    if DRY:
        print("[DRY] 方案 1 单封全量预览：")
        build_mail(SUBJECT, ATTACHMENTS_FULL)
        print("[DRY] 未实际发送")
        return 0

    print("[方案 1] 单封全量（56MB 完整离线包）...")
    try:
        if try_send(build_mail(SUBJECT, ATTACHMENTS_FULL)):
            print("发送成功（单封全量）:", TO)
            return 0
    except Exception as e:
        print(f"  方案 1 被拒: {type(e).__name__}: {str(e)[:200]}")

    print("[方案 2] 拆两封：A 离线包+技术方案；B 视频 V3 ...")
    if not try_send(build_mail(SUBJECT, ATTACHMENTS_SPLIT_A)):
        print("  邮件 A 失败！")
        return 1
    print("  邮件 A 发送成功")
    video_note = body_html.replace(
        "</ol>",
        "</ol><p><b>说明</b>：因单封邮件附件限额，演示视频 V3（314 秒，26.8MB）"
        "在本邮件 2/2 的附件中提供；亦可直接在公网演示中心在线观看。</p>", 1)
    if not try_send(build_mail(SUBJECT_VIDEO, ATTACHMENTS_SPLIT_B,
                               body_override=video_note)):
        print("  邮件 B 失败！")
        return 1
    print("  邮件 B 发送成功")
    print("全部发送成功:", TO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
