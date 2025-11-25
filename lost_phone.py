import subprocess
import time
from datetime import datetime
import os
import configparser
import json

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


# =========================================================
# 🛠️ 유틸리티: JSON 위치 정보 포맷팅 함수
# =========================================================
def format_location_info(loc_json):
    lat = loc_json.get("latitude", "N/A")
    lon = loc_json.get("longitude", "N/A")
    acc = loc_json.get("accuracy", "N/A")
    provider = loc_json.get("provider", "N/A")

    return (
        f"  > 시간: {datetime.now().strftime('%H:%M:%S')}\n"
        f"  > 위도: {lat}, 경도: {lon}\n"
        f"  > 정확도: {acc}m, 출처: {provider}"
    )


# =========================================================
# 🛰️ 위치 정보 획득 함수 (GPS -> Network 순차 시도)
# =========================================================
def get_best_location():
    print("🛰️ 위치 정보 탐색 시작...")

    # 1단계: GPS (High Accuracy) 시도
    try:
        print("  [1단계] GPS 정밀 탐색 시도 (15초)...")
        res = subprocess.run(
            ["termux-location", "-p", "high"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        info = format_location_info(json.loads(res.stdout))
        print("  ✅ GPS 위치 확보 성공.")
        return f"위치 정보 (GPS):\n{info}"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print("  ⚠️ GPS 탐색 실패 또는 시간 초과.")

    # 2단계: Network (Wi-Fi/Cell) 시도
    try:
        print("  [2단계] 네트워크 기반 탐색 시도 (15초)...")
        res = subprocess.run(
            ["termux-location", "-p", "network"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        info = format_location_info(json.loads(res.stdout))
        print("  ✅ 네트워크 위치 확보 성공.")
        return f"위치 정보 (Network):\n{info}"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print("  ❌ 모든 위치 탐색 실패.")
        return "위치 정보 획득 실패 (GPS 및 네트워크 응답 없음)"


# =========================================================
# 📧 이메일 전송 함수
# =========================================================
def send_photo_email(filenames, subject_text, location_info):
    config = configparser.ConfigParser()
    if not config.read("config.ini"):
        print("❌ 오류: config.ini 파일을 찾을 수 없습니다.")
        return False

    try:
        settings = config["EMAIL_CONFIG"]
        SMTP_SERVER = settings.get("smtp_server")
        SMTP_PORT = settings.getint("smtp_port")
        SENDER_EMAIL = settings.get("sender_email")
        APP_PASSWORD = settings.get("app_password")
        RECIPIENT_EMAIL = settings.get("recipient_email")

        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENT_EMAIL
        msg["Subject"] = subject_text

        body = (
            f"침입자 감지 알림입니다. (총 {len(filenames)}장)\n\n"
            f"--- 위치 정보 ---\n{location_info}\n-----------------"
        )
        msg.attach(MIMEText(body, "plain"))

        for filename in filenames:
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {os.path.basename(filename)}",
                )
                msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print(f"✅ 이메일 전송 완료 ({RECIPIENT_EMAIL})")
        return True
    except Exception as e:
        print(f"❌ 이메일 전송 오류: {e}")
        return False


# =========================================================
# 📷 메인 촬영 함수
# =========================================================
def take_selfie():
    target_dir = "/sdcard/DCIM/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    taken_files = []

    # 1. 위치 정보 가져오기 (GPS 15초 -> 실패시 Network 15초)
    location_info = get_best_location()

    # 2. 촬영 시퀀스 설정 (전면 1장, 후면 1장)
    shooting_sequence = [
        {"name": "front", "id": 1},  # 전면
        {"name": "back", "id": 0},  # 후면
    ]

    print(f"\n📸 카메라 촬영 준비... (안정성을 위해 3초 대기)")
    time.sleep(3)  # 🚨 초기 하드웨어 준비 시간 확보

    for i, cam in enumerate(shooting_sequence):
        name = cam["name"]
        cam_id = cam["id"]
        filename = f"{target_dir}/{timestamp}_{name}.jpg"

        # 🚨 카메라 전환 시 충분한 시간 확보 (4초)
        if i > 0:
            print("🕒 카메라 전환 및 저장 대기 (4초)...")
            time.sleep(4)

        cmd = f"termux-camera-photo -c {cam_id} {filename}"

        try:
            print(f"  > [{name.upper()}] 촬영 시도...")
            subprocess.run(cmd, shell=True, check=True)
            print(f"  > 저장 완료: {os.path.basename(filename)}")
            taken_files.append(filename)
        except subprocess.CalledProcessError:
            print(f"  ❌ {name} 촬영 실패 (권한 또는 하드웨어 오류)")

    # 3. 이메일 발송
    if taken_files:
        print("\n📧 이메일 전송 준비...")
        subject = f"🚨 Lost Phone 감지 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        send_photo_email(taken_files, subject, location_info)
    else:
        print("\n❌ 촬영된 사진이 없습니다.")


if __name__ == "__main__":
    # 필수 폴더 생성
    try:
        os.makedirs("/sdcard/DCIM/termux", exist_ok=True)
    except OSError:
        print("❌ 폴더 생성 권한 오류.")
        exit(1)

    take_selfie()
