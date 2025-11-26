import subprocess
import time
from datetime import datetime
import os
import configparser
import json
import shutil
import glob

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
# 🛰️ 위치 정보 획득 함수
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
# 📧 이메일 전송 함수 (결함 허용 로직 강화)
# =========================================================
def send_photo_email(filenames, subject_text, location_info):
    config = configparser.ConfigParser()
    config_path = "config.ini"

    # config.ini 경로 확인
    if not os.path.exists(config_path):
        home_config = "/data/data/com.termux/files/home/config.ini"
        if os.path.exists(home_config):
            config_path = home_config
        else:
            print("❌ 오류: config.ini 파일을 찾을 수 없습니다.")
            return False

    config.read(config_path)

    if not config.sections():
        print("❌ 오류: 설정 파일에 계정 정보가 없습니다.")
        return False

    success_count = 0

    # 🚨 모든 섹션(계정)을 순회
    for section in config.sections():
        print(f"\n📨 [{section}] 계정 처리 중...")

        try:
            settings = config[section]

            # 값 읽기 (없으면 None 반환)
            SMTP_SERVER = settings.get("smtp_server")
            SMTP_PORT = settings.getint("smtp_port")
            SENDER_EMAIL = settings.get("sender_email")
            APP_PASSWORD = settings.get("app_password")
            RECIPIENT_EMAIL = settings.get("recipient_email")

            # 🚨 [검증 단계] 필수 정보가 하나라도 비어있으면 이 계정은 건너뜀
            if not all(
                [SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, APP_PASSWORD, RECIPIENT_EMAIL]
            ):
                print(f"  ⚠️ 경고: [{section}] 설정 정보가 부족합니다. 건너뜁니다.")
                continue  # 다음 섹션으로 즉시 이동

            # 메일 구성
            msg = MIMEMultipart()
            msg["From"] = SENDER_EMAIL
            msg["To"] = RECIPIENT_EMAIL
            msg["Subject"] = subject_text

            photo_count = len([f for f in filenames if f.endswith(".jpg")])
            body = (
                f"침입자 감지 알림입니다.\n"
                f"- 발송 계정: {section}\n"
                f"- 사진: {photo_count}장\n"
                f"- 녹음: 포함됨 (60초)\n\n"
                f"--- 위치 정보 ---\n{location_info}\n-----------------"
            )
            msg.attach(MIMEText(body, "plain"))

            # 파일 첨부
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

            # 서버 연결 및 전송
            print(f"  Connecting to {SMTP_SERVER}...")
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
            server.quit()

            print(f"  ✅ {section}: 전송 성공! -> {RECIPIENT_EMAIL}")
            success_count += 1

        except Exception as e:
            # 🚨 이 계정에서 에러가 나도 스크립트는 죽지 않고 로그만 남김
            print(f"  ❌ {section}: 전송 실패 ({e})")
            # continue는 자동으로 수행됨 (다음 루프로)

    return success_count > 0


# =========================================================
# 🔍 최신 녹음 파일 찾기 함수
# =========================================================
def find_latest_recording(search_dir="/sdcard/"):
    pattern = os.path.join(search_dir, "TermuxAudioRecording*.m4a")
    files = glob.glob(pattern)

    if not files:
        return None

    latest_file = max(files, key=os.path.getmtime)
    return latest_file


# =========================================================
# 📷 메인 촬영 및 녹음 함수
# =========================================================
# =========================================================
# 📷 메인 촬영 및 녹음 함수 (수정됨)
# =========================================================
def take_selfie():
    target_dir = "/sdcard/Documents/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    taken_files = []

    RECORD_SECONDS = 60

    # -----------------------------------------------
    # 🎙️ 1. 오디오 녹음 시작 (수정: 파일명 지정 방식)
    # -----------------------------------------------
    final_audio = f"{target_dir}/{timestamp}_audio.m4a"

    print(f"🎙️ {RECORD_SECONDS}초 녹음 시작 (파일 직접 저장)...")
    try:
        # [-f 파일경로] 옵션을 추가하여 지정된 위치에 바로 저장합니다.
        subprocess.Popen(
            ["termux-microphone-record", "-f", final_audio],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        record_start_time = time.time()
    except Exception as e:
        print(f"❌ 녹음 시작 실패: {e}")
        record_start_time = time.time()

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

            # 파일이 실제로 생겼는지 확인
            if os.path.exists(filename):
                print(f"  > 저장 완료: {os.path.basename(filename)}")
                taken_files.append(filename)
            else:
                print(f"  ⚠️ 파일 생성 안됨: {filename}")
            time.sleep(1)

        except subprocess.CalledProcessError:
            print(f"  ❌ {name} 촬영 실패 (권한 또는 하드웨어 오류)")

    # -----------------------------------------------
    # ⏳ 4. 남은 시간 대기 및 녹음 종료
    # -----------------------------------------------
    elapsed_time = time.time() - record_start_time
    remaining_time = RECORD_SECONDS - elapsed_time

    if remaining_time > 0:
        print(f"⏳ 남은 {remaining_time:.1f}초 대기 후 녹음 종료...")
        time.sleep(remaining_time)
    else:
        print("⏳ 시간이 초과되어 즉시 종료합니다.")

    # 녹음 종료 명령
    subprocess.run(
        ["termux-microphone-record", "-q"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)  # 파일 저장 마무리를 위해 잠시 대기

    # -----------------------------------------------
    # 📂 녹음 파일 확인 (수정: 이동 로직 삭제)
    # -----------------------------------------------
    # 이미 final_audio 위치에 저장되었으므로 존재 여부만 확인하면 됩니다.
    if os.path.exists(final_audio):
        print(f"✅ 녹음 파일 확인 완료: {os.path.basename(final_audio)}")
        taken_files.append(final_audio)
    else:
        print(f"❌ 녹음 파일이 생성되지 않았습니다: {final_audio}")

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
        os.makedirs("/sdcard/Documents/termux", exist_ok=True)
        take_selfie()
    finally:
        release_wake_lock()
        print("🔓 Wake Lock 해제 완료.")
