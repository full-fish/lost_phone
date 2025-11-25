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
# 🔋 전원 관리 함수 (Wake Lock)
# =========================================================
def acquire_wake_lock():
    subprocess.run(["termux-wake-lock"])


def release_wake_lock():
    subprocess.run(["termux-wake-unlock"])


# =========================================================
# 🛠️ 안전한 명령어 실행 함수 (Killer 기능 포함)
# =========================================================
def run_command_with_timeout(cmd_list, timeout_sec):
    try:
        proc = subprocess.Popen(
            cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        if proc.returncode == 0:
            return stdout, True
        else:
            return None, False
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return None, False
    except Exception as e:
        return None, False


# =========================================================
# 🛠️ 유틸리티: JSON 위치 정보 포맷팅
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
# 🛰️ 위치 정보 획득 함수 (Killer 적용됨, 시간 10초)
# =========================================================
def get_best_location():
    print("🛰️ 위치 정보 탐색 시작...")

    print("  [1단계] GPS 정밀 탐색 시도 (10초)...")
    gps_output, success = run_command_with_timeout(["termux-location", "-p", "gps"], 10)

    if success and gps_output:
        try:
            info = format_location_info(json.loads(gps_output))
            print("  ✅ GPS 위치 확보 성공.")
            return f"위치 정보 (GPS):\n{info}"
        except json.JSONDecodeError:
            pass

    print("  ⚠️ GPS 탐색 실패 또는 시간 초과. (프로세스 Kill 완료)")
    print("  🔄 네트워크로 전환합니다.")

    print("  [2단계] 네트워크 기반 탐색 시도 (10초)...")
    net_output, success = run_command_with_timeout(
        ["termux-location", "-p", "network"], 10
    )

    if success and net_output:
        try:
            info = format_location_info(json.loads(net_output))
            print("  ✅ 네트워크 위치 확보 성공.")
            return f"위치 정보 (Network):\n{info}"
        except json.JSONDecodeError:
            pass

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

        # 본문 수정
        photo_count = len([f for f in filenames if f.endswith(".jpg")])
        body = (
            f"침입자 감지 알림입니다.\n"
            f"- 사진: {photo_count}장\n"
            f"- 녹음: 포함됨\n\n"
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
# 📷 메인 촬영 및 녹음 함수
# =========================================================
def take_selfie():
    # 🚨 저장 경로 수정: Documents/termux 폴더로 변경
    target_dir = "/sdcard/Documents/termux"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    taken_files = []

    # -----------------------------------------------
    # 🎙️ 1. 오디오 녹음 시작 (백그라운드 실행)
    # -----------------------------------------------
    audio_filename = f"{target_dir}/{timestamp}_audio.m4a"
    audio_proc = None

    print(f"🎙️ 30초 녹음 시작 (백그라운드)...")
    try:
        audio_proc = subprocess.Popen(
            ["termux-microphone-record", "-d", "30", "-f", audio_filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        print(f"❌ 녹음 시작 실패: {e}")

    # -----------------------------------------------
    # 🛰️ 2. 위치 정보 가져오기 (녹음 중에 수행)
    # -----------------------------------------------
    location_info = get_best_location()

    # -----------------------------------------------
    # 📷 3. 카메라 촬영 (녹음 중에 수행)
    # -----------------------------------------------
    shooting_sequence = [
        {"name": "front", "id": 1},
        {"name": "back", "id": 0},
    ]

    print(f"\n📸 카메라 촬영 준비... (위치 찾느라 고생했으니 2초 쉼)")
    time.sleep(2)

    for i, cam in enumerate(shooting_sequence):
        name = cam["name"]
        cam_id = cam["id"]
        filename = f"{target_dir}/{timestamp}_{name}.jpg"

        if i > 0:
            print("🕒 카메라 전환 및 저장 대기 (4초)...")
            time.sleep(4)

        cmd = f"termux-camera-photo -c {cam_id} {filename}"

        try:
            print(f"  > [{name.upper()}] 촬영 시도...")
            subprocess.run(cmd, shell=True, check=True)
            print(f"  > 저장 완료: {os.path.basename(filename)}")
            taken_files.append(filename)
            time.sleep(1)

        except subprocess.CalledProcessError:
            print(f"  ❌ {name} 촬영 실패 (권한 또는 하드웨어 오류)")

    # -----------------------------------------------
    # ⏳ 4. 녹음 완료 대기 및 파일 추가
    # -----------------------------------------------
    if audio_proc:
        print("⏳ 녹음 완료 대기 중 (최대 30초)...")
        audio_proc.wait()  # 녹음이 끝날 때까지 기다립니다.

        if os.path.exists(audio_filename):
            print(f"✅ 녹음 완료: {os.path.basename(audio_filename)}")
            taken_files.append(audio_filename)  # 전송 목록에 추가
        else:
            print("❌ 녹음 파일 생성 실패")

    # -----------------------------------------------
    # 📧 5. 이메일 발송
    # -----------------------------------------------
    if taken_files:
        print("\n📧 이메일 전송 준비...")
        subject = f"🚨 Lost Phone 감지 (사진+녹음) ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        send_photo_email(taken_files, subject, location_info)
    else:
        print("\n❌ 전송할 파일이 없습니다.")


if __name__ == "__main__":
    acquire_wake_lock()
    print("🔒 Wake Lock 설정됨")

    try:
        # 🚨 폴더 자동 생성 경로도 Documents로 수정
        os.makedirs("/sdcard/Documents/termux", exist_ok=True)
        take_selfie()
    finally:
        release_wake_lock()
        print("🔓 Wake Lock 해제 완료.")
