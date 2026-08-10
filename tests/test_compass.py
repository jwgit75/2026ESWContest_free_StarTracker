import math
import unittest

from managers.sensor_manager import QMC5883L, _signed_int16


class FakeBus:
    def __init__(self, data):
        self.data = data

    def read_byte_data(self, address, register):
        return 0x01

    def read_i2c_block_data(self, address, register, length):
        return self.data


class CompassTests(unittest.TestCase):
    def test_read_heading_raises_for_incomplete_data(self):
        compass = QMC5883L(bus_factory=lambda _: FakeBus([0x01, 0x02, 0x03]))
        compass.initialized = True

        with self.assertRaises(RuntimeError) as context:
            compass.read_heading()

        self.assertIn("incomplete data", str(context.exception))

    def test_read_heading_returns_heading_for_valid_data(self):
        compass = QMC5883L(bus_factory=lambda _: FakeBus([0x01, 0x02, 0x03, 0x04, 0x05, 0x06]))
        compass.initialized = True

        heading = compass.read_heading()

        self.assertIsInstance(heading, float)
        self.assertGreaterEqual(heading, 0.0)
        self.assertLess(heading, 360.0)

    def test_signed_int16_decodes_values(self):
        self.assertEqual(_signed_int16(0x00, 0x01), 1)
        self.assertEqual(_signed_int16(0xFF, 0xFF), -1)


if __name__ == "__main__":
    unittest.main()
