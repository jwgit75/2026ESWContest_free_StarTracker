"""
config.py

StarTracker 전체 설정

현재 기준 하드웨어:
- Raspberry Pi 5
- 17HM19-2004S, 0.9°/full step
- TMC2209, 1/32 microstep
- AZ : STEP BCM 22 / DIR BCM 27
- ALT: STEP BCM 10 / DIR BCM 9
- Raspberry Pi HQ Camera + 16 mm Lens
- GY-NEO6MV2 GNSS
- Astrometry.net Offline Plate Solving
"""


# =========================================================
# Motor Mechanical Specification
# =========================================================

# 17HM19-2004S
MOTOR_FULL_STEP_ANGLE = 0.9

# 360° / 0.9° = 400 full steps
MOTOR_FULL_STEPS_PER_REVOLUTION = 400

# TMC2209 마이크로스텝 설정
MICROSTEP = 32

# 최종 기계 감속비
GEAR_RATIO = 27.0

# 모터 마이크로스텝 1회당 최종 출력축 이동 각도
#
# 0.9 / 32 / 27
# = 약 0.00104167°
STEP_ANGLE = (
    MOTOR_FULL_STEP_ANGLE
    / MICROSTEP
    / GEAR_RATIO
)

# 최종 출력축을 1° 움직이는 데 필요한 스텝 수
#
# 약 960 steps/degree
STEPS_PER_DEGREE = 1.0 / STEP_ANGLE


# =========================================================
# Motor GPIO
#
# 실제 BLE 조이스틱 2축 테스트에서 동작 확인된 핀
# BCM 번호 기준
# =========================================================

# AZ 축
MOTOR_BASE_STEP_PIN = 22
MOTOR_BASE_DIR_PIN = 27

# EL 축을 프로젝트에서는 ALT 축으로 사용
MOTOR_MOUNT_STEP_PIN = 10
MOTOR_MOUNT_DIR_PIN = 9


# =========================================================
# Optional Motor Driver GPIO
# =========================================================

# 현재 실제 작동 테스트에서는 STEP/DIR만 사용했으므로
# 연결이 확인되기 전까지 None으로 유지한다.
MOTOR_ENABLE_PIN = None
MOTOR_MS1_PIN = None
MOTOR_MS2_PIN = None

MOTOR_ENABLE_ACTIVE_LOW = True

# 마이크로스텝 핀 조합은 현재 소프트웨어에서 변경하지 않는다.
# TMC2209 하드웨어 설정을 그대로 사용한다.
DEFAULT_MOTOR_MODE = None
MICROSTEP_MODE_TABLE = {}


# =========================================================
# Motor Pulse
# =========================================================

# Tracking에서 사용하는 STEP 신호의 HIGH/LOW 각각의 시간
#
# 실제 수동 테스트에서는
# 0.003 / 0.0015 / 0.0007초가 동작했다.
# Tracking 기본값은 비교적 안정적인 0.001초로 사용한다.
MOTOR_PULSE_DELAY = 0.001


# =========================================================
# Motor Position Control
# =========================================================

# Tracking Loop 한 번에 축별로 이동할 최대 스텝 수
MAX_STEP_PER_UPDATE = 5

# 목표에 도달했다고 판단할 각도 오차
ANGLE_TOLERANCE = 0.03

# ALT 출력축 안전 범위
MIN_ALTITUDE = 0.0
MAX_ALTITUDE = 90.0


# =========================================================
# Tracking
# =========================================================

# Tracking Loop 주기
# 0.05초 = 20 Hz
TRACKING_INTERVAL = 0.05

# Plate Solving 보정 간격
CORRECTION_INTERVAL = 120.0

# 성공한 보정 횟수가 이 값에 도달하면 자동 촬영 단계로 이동
MAX_CORRECTION_COUNT = 15


# =========================================================
# Tracking Log
# =========================================================

# 세션마다 Tracking Log와 Plate Solving 결과 JSON을 저장한다.
TRACKING_LOG_DIRECTORY = "data/logs"


# =========================================================
# Camera
# =========================================================

CAMERA_IMAGE_WIDTH = 4056
CAMERA_IMAGE_HEIGHT = 3040
CAMERA_FORMAT = "RGB888"

# 카메라 시작 후 안정화 시간
CAMERA_WARMUP_SECONDS = 2.0

# 노출과 Gain 설정 후 적용 대기 시간
CAMERA_CONTROL_SETTLE_SECONDS = 0.5


# =========================================================
# Plate Solving Image Capture
# =========================================================

PLATE_IMAGE_PATH = "data/images/plate_current.jpg"

PLATE_EXPOSURE_SECONDS = 5.0
PLATE_ANALOGUE_GAIN = 4.0


# =========================================================
# Final Image Capture
# =========================================================

FINAL_IMAGE_PATH = "data/images/final_result.jpg"

# 현재 알고리즘상의 최종 장노출 시간
LONG_EXPOSURE_SECONDS = 180.0
LONG_EXPOSURE_ANALOGUE_GAIN = 2.0


# =========================================================
# Astrometry.net Plate Solving
#
# 기존 Raspberry Pi HQ Camera + 16 mm 렌즈 환경에서
# index 4115로 성공했던 설정을 유지한다.
# =========================================================

PLATE_SCALE_UNITS = "degwidth"

# Raspberry Pi HQ Camera의 전체 센서와 16 mm 렌즈 조합은
# 가로 시야각이 약 22도이므로 그 주변을 우선 검색한다.
# 실제 장착 상태에서 측정한 시야각이 다르면 이 범위를 조정한다.
PLATE_SCALE_LOW = 15.0
PLATE_SCALE_HIGH = 30.0

PLATE_DOWNSAMPLE = 4

# solve-field 최대 실행 대기 시간
PLATE_SOLVE_TIMEOUT = 60.0


# =========================================================
# GNSS
# =========================================================

GNSS_PORT = "/dev/serial0"
GNSS_BAUDRATE = 9600
GNSS_READ_TIMEOUT = 1.0

# 유효한 위치 Fix 최대 대기 시간
GNSS_FIX_TIMEOUT = 60.0
