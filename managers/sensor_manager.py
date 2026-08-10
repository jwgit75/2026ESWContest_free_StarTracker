"""
managers/sensor_manager.py

StarTracker Sensor Manager

현재 지원:
- GY-NEO6MV2 GNSS
    - Latitude
    - Longitude
    - Altitude
    - UTC
    - Satellite Count
    - Fix Status

추후 추가 예정:
- Dual MPU-6500
- QMC5883L Compass
"""

import math
import threading
import time as time_module
from datetime import datetime, timedelta, timezone
from typing import Optional

import pynmea2
import serial

import config


def _signed_int16(low: int, high: int) -> int:
    """Decode a little-endian two's-complement 16-bit integer."""
    value = ((int(high) & 0xFF) << 8) | (int(low) & 0xFF)
    return value - 0x10000 if value & 0x8000 else value


class QMC5883L:
    """Minimal QMC5883L compass driver for heading measurement."""

    STATUS_REG = 0x06
    DATA_REGISTER = 0x00
    CONTROL_REG = 0x09

    def __init__(
        self,
        bus_number: int = 1,
        address: int = 0x0D,
        bus_factory=None,
        sleep: callable = time_module.sleep,
    ) -> None:
        self.bus_number = int(bus_number)
        self.address = int(address)
        self._bus_factory = bus_factory
        self._sleep = sleep
        self._bus = None
        self.initialized = False

    def initialize(self) -> None:
        """Open I2C and configure the compass for continuous measurement."""

        if self.initialized:
            return

        if self._bus_factory is None:
            try:
                from smbus2 import SMBus
            except ImportError as error:
                raise RuntimeError(
                    "smbus2 is required for QMC5883L compass access."
                ) from error

            self._bus_factory = SMBus

        self._bus = self._bus_factory(self.bus_number)

        # Continuous measurement mode, 2 gauss range, 200 Hz output rate.
        self._bus.write_byte_data(
            self.address,
            self.CONTROL_REG,
            0x1D,
        )

        self._sleep(0.01)
        self.initialized = True

    def read_heading(self) -> float:
        """Read the current heading in degrees from the compass."""

        if not self.initialized or self._bus is None:
            raise RuntimeError("QMC5883L is not initialized.")

        status = self._bus.read_byte_data(self.address, self.STATUS_REG)
        if not (status & 0x01):
            raise RuntimeError("Compass data not ready.")

        data = self._bus.read_i2c_block_data(
            self.address,
            self.DATA_REGISTER,
            6,
        )

        x = _signed_int16(data[0], data[1])
        y = _signed_int16(data[2], data[3])
        z = _signed_int16(data[4], data[5])

        heading = math.degrees(math.atan2(y, x))
        if heading < 0.0:
            heading += 360.0

        return heading

    def close(self) -> None:
        """Close the I2C bus if it was opened."""

        if self._bus is None:
            return

        try:
            self._bus.close()
        except Exception:
            pass

        self._bus = None
        self.initialized = False


