import subprocess
import time
from datetime import datetime
import os
import configparser
import json
import shutil
import glob  # 🚨 파일 패턴 찾기를 위해 추가

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
# 🛰️ 위치 정보 획득 함수 (안정적인 3단계)
# =========================================================
def get_best_location():
    print("🛰️ 위치 정보 탐색 시작...")

    print("  [1단계] GPS 정밀 탐색 시도 (3초)...")
    gps_output, success = run_command_with_timeout(["termux-location", "-p", "gps"], 3)

    if success and gps_output:
        try:
            info = format_location_info(json.loads(gps_output))
            print("  ✅ GPS 위치 확보 성공.")
            return f"위치 정보 (GPS):\n{info}"
        except json.JSONDecodeError:
            pass

    print("  ⚠️ GPS 탐색 실패. (네트워크로 전환)")

    print("  [2단계] 네트워크 기반 탐색 시도 (5초)...")
    net_output, success = run_command_with_timeout(
        ["termux-location", "-p", "network"], 5
    )

    if success and net_output:
        try:
            info = format_location_info(json.loads(net_output))
            print("  ✅ 네트워크 위치 확보 성공.")
            return f"위치 정보 (Network):\n{info}"
        except json.JSONDecodeError:
            pass

    print("  ⚠️ 네트워크 탐색 실패. (마지막 위치 조회)")

    # 3단계: 마지막 위치 (Last Known Location)
    print("  [3단계] 마지막 저장된 위치 가져오기...")
    last_output, success = run_command_with_timeout(
        ["termux-location", "-r", "last"], 3
    )

    if success and last_output:
        try:
            info = format_location_info(json.loads(last_output))
            print("  ✅ 마지막 위치 확보 성공.")
            return f"위치 정보 (마지막 기록):\n{info}"
        except json.JSONDecodeError:
            pass

    print("  ❌ 모든 위치 탐색 실패.")
    return "위치 정보 획득 실패 (권한 확인 필요)"


# =========================================================
# 📧 이메일 전송 함수
# =========================================================
def send_photo_email(filenames, subject_text, location_info):
    config = configparser.ConfigParser()
    if not os.path.exists("config.ini"):
        home_config = "/data/data/com.termux/files/home/config.ini"
        if os.path.exists(home_config):
            config.read(home_config)
        else:
            print("❌ 오류: config.ini 파일을 찾을 수 없습니다.")
            return False
    else:
        config.read("config.ini")

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

        photo_count = len([f for f in filenames if f.endswith(".jpg")])
        body = (
            f"침입자 감지 알림입니다.\n"
            f"- 사진: {photo_count}장\n"
            f"- 녹음: 포함됨 (60초)\n\n"
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
# 🔍 최신 녹음 파일 찾기 함수 (추가됨)
# =========================================================
def find_latest_recording(search_dir="/sdcard/"):
    pattern = os.path.join(search_dir, "TermuxAudioRecording*.m4a")
    files = glob.glob(pattern)

    if not files:
        return None

    latest_file = max(files, key=os.path.getmtime)
    return latest_file


# =========================================================
# 📷 메인 촬영 및 녹음 함수 (최종 수동 타이머)
# =========================================================
def take_selfie():
    target_dir = "/sdcard/Documents/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    taken_files = []

    RECORD_SECONDS = 60  # 🚨 녹음 시간 설정 (초)

    # -----------------------------------------------
    # 🎙️ 1. 오디오 녹음 시작 (수동 제어)
    # -----------------------------------------------
    final_audio = f"{target_dir}/{timestamp}_audio.m4a"
    record_start_time = time.time()  # 🚨 시작 시간 기록

    print(f"🎙️ {RECORD_SECONDS}초 녹음 시작 (수동 제어)...")
    try:
        # Popen으로 무한 녹음을 시작합니다. (Process itself does not block Python)
        subprocess.Popen(
            ["termux-microphone-record"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        print(f"❌ 녹음 시작 실패: {e}")

    # -----------------------------------------------
    # 🛰️ 2. 위치 정보 가져오기
    # -----------------------------------------------
    location_info = get_best_location()

    # -----------------------------------------------
    # 📷 3. 카메라 촬영
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
    # ⏳ 4. 남은 시간 대기 및 녹음 종료 (핵심)
    # -----------------------------------------------
    elapsed_time = time.time() - record_start_time
    remaining_time = RECORD_SECONDS - elapsed_time

    if remaining_time > 0:
        print(f"⏳ 남은 {remaining_time:.1f}초 대기 후 녹음 종료...")
        time.sleep(remaining_time)
    else:
        print("⏳ 주요 작업 시간이 60초를 초과했습니다. 즉시 종료합니다.")

    # 🚨 녹음 강제 종료 명령 전송 (-q 옵션)
    subprocess.run(
        ["termux-microphone-record", "-q"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)  # 파일이 완전히 닫힐 시간 부여

    # -----------------------------------------------
    # 📂 5. 파일 찾기 및 이동
    # -----------------------------------------------
    latest_rec = find_latest_recording("/sdcard/")

    if latest_rec and os.path.exists(latest_rec):
        try:
            shutil.move(latest_rec, final_audio)
            print(f"✅ 녹음 파일 발견 및 이동 완료: {os.path.basename(final_audio)}")
            taken_files.append(final_audio)
        except Exception as e:
            print(f"❌ 녹음 파일 이동 실패: {e}")
    else:
        termux_home = os.getenv("HOME", "/data/data/com.termux/files/home")
        latest_rec_home = find_latest_recording(termux_home)

        if latest_rec_home and os.path.exists(latest_rec_home):
            try:
                shutil.move(latest_rec_home, final_audio)
                print(
                    f"✅ 녹음 파일(홈) 발견 및 이동 완료: {os.path.basename(final_audio)}"
                )
                taken_files.append(final_audio)
            except Exception as e:
                print(f"❌ 녹음 파일 이동 실패: {e}")
        else:
            print("❌ 녹음 파일을 찾을 수 없습니다. (저장 실패)")

    # -----------------------------------------------
    # 📧 6. 이메일 발송
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
        os.makedirs("/sdcard/Documents/termux", exist_ok=True)
        take_selfie()
    finally:
        release_wake_lock()
        print("🔓 Wake Lock 해제 완료.")
