import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import configparser  # 🚨 configparser 라이브러리 추가


def send_photo_email(filename, subject_text):
    # 1. 설정 파일 (config.ini) 읽어오기
    config = configparser.ConfigParser()

    # config.ini 파일이 없으면 오류 메시지를 출력하고 종료합니다.
    if not config.read("config.ini"):
        print("❌ 오류: config.ini 파일을 찾거나 읽을 수 없습니다.")
        return False

    # EMAIL_CONFIG 섹션의 설정을 가져옵니다.
    settings = config["EMAIL_CONFIG"]

    # 2. 변수에 값 할당
    SMTP_SERVER = settings.get("smtp_server")
    SMTP_PORT = settings.getint("smtp_port")  # 포트는 숫자로 가져옵니다.
    SENDER_EMAIL = settings.get("sender_email")
    APP_PASSWORD = settings.get("app_password")
    RECIPIENT_EMAIL = settings.get("recipient_email")

    # =================================================

    # 3. 메일 내용 구성
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = subject_text

    # 4. 본문 추가
    body = "첨부된 파일은 침입자 감지 카메라가 촬영한 사진입니다."
    msg.attach(MIMEText(body, "plain"))

    # 5. 첨부 파일 추가 (기존 코드와 동일)
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

        except Exception as e:
            print(f"❌ 파일 첨부 오류: {e}")
            return False
    else:
        print(f"❌ 첨부할 파일이 존재하지 않습니다: {filename}")
        return False

    # 6. SMTP 서버 접속 및 전송
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print("✅ 이메일 전송 성공!")
        return True
    except Exception as e:
        print(f"❌ 이메일 전송 실패 (SMTP 오류): {e}")
        return False


# ... (take_selfie 함수 및 main 부분은 그대로 유지)
