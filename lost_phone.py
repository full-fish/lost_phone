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
        # 🚨 수정: 60초 동안 프로세스를 기다립니다.
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        if proc.returncode == 0:
            return stdout, True
        else:
            return None, False
    except subprocess.TimeoutExpired:
        # 🚨 60초가 지나면 파이썬이 프로세스를 종료시킵니다.
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
# 🛰️ 위치 정보 획득 함수 (안정적인 60초 대기)
# =========================================================
def get_best_location():
    # 🚨 수정: 단일 요청으로 60초를 기다리도록 단순화
    LONG_TIMEOUT_SEC = 60
    print(f"🛰️ 위치 정보 탐색 시작 (최대 {LONG_TIMEOUT_SEC}초 대기)...")

    # 옵션 없이 termux-location을 호출하여 OS가 GPS와 네트워크 중 가장 좋은 결과를 찾도록 합니다.
    location_output, success = run_command_with_timeout(
        ["termux-location"], LONG_TIMEOUT_SEC
    )

    if success and location_output:
        try:
            info = format_location_info(json.loads(location_output))
            print("  ✅ 위치 확보 성공.")
            return f"위치 정보 (GPS 또는 네트워크):\n{info}"
        except json.JSONDecodeError:
            pass

    print(
        f"  ❌ 위치 탐색 실패. (최대 {LONG_TIMEOUT_SEC}초 동안 위치 정보를 얻지 못함)"
    )
    return "위치 정보 획득 실패 (응답 없음)"


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
# 🔍 최신 녹음 파일 찾기 함수
# =========================================================
def find_latest_recording(search_dir="/sdcard/"):
    # TermuxAudioRecording*.m4a 패턴으로 파일 검색
    pattern = os.path.join(search_dir, "TermuxAudioRecording*.m4a")
    files = glob.glob(pattern)

    if not files:
        return None

    # 수정 시간 기준으로 정렬하여 가장 최신 파일 반환
    latest_file = max(files, key=os.path.getmtime)
    return latest_file


# =========================================================
# 📷 메인 촬영 및 녹음 함수
# =========================================================
def take_selfie():
    target_dir = "/sdcard/Documents/termux"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    taken_files = []

    # -----------------------------------------------
    # 🎙️ 1. 오디오 녹음 시작 (파일명 지정 안 함 -> 기본 이름 사용)
    # -----------------------------------------------
    audio_proc = None
    final_audio = f"{target_dir}/{timestamp}_audio.m4a"

    print(f"🎙️ 30초 녹음 시작 (기본 파일명 사용)...")
    try:
        # 🚨 수정: -f 옵션을 제거하여 Termux가 알아서 저장하게 둠
        audio_proc = subprocess.Popen(
            ["termux-microphone-record", "-d", "30"],
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
    # ⏳ 4. 녹음 완료 대기 및 파일 찾아서 이동 (핵심 수정)
    # -----------------------------------------------
    if audio_proc:
        print("⏳ 녹음 완료 대기 중 (최대 30초)...")
        audio_proc.wait()

        # 🚨 수정: 폰 루트(/sdcard/)에서 가장 최근에 생긴 TermuxAudio... 파일을 찾음
        latest_rec = find_latest_recording("/sdcard/")

        if latest_rec and os.path.exists(latest_rec):
            try:
                # 찾은 파일을 우리가 원하는 곳으로 이동 및 이름 변경
                shutil.move(latest_rec, final_audio)
                print(
                    f"✅ 녹음 파일 발견 및 이동 완료: {os.path.basename(final_audio)}"
                )
                taken_files.append(final_audio)
            except Exception as e:
                print(f"❌ 녹음 파일 이동 실패: {e}")
        else:
            # 혹시 Termux 홈에 저장됐나 한 번 더 확인
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
