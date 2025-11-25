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
    """
    명령어를 실행하되, 시간이 초과되면 프로세스를 확실히 죽입니다.
    성공 시: (stdout, True) 반환
    실패/초과 시: (None, False) 반환
    """
    try:
        # Popen으로 프로세스를 엽니다.
        proc = subprocess.Popen(
            cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # 정해진 시간만큼 기다립니다.
        stdout, stderr = proc.communicate(timeout=timeout_sec)

        # 실행이 잘 끝났으면 결과 반환
        if proc.returncode == 0:
            return stdout, True
        else:
            return None, False

    except subprocess.TimeoutExpired:
        # 🚨 시간이 초과되면 프로세스를 강제로 죽입니다 (Kill)
        proc.kill()
        # 좀비 프로세스가 되지 않게 뒷정리(communicate)를 한 번 더 해줍니다.
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
# 🛰️ 위치 정보 획득 함수 (Killer 적용됨)
# =========================================================
def get_best_location():
    print("🛰️ 위치 정보 탐색 시작...")

    # 1단계: GPS (High Accuracy) 우선 시도
    print("  [1단계] GPS 정밀 탐색 시도 (15초)...")

    # 위에서 만든 '안전한 실행 함수'를 사용합니다.
    gps_output, success = run_command_with_timeout(["termux-location", "-p", "gps"], 15)

    if success and gps_output:
        try:
            info = format_location_info(json.loads(gps_output))
            print("  ✅ GPS 위치 확보 성공.")
            return f"위치 정보 (GPS):\n{info}"
        except json.JSONDecodeError:
            pass  # JSON 파싱 에러나면 다음으로 넘어감

    print("  ⚠️ GPS 탐색 실패 또는 시간 초과. (프로세스 Kill 완료)")
    print("  🔄 네트워크로 전환합니다.")

    # 2단계: Network (Wi-Fi/Cell) 시도
    print("  [2단계] 네트워크 기반 탐색 시도 (15초)...")

    net_output, success = run_command_with_timeout(
        ["termux-location", "-p", "network"], 15
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

    # 1. 위치 정보 가져오기 (GPS -> 15초 -> Kill -> Network -> 15초)
    location_info = get_best_location()

    # 2. 촬영 시퀀스 설정 (전면 1장, 후면 1장)
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

    # 3. 이메일 발송
    if taken_files:
        print("\n📧 이메일 전송 준비...")
        subject = f"🚨 Lost Phone 감지 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        send_photo_email(taken_files, subject, location_info)
    else:
        print("\n❌ 촬영된 사진이 없습니다.")


if __name__ == "__main__":
    acquire_wake_lock()
    print("🔒 Wake Lock 설정됨")

    try:
        os.makedirs("/sdcard/DCIM/termux", exist_ok=True)
        take_selfie()
    finally:
        release_wake_lock()
        print("🔓 Wake Lock 해제 완료.")