class SensorManager:
    """StarTracker의 센서 데이터를 통합 관리한다."""

    def __init__(self):

        # ==================================================
        # GNSS
        # ==================================================

        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: Optional[float] = None

        self.utc: Optional[datetime] = None
        self._utc_reference_monotonic: Optional[float] = None

        self.satellites = 0
        self.fix_quality = 0

        # ==================================================
        # 추후 IMU / Compass용
        # ==================================================

        self.heading: Optional[float] = None

        self.pitch: Optional[float] = None
        self.roll: Optional[float] = None

        # ==================================================
        # Internal
        # ==================================================

        self.serial_port: Optional[serial.Serial] = None

        self._compass: Optional[QMC5883L] = None
        self._compass_thread: Optional[threading.Thread] = None

        self.running = False

        self._reader_thread: Optional[threading.Thread] = None

        self._data_lock = threading.Lock()

        # 유효한 GNSS Fix를 얻으면 set
        self._fix_event = threading.Event()

        # 유효한 RMC UTC를 얻으면 set
        self._utc_event = threading.Event()

        # 종료 신호
        self._stop_event = threading.Event()

    # ==================================================
    # Initialize
    # ==================================================

    def initialize(self) -> bool:
        """GNSS UART를 열고 백그라운드 수신 스레드를 시작한다."""

        if self.running:
            print("[Sensor] Already initialized.")
            return True

        try:

            self.serial_port = serial.Serial(
                port=config.GNSS_PORT,
                baudrate=config.GNSS_BAUDRATE,
                timeout=config.GNSS_READ_TIMEOUT,
            )

        except serial.SerialException as error:

            print(
                f"[Sensor] GNSS Serial Open Failed: {error}"
            )

            return False

        self._stop_event.clear()
        self._fix_event.clear()
        self._utc_event.clear()

        with self._data_lock:
            self.utc = None
            self._utc_reference_monotonic = None
            self.heading = None

        self.running = True

        if config.COMPASS_ENABLED:
            try:
                self._compass = QMC5883L(
                    bus_number=config.COMPASS_I2C_BUS,
                    address=config.COMPASS_ADDRESS,
                )
                self._compass.initialize()
            except Exception as error:
                print(
                    f"[Sensor] Compass initialization failed: {error}"
                )
                self._compass = None

        self._reader_thread = threading.Thread(
            target=self._gnss_reader_loop,
            name="GNSSReader",
            daemon=True,
        )

        self._reader_thread.start()

        if (
            config.COMPASS_ENABLED
            and self._compass is not None
        ):
            self._compass_thread = threading.Thread(
                target=self._compass_reader_loop,
                name="CompassReader",
                daemon=True,
            )
            self._compass_thread.start()

        print(
            f"[Sensor] GNSS Started: "
            f"{config.GNSS_PORT} @ "
            f"{config.GNSS_BAUDRATE} baud"
        )

        if self._compass is not None:
            print("[Sensor] Compass Started")

        return True

    # ==================================================
    # GNSS Reader Loop
    # ==================================================

    def _gnss_reader_loop(self) -> None:
        """UART에서 NMEA 문장을 계속 읽는다."""

        while (
            self.running
            and not self._stop_event.is_set()
        ):

            try:

                if self.serial_port is None:
                    break

                raw_line = self.serial_port.readline()

                if not raw_line:
                    continue

                line = raw_line.decode(
                    "ascii",
                    errors="ignore",
                ).strip()

                if not line.startswith("$"):
                    continue

                try:

                    message = pynmea2.parse(line)

                except pynmea2.ParseError:
                    continue

                self._process_nmea(message)

            except serial.SerialException as error:

                print(
                    f"[Sensor] GNSS Serial Error: {error}"
                )

                break

            except Exception as error:

                print(
                    f"[Sensor] GNSS Read Warning: {error}"
                )

        self.running = False

        print("[Sensor] GNSS Reader Ended")

    # ==================================================
    # Compass Reader

    def _compass_reader_loop(self) -> None:
        """주기적으로 QMC5883L에서 heading 값을 읽는다."""

        while (
            self.running
            and not self._stop_event.is_set()
            and self._compass is not None
        ):

            try:
                heading = self._compass.read_heading()

                with self._data_lock:
                    self.heading = heading

            except Exception as error:
                print(
                    f"[Sensor] Compass Read Warning: {error}"
                )

            time_module.sleep(
                config.COMPASS_UPDATE_INTERVAL_SECONDS
            )

        print("[Sensor] Compass Reader Ended")

    # ==================================================
    # Process NMEA
    # ==================================================

    def _process_nmea(self, message) -> None:
        """GGA와 RMC 문장에서 필요한 GNSS 정보를 추출한다."""

        sentence_type = getattr(
            message,
            "sentence_type",
            "",
        )

        # --------------------------------------------------
        # GGA
        #
        # 위치 / 고도 / Fix / 위성 수
        # --------------------------------------------------

        if sentence_type == "GGA":

            try:

                fix_quality = int(
                    message.gps_qual or 0
                )

            except (ValueError, TypeError):

                fix_quality = 0

            try:

                satellites = int(
                    message.num_sats or 0
                )

            except (ValueError, TypeError):

                satellites = 0

            with self._data_lock:

                self.fix_quality = fix_quality
                self.satellites = satellites

                if fix_quality > 0:

                    latitude = float(message.latitude)
                    longitude = float(message.longitude)

                    try:
                        altitude = float(message.altitude)

                    except (ValueError, TypeError):
                        altitude = 0.0

                    self.latitude = latitude
                    self.longitude = longitude
                    self.altitude = altitude

                    self._fix_event.set()

        # --------------------------------------------------
        # RMC
        #
        # 위치 / 날짜 / UTC
        # --------------------------------------------------

        elif sentence_type == "RMC":

            # A = Valid
            # V = Invalid
            status = getattr(
                message,
                "status",
                "V",
            )

            if status != "A":
                return

            with self._data_lock:

                try:

                    self.latitude = float(
                        message.latitude
                    )

                    self.longitude = float(
                        message.longitude
                    )

                except (ValueError, TypeError):
                    pass

                # RMC는 날짜 + UTC 시간을 둘 다 제공
                try:

                    if (
                        message.datestamp is not None
                        and
                        message.timestamp is not None
                    ):

                        utc_datetime = datetime.combine(
                            message.datestamp,
                            message.timestamp,
                        )

                        # GNSS 시간은 UTC
                        self.utc = utc_datetime.replace(
                            tzinfo=timezone.utc
                        )
                        self._utc_reference_monotonic = (
                            time_module.monotonic()
                        )

                        self._utc_event.set()

                except Exception:
                    pass

    # ==================================================
    # Wait For GNSS Fix
    # ==================================================

    def wait_for_fix(
        self,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        유효한 GNSS 위치를 얻을 때까지 기다린다.

        성공:
            True

        시간 초과:
            False
        """

        if timeout is None:
            timeout = config.GNSS_FIX_TIMEOUT

        print(
            f"[Sensor] Waiting for GNSS Fix "
            f"(timeout={timeout}s)..."
        )

        deadline = time_module.monotonic() + timeout

        position_success = self._fix_event.wait(timeout)

        if position_success:

            remaining = max(
                0.0,
                deadline - time_module.monotonic(),
            )

            utc_success = self._utc_event.wait(remaining)

            if not utc_success:
                print("[Sensor] GNSS UTC acquisition timeout")
                return False

            location = self.get_location()

            if location is not None:

                latitude, longitude, altitude = location

                print("[Sensor] GNSS Fix Acquired")

                print(
                    f"[Sensor] Latitude  : "
                    f"{latitude:.6f}"
                )

                print(
                    f"[Sensor] Longitude : "
                    f"{longitude:.6f}"
                )

                print(
                    f"[Sensor] Altitude  : "
                    f"{altitude:.1f} m"
                )

                print(
                    f"[Sensor] Satellites: "
                    f"{self.get_satellites()}"
                )

            return True

        print("[Sensor] GNSS Fix Timeout")

        return False

    # ==================================================
    # GNSS Fix Status
    # ==================================================

    def has_fix(self) -> bool:

        return self._fix_event.is_set()

    # ==================================================
    # Get Location
    # ==================================================

    def get_location(
        self,
    ) -> Optional[tuple[float, float, float]]:
        """
        반환:
            (latitude, longitude, altitude)

        Fix가 없으면:
            None
        """

        with self._data_lock:

            if (
                self.latitude is None
                or
                self.longitude is None
            ):
                return None

            altitude = (
                self.altitude
                if self.altitude is not None
                else 0.0
            )

            return (
                self.latitude,
                self.longitude,
                altitude,
            )

    # ==================================================
    # Get UTC
    # ==================================================

    def get_utc(self) -> Optional[datetime]:

        with self._data_lock:

            if (
                self.utc is None
                or self._utc_reference_monotonic is None
            ):
                return None

            # GNSS RMC는 보통 1 Hz이므로 마지막 GNSS UTC를 monotonic
            # clock으로 보간하여 Tracking Loop에 연속적인 UTC를 제공한다.
            elapsed = max(
                0.0,
                time_module.monotonic()
                - self._utc_reference_monotonic,
            )

            return self.utc + timedelta(seconds=elapsed)

    # ==================================================
    # Get Satellite Count
    # ==================================================

    def get_satellites(self) -> int:

        with self._data_lock:
            return self.satellites

    # ==================================================
    # Get Fix Quality
    # ==================================================

    def get_fix_quality(self) -> int:

        with self._data_lock:
            return self.fix_quality

    # ==================================================
    # Get Sensor Snapshot
    # ==================================================

    def get_snapshot(self) -> dict:
        """현재 센서 상태 전체를 복사해서 반환한다."""

        with self._data_lock:

            return {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "altitude": self.altitude,
                "utc": self.utc,
                "satellites": self.satellites,
                "fix_quality": self.fix_quality,

                # 추후 센서
                "heading": self.heading,
                "pitch": self.pitch,
                "roll": self.roll,
            }

    # ==================================================
    # Future: Compass
    # ==================================================

    def get_heading(self) -> Optional[float]:

        with self._data_lock:
            return self.heading

    # ==================================================
    # Future: IMU
    # ==================================================

    def get_attitude(
        self,
    ) -> tuple[Optional[float], Optional[float]]:

        with self._data_lock:

            return (
                self.pitch,
                self.roll,
            )

    # ==================================================
    # Stop
    # ==================================================

    def stop(self) -> None:
        """GNSS 수신을 중단한다."""

        self.running = False
        self._stop_event.set()

        if (
            self._reader_thread is not None
            and self._reader_thread.is_alive()
            and self._reader_thread
            is not threading.current_thread()
        ):

            self._reader_thread.join(timeout=2.0)

        if (
            self._compass_thread is not None
            and self._compass_thread.is_alive()
            and self._compass_thread
            is not threading.current_thread()
        ):

            self._compass_thread.join(timeout=2.0)

        if self.serial_port is not None:

            try:
                self.serial_port.close()

            except Exception:
                pass

            self.serial_port = None

        if self._compass is not None:

            try:
                self._compass.close()

            except Exception:
                pass

            self._compass = None

        print("[Sensor] Stopped")

    # ==================================================
    # Shutdown
    # ==================================================

    def shutdown(self) -> None:

        self.stop()
