"""
main.py

StarTracker Main Program

전체 실행 흐름:

1. GNSS 초기화
2. GNSS 위치 Fix 및 UTC 획득
3. 실제 위도 / 경도 / 고도 등록
4. GNSS UTC를 Tracking clock으로 연결
5. Camera / Motor / Astronomy 초기화
6. BLE 연결
7. 조이스틱 수동 조작
8. 조이스틱 클릭으로 Tracking Start / Stop
9. 2분마다 Plate Solving 보정
10. 15회 보정 후 Tracking을 유지하며 최종 촬영
11. Tracking/Plate Solving 로그 저장 후 Manual Mode 복귀
"""

import asyncio

import config

from communication.ble_manager import BLEManager
from managers.sensor_manager import SensorManager
from managers.tracking_manager import TrackingManager


async def run_star_tracker() -> None:

    sensor = SensorManager()
    tracking = TrackingManager()
    ble = BLEManager(tracking)

    try:

        # ==================================================
        # Program Start
        # ==================================================

        print()
        print("========================================")
        print("             STAR TRACKER")
        print("========================================")
        print()

        # ==================================================
        # 1. GNSS Initialize
        # ==================================================

        print("[Main] GNSS initialization...")

        sensor_initialized = sensor.initialize()

        if not sensor_initialized:

            print("[Main] GNSS initialization failed.")
            return

        # ==================================================
        # 2. Wait For GNSS Fix
        # ==================================================

        fix_success = sensor.wait_for_fix(
            timeout=config.GNSS_FIX_TIMEOUT
        )

        if not fix_success:

            print("[Main] GNSS Fix acquisition failed.")
            print("[Main] Move the system outdoors and restart.")
            return

        location = sensor.get_location()

        if location is None:

            print("[Main] GNSS location data is unavailable.")
            return

        latitude, longitude, altitude = location

        print()
        print("[Main] GNSS Location")
        print(f"[Main] Latitude  : {latitude:.6f}")
        print(f"[Main] Longitude : {longitude:.6f}")
        print(f"[Main] Altitude  : {altitude:.1f} m")
        print()

        # ==================================================
        # 3. GNSS UTC Provider
        # ==================================================

        tracking.set_time_provider(
            sensor.get_utc
        )

        # ==================================================
        # 4. Tracking System Initialize
        # ==================================================

        print("[Main] Tracking system initialization...")

        tracking.initialize(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
        )

        # ==================================================
        # 5. BLE Connect
        # ==================================================

        print("[Main] BLE connection...")

        ble_connected = await ble.connect()

        if not ble_connected:

            print("[Main] BLE connection failed.")
            return

        # ==================================================
        # 6. System Ready
        # ==================================================

        print()
        print("========================================")
        print("              SYSTEM READY")
        print("========================================")
        print()
        print("[Control]")
        print("Joystick X : AZ movement")
        print("Joystick Y : ALT movement")
        print("Joystick Click : Tracking Start / Stop")
        print("Ctrl+C : Program Exit")
        print()

        # ==================================================
        # 7. Main Loop
        # ==================================================

        while True:

            if not ble.running:

                print(
                    "[Main] BLE connection lost. "
                    "Stopping the system for safety."
                )

                break

            await asyncio.sleep(0.5)

    except asyncio.CancelledError:

        print("[Main] Program cancellation requested.")
        raise

    except Exception as error:

        print(f"[Main] Unexpected Error: {error}")

    finally:

        # ==================================================
        # System Shutdown
        # ==================================================

        print()
        print("[Main] System shutdown started...")

        try:

            await ble.disconnect()

        except Exception as error:

            print(
                f"[Main] BLE Shutdown Warning: {error}"
            )

        try:

            tracking.shutdown()

        except Exception as error:

            print(
                f"[Main] Tracking Shutdown Warning: {error}"
            )

        try:

            sensor.shutdown()

        except Exception as error:

            print(
                f"[Main] Sensor Shutdown Warning: {error}"
            )

        print("[Main] System shutdown complete.")


def main() -> None:

    try:

        asyncio.run(
            run_star_tracker()
        )

    except KeyboardInterrupt:

        print()
        print("[Main] Program terminated by user.")


if __name__ == "__main__":

    main()
