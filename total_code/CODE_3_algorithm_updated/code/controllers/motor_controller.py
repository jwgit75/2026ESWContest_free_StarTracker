"""
controllers/motor_controller.py

High Level Motor Controller

- Manual Control
- GOTO
- ALT/AZ Tracking
- Drift Correction

모든 모터 명령은 이 클래스를 통해 실행한다.
"""

import threading
from enum import Enum, auto

import config

from hardware.motor import MotorDriver


class MotorMode(Enum):

    STOP = auto()
    MANUAL = auto()
    TRACKING = auto()


class MotorController:

    def __init__(self):

        self.driver = MotorDriver()

        self.mode = MotorMode.STOP

        # 소프트웨어가 추정하는 현재 출력축 각도
        self.current_alt = 0.0
        self.current_az = 0.0

        # 목표 출력축 각도
        self.target_alt = 0.0
        self.target_az = 0.0

        self.step_angle = config.STEP_ANGLE
        self.steps_per_degree = config.STEPS_PER_DEGREE

        # Tracking Thread와 Correction Thread의 동시 접근 방지
        self._motor_lock = threading.Lock()
        # 수동 조작 시 두 축을 독립적으로 움직이기 위한 Lock
        self._manual_alt_lock = threading.Lock()
        self._manual_az_lock = threading.Lock()

    # =====================================================
    # Initialize
    # =====================================================

    def initialize(self):

        self.driver.initialize()

        self.driver.set_mode(
            config.DEFAULT_MOTOR_MODE
        )

        self.driver.enable()

        self.mode = MotorMode.STOP

        print("[MotorController] Ready")

    # =====================================================
    # Manual Control
    # =====================================================

    def move_manual(
        self,
        axis: str,
        direction: bool,
        steps: int,
        pulse_delay: float = None,
    ):

        if steps <= 0:
            return

        axis = axis.upper()

        if axis == "ALT":
            axis_lock = self._manual_alt_lock

        elif axis == "AZ":
            axis_lock = self._manual_az_lock

        else:
            raise ValueError(
                "Axis must be 'ALT' or 'AZ'"
            )

        # ALT와 AZ는 서로 다른 Lock을 사용하므로
        # 조이스틱 대각선 입력 시 두 축이 동시에 움직일 수 있다.
        with axis_lock:

            # 소프트웨어 위치만 제한하면 실제 축은 0/90도 경계를 넘어
            # 계속 움직일 수 있다. 따라서 모터를 구동하기 전에 남은
            # 이동 범위로 스텝 수를 제한한다.
            if axis == "ALT":

                if direction:
                    remaining_angle = (
                        config.MAX_ALTITUDE
                        - self.current_alt
                    )
                else:
                    remaining_angle = (
                        self.current_alt
                        - config.MIN_ALTITUDE
                    )

                allowed_steps = int(
                    max(0.0, remaining_angle)
                    / self.step_angle
                )

                steps = min(steps, allowed_steps)

                if steps <= 0:
                    return

            self.mode = MotorMode.MANUAL

            self.driver.drive(
                axis=axis,
                direction=direction,
                steps=steps,
                pulse_delay=pulse_delay,
            )

            moved_angle = self.steps_to_angle(
                steps
            )

            if axis == "ALT":

                if direction:
                    self.current_alt += moved_angle
                else:
                    self.current_alt -= moved_angle

                self.current_alt = (
                    self._clamp_altitude(
                        self.current_alt
                    )
                    )
            

            else:

                if direction:
                    self.current_az += moved_angle
                else:
                    self.current_az -= moved_angle

                self.current_az = (
                    self._normalize_azimuth(
                        self.current_az
                    )
                )
    # =====================================================
    # Tracking Target
    # =====================================================

    def set_target(
        self,
        alt: float,
        az: float,
    ):

        self.mode = MotorMode.TRACKING

        self.target_alt = self._clamp_altitude(alt)
        self.target_az = self._normalize_azimuth(az)

    # 이전 코드와의 호환용
    def goto(
        self,
        alt: float,
        az: float,
    ):

        self.set_target(alt, az)

    # =====================================================
    # Current Position Synchronization
    # =====================================================

    def set_current_position(
        self,
        alt: float,
        az: float,
    ):

        with self._motor_lock:

            self.current_alt = self._clamp_altitude(alt)
            self.current_az = self._normalize_azimuth(az)

    # =====================================================
    # Tracking Update
    # =====================================================

    def update(self):

        if self.mode != MotorMode.TRACKING:
            return

        with self._motor_lock:

            alt_error = (
                self.target_alt
                - self.current_alt
            )

            # 0/360도 경계를 고려한 최단 AZ 오차
            az_error = self._shortest_azimuth_error(
                target_az=self.target_az,
                current_az=self.current_az,
            )

            alt_steps = 0
            az_steps = 0

            alt_direction = alt_error >= 0
            az_direction = az_error >= 0

            if abs(alt_error) >= config.ANGLE_TOLERANCE:

                requested_alt_steps = self.angle_to_steps(
                    abs(alt_error)
                )

                alt_steps = min(
                    requested_alt_steps,
                    config.MAX_STEP_PER_UPDATE,
                )

            if abs(az_error) >= config.ANGLE_TOLERANCE:

                requested_az_steps = self.angle_to_steps(
                    abs(az_error)
                )

                az_steps = min(
                    requested_az_steps,
                    config.MAX_STEP_PER_UPDATE,
                )

            if alt_steps == 0 and az_steps == 0:
                return

            self.driver.drive_dual(
                alt_steps=alt_steps,
                alt_direction=alt_direction,
                az_steps=az_steps,
                az_direction=az_direction,
            )

            self._apply_step_position_update(
                alt_steps=alt_steps,
                alt_direction=alt_direction,
                az_steps=az_steps,
                az_direction=az_direction,
            )

    # =====================================================
    # Internal Position Update
    # =====================================================

    def _apply_step_position_update(
        self,
        alt_steps: int,
        alt_direction: bool,
        az_steps: int,
        az_direction: bool,
    ):

        if alt_steps > 0:

            moved_alt = self.steps_to_angle(alt_steps)

            if alt_direction:
                self.current_alt += moved_alt
            else:
                self.current_alt -= moved_alt

            self.current_alt = self._clamp_altitude(
                self.current_alt
            )

        if az_steps > 0:

            moved_az = self.steps_to_angle(az_steps)

            if az_direction:
                self.current_az += moved_az
            else:
                self.current_az -= moved_az

            self.current_az = self._normalize_azimuth(
                self.current_az
            )

    # =====================================================
    # Target Check
    # =====================================================

    def reached_target(self):

        alt_error = abs(
            self.target_alt
            - self.current_alt
        )

        az_error = abs(
            self._shortest_azimuth_error(
                target_az=self.target_az,
                current_az=self.current_az,
            )
        )

        return (
            alt_error < config.ANGLE_TOLERANCE
            and
            az_error < config.ANGLE_TOLERANCE
        )

    # =====================================================
    # Stop
    # =====================================================

    def stop(self):

        self.mode = MotorMode.STOP

    # =====================================================
    # Angle / Step Conversion
    # =====================================================

    def angle_to_steps(
        self,
        angle: float,
    ) -> int:

        if angle <= 0:
            return 0

        return round(
            angle * self.steps_per_degree
        )

    def steps_to_angle(
        self,
        steps: int,
    ) -> float:

        return steps * self.step_angle

    # =====================================================
    # Angle Utilities
    # =====================================================

    @staticmethod
    def _normalize_azimuth(az: float) -> float:

        return az % 360.0

    @staticmethod
    def _clamp_altitude(alt: float) -> float:

        return max(
            config.MIN_ALTITUDE,
            min(config.MAX_ALTITUDE, alt),
        )

    @staticmethod
    def _shortest_azimuth_error(
        target_az: float,
        current_az: float,
    ) -> float:

        return (
            target_az
            - current_az
            + 180.0
        ) % 360.0 - 180.0

    # =====================================================
    # Cleanup
    # =====================================================

    def cleanup(self):

        self.mode = MotorMode.STOP

        self.driver.cleanup()
