import subprocess
import time
from datetime import datetime
import os
import configparser
import json  # GPS 정보 처리를 위해 추가

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


# =========================================================
# 📧 이메일 전송 함수 (위치 정보를 본문에 포함하도록 수정됨)
# =========================================================


def send_photo_email(filenames, subject_text, location_info):
    # 1. 설정 파일 (config.ini) 읽어오기
    config = configparser.ConfigParser()
    if not config.read("config.ini"):
        print("❌ 오류: config.ini 파일을 찾거나 읽을 수 없습니다.")
        return False

    settings = config["EMAIL_CONFIG"]

    # 2. 변수에 값 할당
    SMTP_SERVER = settings.get("smtp_server")
    SMTP_PORT = settings.getint("smtp_port")
    SENDER_EMAIL = settings.get("sender_email")
    APP_PASSWORD = settings.get("app_password")
    RECIPIENT_EMAIL = settings.get("recipient_email")

    # 3. 메일 내용 구성
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = subject_text

    # 4. 본문 추가 (GPS 정보 포함)
    body = (
        f"첨부된 파일은 침입자 감지 카메라가 촬영한 사진입니다. (총 {len(filenames)}장)\n\n"
        f"--- GPS 정보 ---\n"
        f"{location_info}\n"
        f"----------------"
    )
    msg.attach(MIMEText(body, "plain"))

    # 5. 첨부 파일 추가 (리스트 처리)
    for filename in filenames:
        if os.path.exists(filename):
            try:
                with open(filename, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())

                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {os.path.basename(filename)}",
                )
                msg.attach(part)
                print(f"✅ 파일 첨부 완료: {os.path.basename(filename)}")

            except Exception as e:
                print(f"❌ 파일 첨부 오류 ({os.path.basename(filename)}): {e}")

        else:
            print(f"❌ 첨부할 파일이 존재하지 않습니다: {filename}")

    # 6. SMTP 서버 접속 및 전송
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("✅ 이메일 전송 성공! 받는 사람: " + RECIPIENT_EMAIL)
        return True
    except Exception as e:
        print(f"❌ 이메일 전송 실패 (SMTP 오류): {e}")
        return False


# =========================================================
# 📷 사진 촬영 및 전송 통합 함수
# =========================================================


def take_selfie():
    target_dir = "/sdcard/DCIM/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    taken_files = []

    # -----------------------------------------------
    # 1. 🛰️ GPS 위치 정보 획득
    # -----------------------------------------------
    location_info = ""
    try:
        print("🛰️ GPS 위치 정보 수신 중... (최대 15초 대기)")
        loc_result = subprocess.run(
            ["termux-location", "-p", "high"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        loc_json = json.loads(loc_result.stdout)

        lat = loc_json.get("latitude", "N/A")
        lon = loc_json.get("longitude", "N/A")
        acc = loc_json.get("accuracy", "N/A")
        provider = loc_json.get("provider", "N/A")

        location_info = (
            f"위치 정보 획득 성공:\n"
            f"  > 시간: {datetime.now().strftime('%H:%M:%S')}\n"
            f"  > 위도: {lat}, 경도: {lon}\n"
            f"  > 정확도: {acc}m, 출처: {provider}"
        )
        print(f"✅ 위치 정보 획득 완료.")

    except Exception as e:
        location_info = "위치 정보 획득 실패 (GPS 비활성, 권한 오류, 또는 시간 초과)."
        print(f"❌ GPS 오류 발생: {e}")

    # -----------------------------------------------
    # 2. 📷 카메라 촬영 루프 (번갈아 촬영 및 딜레이)
    # -----------------------------------------------
    shooting_sequence = [
        {"name": "front", "id": 1},
        {"name": "back", "id": 0},
        {"name": "front", "id": 1},
        {"name": "back", "id": 0},
    ]

    print(f"📸 카메라 번갈아 촬영 시작 (총 {len(shooting_sequence)}장)...")

    for i, camera_info in enumerate(shooting_sequence):
        name = camera_info["name"]
        cam_id = camera_info["id"]
        sequence_num = i + 1

        filename = f"{target_dir}/{timestamp}_{name.lower()}_{sequence_num:02d}.jpg"
        command = f"termux-camera-photo -c {cam_id} {filename}"

        if sequence_num > 1:
            print("🕒 1초 대기...")
            time.sleep(1)

        try:
            print(f"  > {name} {sequence_num}차 촬영 시도 중... (ID: {cam_id})")
            subprocess.run(command, shell=True, check=True)
            print(
                f"  > {name} {sequence_num}차 촬영 성공: {os.path.basename(filename)}"
            )
            taken_files.append(filename)

        except subprocess.CalledProcessError:
            print(
                f"  ❌ {name} {sequence_num}차 촬영 실패. (ID: {cam_id}가 유효하지 않거나 권한 오류)"
            )

    # 3. 📧 이메일 전송
    if taken_files:
        print(f"\n📧 촬영된 사진 {len(taken_files)}장을 이메일로 전송합니다.")
        subject = f"🚨 lost_phone 감지 알림 (총 {len(taken_files)}장) ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        send_photo_email(taken_files, subject, location_info)  # 위치 정보 전달
    else:
        print("\n❌ 촬영된 사진이 없어 이메일을 전송하지 않습니다.")


if __name__ == "__main__":

    # 🚨 필수: 폴더 자동 생성 확인
    target_dir = "/sdcard/DCIM/termux"
    try:
        os.makedirs(target_dir, exist_ok=True)
        print(f"✅ 저장 폴더 확인/생성 완료: {target_dir}")
    except Exception as e:
        print(f"❌ 폴더 생성 실패: {e}. 권한을 확인해 주세요.")
        exit(1)

    print("스크립트 실행. 촬영 및 이메일 전송 시도.")

    take_selfie()
