import subprocess
import time
from datetime import datetime
import os
import configparser

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# =========================================================
# 📧 이메일 전송 함수 (파일명 리스트를 받도록 수정됨)
# =========================================================


def send_photo_email(filenames, subject_text):
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

    # 4. 본문 추가
    body = "첨부된 파일은 침입자 감지 카메라가 촬영한 사진입니다. (전면 및 후면)"
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

# =========================================================
# 📷 사진 촬영 및 전송 통합 함수
# =========================================================


def take_selfie():
    target_dir = "/sdcard/DCIM/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 찍은 파일 목록을 저장할 리스트
    taken_files = []

    # 1. 카메라 ID 목록 및 촬영 횟수 설정
    # 카메라 ID (0: 후면, 1: 전면)
    cameras = {"back": 0, "front": 1}
    SHOOT_COUNT = 2  # 🚨 각 카메라당 2장씩 촬영 설정

    print(
        f"📸 전면/후면 카메라 각각 {SHOOT_COUNT}장씩 총 {len(cameras) * SHOOT_COUNT}장 촬영 시작..."
    )

    for name, cam_id in cameras.items():
        for i in range(1, SHOOT_COUNT + 1):  # 1부터 2까지 반복 (1차, 2차 촬영)
            # 파일명과 경로를 카메라 이름 및 순번에 따라 다르게 설정
            filename = f"{target_dir}/{timestamp}_{name.lower()}_{i:02d}.jpg"
            command = f"termux-camera-photo -c {cam_id} {filename}"

            try:
                print(f"  > {name} {i}차 촬영 시도 중... (ID: {cam_id})")
                subprocess.run(command, shell=True, check=True)
                print(f"  > {name} {i}차 촬영 성공: {os.path.basename(filename)}")
                taken_files.append(filename)  # 성공한 파일만 목록에 추가

            except subprocess.CalledProcessError:
                # 첫 번째 실패 시 바로 다음 카메라로 넘어가지 않고 실패 메시지 출력
                print(
                    f"  ❌ {name} {i}차 촬영 실패. (ID: {cam_id}가 유효하지 않거나 권한 오류)"
                )
                # 이 에러는 심각한 오류가 아닐 수 있으므로 루프를 계속 진행합니다.

    # 3. 이메일 전송
    if taken_files:
        print(f"\n📧 촬영된 사진 {len(taken_files)}장을 이메일로 전송합니다.")
        subject = f"🚨 lost_phone 감지 알림 (총 {len(taken_files)}장) ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        send_photo_email(taken_files, subject)
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

    # 폰 기종에 따라 촬영이 느릴 수 있어 3초 대기 제거
    print("스크립트 실행. 촬영 및 이메일 전송 시도.")

    take_selfie()
