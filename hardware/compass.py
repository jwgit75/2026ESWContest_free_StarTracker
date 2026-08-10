class QMC5883L:
    I2C_ADDRESS = 0x0D
    CONTROL_REG = 0x09
    STATUS_REG = 0x06
    DATA_START = 0x00

    def __init__(self, bus_number=1, address=I2C_ADDRESS, bus_factory=None):
        self.bus_number = bus_number
        self.address = address
        self.bus_factory = bus_factory
        self._bus = None
        self.initialized = False

    def initialize(self):
        if self.initialized:
            return
        if self.bus_factory is None:
            from smbus2 import SMBus
            self.bus_factory = SMBus
        self._bus = self.bus_factory(self.bus_number)
        # continuous measurement mode, 2 gauss, 200Hz
        self._bus.write_byte_data(self.address, self.CONTROL_REG, 0x1D)
        time.sleep(0.01)
        self.initialized = True

    def read_heading(self):
        if not self.initialized:
            raise RuntimeError("Compass is not initialized.")
        status = self._bus.read_byte_data(self.address, self.STATUS_REG)
        if not (status & 0x01):
            raise RuntimeError("Compass data not ready.")
        data = self._bus.read_i2c_block_data(self.address, self.DATA_START, 6)
        x = signed_int16(data[0], data[1])
        y = signed_int16(data[2], data[3])
        z = signed_int16(data[4], data[5])
        heading = math.degrees(math.atan2(y, x))
        if heading < 0:
            heading += 360.0
        return heading

    def close(self):
        if self._bus:
            self._bus.close()
            self._bus = None
            self.initialized = False