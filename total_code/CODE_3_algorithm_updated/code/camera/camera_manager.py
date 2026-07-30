"""
camera/camera_manager.py

Raspberry Pi HQ Camera Manager

담당 기능:
- 카메라 초기화
- Plate Solving용 이미지 촬영
- 최종 장노출 촬영
- 카메라 자원 종료
"""

import threading
import time
from pathlib import Path
from typing import Optional

from picamera2 import Picamera2

import config


class CameraManager:
    """Raspberry Pi HQ Camera의 촬영 작업을 관리한다."""

    def __init__(self):

        self.camera: Optional[Picamera2] = None
        self.initialized = False

        # 두 스레드가 카메라를 동시에 사용하는 것을 방지
        self._camera_lock = threading.Lock()

    # ==================================================
    # Initialize
    # ==================================================

    def initialize(self) -> None:
        """카메라를 생성하고 Plate Solving 촬영 설정으로 시작한다."""

        with self._camera_lock:

            if self.initialized:
                return

            self.camera = Picamera2()

            plate_config = self.camera.create_still_configuration(
                main={
                    "size": (
                        config.CAMERA_IMAGE_WIDTH,
                        config.CAMERA_IMAGE_HEIGHT,
                    ),
                    "format": config.CAMERA_FORMAT,
                },
                buffer_count=2,
            )

            self.camera.configure(plate_config)
            self.camera.start()

            time.sleep(config.CAMERA_WARMUP_SECONDS)

            self.initialized = True

            print("[Camera] Ready")

    # ==================================================
    # Plate Solving Capture
    # ==================================================

    def capture_plate(
        self,
        filename: Optional[str] = None,
    ) -> str:
        """Plate Solving에 사용할 이미지를 촬영한다."""

        self._require_initialized()

        if filename is None:
            filename = config.PLATE_IMAGE_PATH

        filepath = Path(filename)
        filepath.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._camera_lock:

            self.camera.set_controls(
                {
                    "AeEnable": False,
                    "ExposureTime": int(
                        config.PLATE_EXPOSURE_SECONDS
                        * 1_000_000
                    ),
                    "AnalogueGain": config.PLATE_ANALOGUE_GAIN,
                }
            )

            # 설정 반영 대기
            time.sleep(config.CAMERA_CONTROL_SETTLE_SECONDS)

            self.camera.capture_file(str(filepath))

        print(f"[Camera] Plate image saved: {filepath}")

        return str(filepath)

    # ==================================================
    # Long Exposure Capture
    # ==================================================

    def capture_long_exposure(
        self,
        filename: Optional[str] = None,
        exposure_time: Optional[float] = None,
    ) -> str:
        """최종 결과용 장노출 이미지를 촬영한다."""

        self._require_initialized()

        if filename is None:
            filename = config.FINAL_IMAGE_PATH

        if exposure_time is None:
            exposure_time = config.LONG_EXPOSURE_SECONDS

        if exposure_time <= 0:
            raise ValueError(
                "exposure_time must be greater than zero."
            )

        filepath = Path(filename)
        filepath.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        exposure_microseconds = int(
            exposure_time * 1_000_000
        )

        with self._camera_lock:

            self.camera.set_controls(
                {
                    "AeEnable": False,
                    "ExposureTime": exposure_microseconds,
                    "AnalogueGain": config.LONG_EXPOSURE_ANALOGUE_GAIN,
                }
            )

            time.sleep(config.CAMERA_CONTROL_SETTLE_SECONDS)

            print(
                "[Camera] Long exposure started: "
                f"{exposure_time:.1f} sec"
            )

            # capture_file은 노출 및 파일 저장이 끝날 때까지 대기
            self.camera.capture_file(str(filepath))

        print(f"[Camera] Final image saved: {filepath}")

        return str(filepath)

    # ==================================================
    # Stop
    # ==================================================

    def stop(self) -> None:
        """카메라를 안전하게 정지한다."""

        with self._camera_lock:

            if self.camera is None:
                return

            try:
                if self.camera.started:
                    self.camera.stop()

            except Exception as error:
                print(f"[Camera] Stop warning: {error}")

            finally:
                try:
                    self.camera.close()
                except Exception:
                    pass

                self.camera = None
                self.initialized = False

        print("[Camera] Stopped")

    # ==================================================
    # Internal Validation
    # ==================================================

    def _require_initialized(self) -> None:

        if not self.initialized or self.camera is None:
            raise RuntimeError(
                "CameraManager is not initialized. "
                "Call initialize() first."
            )