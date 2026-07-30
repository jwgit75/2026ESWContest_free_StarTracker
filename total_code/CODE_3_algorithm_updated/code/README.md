# Star Tracker

Raspberry Pi 5에서 HQ Camera, GNSS, BLE 조이스틱과 ALT/AZ 스테퍼 모터를
사용하는 별 추적 프로그램입니다.

## 준비

Raspberry Pi OS에서 카메라와 GPIO 패키지를 먼저 설치합니다.

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-rpi-lgpio astrometry.net
```

프로젝트의 일반 Python 의존성을 설치합니다.

```bash
python3 -m pip install -r requirements.txt
```

Astrometry.net 인덱스 파일은 촬영 시야각에 맞는 것을 별도로 설치해야 합니다.
현재 `config.py`는 HQ Camera 전체 센서와 16 mm 렌즈의 약 22도 가로 시야각을
기준으로 15~30도를 검색합니다. 실제 장착 상태에서 측정한 시야각이 다르면
`PLATE_SCALE_LOW`와 `PLATE_SCALE_HIGH`를 조정하십시오.

## 실행

UART와 카메라 인터페이스를 활성화하고 이 디렉터리에서 실행합니다.

```bash
python3 main.py
```

기본 GNSS 포트는 `/dev/serial0`, 통신 속도는 9600 baud입니다. GPIO 핀,
기어비, 회전 방향 및 고도 소프트 리밋은 실제 기구에 맞춰 `config.py`에서
확인해야 합니다.

## 동작 순서

1. GNSS의 GGA 위치/고도와 RMC UTC를 모두 획득합니다.
2. Camera와 Motor를 초기화하고 BLE 조이스틱에 연결합니다.
3. `MANUAL` 상태에서 VNC 화면을 보며 조이스틱으로 구도를 맞춥니다.
4. 조이스틱 SW 버튼을 누르면 `TARGET_CAPTURE` 상태에서 첫 사진을 촬영하고
   Offline Plate Solving으로 Target RA/Dec를 저장합니다.
5. `TRACKING` 상태에서 현재 UTC 기준 Target Alt/Az를 계산하여 모터를
   연속 제어합니다.
6. Tracking 시작 시각 기준 120초마다 `DRIFT_CORRECTION`을 실행하며,
   성공한 보정 15회를 완료할 때까지 반복합니다.
7. 모터 Tracking을 유지한 채 최종 장노출 사진을 저장합니다.
8. Tracking Log와 모든 Plate Solving 수치 결과를 `data/logs`에 JSON으로
   저장하고 다시 `MANUAL` 상태로 돌아갑니다.

첫 Plate Solving 시작 중에는 CODE_3의 BLE 중복 방지 로직이 같은 시작
스레드가 두 번 생성되는 것을 막습니다. 추적 또는 보정 중 SW 버튼을 다시
누르면 현재 세션을 중단하고 `MANUAL` 상태로 복귀합니다.

VNC 서버는 Raspberry Pi OS 서비스로 미리 실행되어 있다고 가정합니다.
현재 코드에는 IMU와 Compass 드라이버가 포함되어 있지 않습니다. IMU는 현재
추적 알고리즘에 필수적이지 않으며, Compass 초기화는 사용할 센서 모델과 보정
방식이 확정된 뒤 추가해야 합니다. 안전상 기준 위치와 회전 방향이 확인되지 않은
상태에서 자동 모터 왕복 테스트는 수행하지 않습니다.

## 안전 주의사항

- ALT 0~90도 제한은 소프트웨어가 추정한 위치를 기준으로 합니다. 전원을 켤
  때 실제 축의 기준 위치를 맞춰야 하며, 장비 보호를 위해 물리 리미트 스위치와
  호밍 절차를 추가하는 것을 권장합니다.
- BLE 연결이 예기치 않게 끊기면 추적을 멈추고 프로그램 종료 절차로 들어갑니다.
- 실제 모터를 연결하기 전에 STEP/DIR 방향과 이동 범위를 저속으로 검증하십시오.
