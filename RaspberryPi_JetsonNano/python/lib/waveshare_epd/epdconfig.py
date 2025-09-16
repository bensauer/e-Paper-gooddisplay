# /*****************************************************************************
# * | File        :   epdconfig.py
# * | Author      :   Waveshare team (edited for RPi.GPIO + spidev)
# * | Function    :   Hardware underlying interface
# * | Version     :   V1.2 (RPi.GPIO rewrite)
# * | Date        :   2022-10-29 (edited 2025-09-15)
# ******************************************************************************
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import os
import logging
import sys
import time
import subprocess
from ctypes import *

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Raspberry Pi implementation (RPi.GPIO + spidev, BUSY active-low)
# ----------------------------------------------------------------------
class RaspberryPi:
    # Pin definition (BCM numbering) — mirror your working C++ pins
    RST_PIN   = 17
    DC_PIN    = 25
    CS_PIN    = 8            # not used directly when spidev controls CS
    BUSY_PIN  = 24
    PWR_PIN   = 18

    # SPI selection: CE0 -> (bus=0, device=0), CE1 -> (bus=0, device=1)
    SPI_BUS     = 0
    SPI_DEVICE  = 0          # change to 1 if you wired CE1
    SPI_CLOCK_HZ = 4000000   # try 2_000_000 if you see signal issues

    def __init__(self):
        import RPi.GPIO as GPIO
        import spidev
        self.GPIO = GPIO
        self.SPI  = spidev.SpiDev()
        self._gpio_inited = False
        self._spi_inited  = False
        self.DEV_SPI = None  # used only when cleanup=True path is selected

    # --- GPIO helpers expected by drivers ---
    def digital_write(self, pin, value):
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        # BUSY is wired active-low on most UC8179 7.5" V2 boards
        # We return the raw GPIO level (0=LOW, 1=HIGH).
        return self.GPIO.input(pin)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    # --- SPI helpers expected by drivers ---
    def spi_writebyte(self, data):
        # accept list/bytes/bytearray
        if isinstance(data, (bytes, bytearray)):
            self.SPI.writebytes(list(data))
        else:
            self.SPI.writebytes(list(data))

    def spi_writebyte2(self, data):
        # some drivers call this variant; treat the same
        self.spi_writebyte(data)

    # --- Alternate shared-lib SPI (rarely used) ---
    def DEV_SPI_write(self, data):
        if self.DEV_SPI:
            self.DEV_SPI.DEV_SPI_SendData(data)

    def DEV_SPI_nwrite(self, data):
        if self.DEV_SPI:
            self.DEV_SPI.DEV_SPI_SendnData(data)

    def DEV_SPI_read(self):
        if self.DEV_SPI:
            return self.DEV_SPI.DEV_SPI_ReadData()
        return 0

    # --- Module lifecycle ---
    def module_init(self, cleanup=False):
        # Power pin on first so the panel is powered before SPI/RESET
        self._gpio_setup_basic()

        if cleanup:
            # Legacy path using DEV_Config_xx.so if present
            find_dirs = [
                os.path.dirname(os.path.realpath(__file__)),
                '/usr/local/lib',
                '/usr/lib',
            ]
            self.DEV_SPI = None
            val = int(os.popen('getconf LONG_BIT').read() or "64")
            so_name = 'DEV_Config_64.so' if val == 64 else 'DEV_Config_32.so'
            for d in find_dirs:
                so_path = os.path.join(d, so_name)
                if os.path.exists(so_path):
                    self.DEV_SPI = CDLL(so_path)
                    break
            if self.DEV_SPI is None:
                raise RuntimeError('Cannot find DEV_Config_xx.so')
            # Ensure SPI also opened for compatibility
            self._spi_open()
            if hasattr(self.DEV_SPI, 'DEV_Module_Init'):
                self.DEV_SPI.DEV_Module_Init()
        else:
            # Standard spidev path
            self._spi_open()

        # Ensure panel power is enabled
        self.GPIO.output(self.PWR_PIN, 1)
        return 0

    def module_exit(self, cleanup=False):
        logger.debug("spi end")
        try:
            if self._spi_inited:
                self.SPI.close()
        except Exception:
            pass

        # Put control lines low; keep BUSY as input
        try:
            self.GPIO.output(self.RST_PIN, 0)
            self.GPIO.output(self.DC_PIN, 0)
            self.GPIO.output(self.PWR_PIN, 0)
            logger.debug("close 5V, Module enters 0 power consumption ...")
        except Exception:
            pass

        if cleanup and self._gpio_inited:
            try:
                self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.BUSY_PIN, self.PWR_PIN])
            except Exception:
                self.GPIO.cleanup()
        self._spi_inited = False
        self._gpio_inited = False

    # --- internal helpers ---
    def _gpio_setup_basic(self):
        if not self._gpio_inited:
            self.GPIO.setwarnings(False)
            self.GPIO.setmode(self.GPIO.BCM)
            # Outputs
            self.GPIO.setup(self.RST_PIN, self.GPIO.OUT, initial=self.GPIO.HIGH)
            self.GPIO.setup(self.DC_PIN,  self.GPIO.OUT, initial=self.GPIO.LOW)
            self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT, initial=self.GPIO.LOW)
            # NEW: CS pin as GPIO output, inactive HIGH (active-low CS)
            self.GPIO.setup(self.CS_PIN,  self.GPIO.OUT, initial=self.GPIO.HIGH)
            # Inputs: BUSY active-low with pull-up
            self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
            self._gpio_inited = True


    def _spi_open(self):
        if not self._spi_inited:
            self.SPI.open(self.SPI_BUS, self.SPI_DEVICE)
            self.SPI.max_speed_hz = self.SPI_CLOCK_HZ
            self.SPI.mode = 0b00
            # NEW: let us control CS via GPIO (driver calls digital_write on CS)
            try:
                self.SPI.no_cs = True
            except Exception:
                pass
            self._spi_inited = True


# ----------------------------------------------------------------------
# Jetson Nano and Sunrise X3 implementations (unchanged)
# ----------------------------------------------------------------------
class JetsonNano:
    # Pin definition
    RST_PIN  = 17
    DC_PIN   = 25
    CS_PIN   = 8
    BUSY_PIN = 24
    PWR_PIN  = 18

    def __init__(self):
        import ctypes
        find_dirs = [
            os.path.dirname(os.path.realpath(__file__)),
            '/usr/local/lib',
            '/usr/lib',
        ]
        self.SPI = None
        for find_dir in find_dirs:
            so_filename = os.path.join(find_dir, 'sysfs_software_spi.so')
            if os.path.exists(so_filename):
                self.SPI = ctypes.cdll.LoadLibrary(so_filename)
                break
        if self.SPI is None:
            raise RuntimeError('Cannot find sysfs_software_spi.so')

        import Jetson.GPIO
        self.GPIO = Jetson.GPIO

    def digital_write(self, pin, value):
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        return self.GPIO.input(self.BUSY_PIN)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.SYSFS_software_spi_transfer(data[0])

    def spi_writebyte2(self, data):
        for i in range(len(data)):
            self.SPI.SYSFS_software_spi_transfer(data[i])

    def module_init(self):
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)
        self.GPIO.output(self.PWR_PIN, 1)
        self.SPI.SYSFS_software_spi_begin()
        return 0

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.SYSFS_software_spi_end()
        logger.debug("close 5V, Module enters 0 power consumption ...")
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)
        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, self.BUSY_PIN, self.PWR_PIN])


class SunriseX3:
    # Pin definition
    RST_PIN  = 17
    DC_PIN   = 25
    CS_PIN   = 8
    BUSY_PIN = 24
    PWR_PIN  = 18
    Flag     = 0

    def __init__(self):
        import spidev
        import Hobot.GPIO
        self.GPIO = Hobot.GPIO
        self.SPI = spidev.SpiDev()

    def digital_write(self, pin, value):
        self.GPIO.output(pin, value)

    def digital_read(self, pin):
        return self.GPIO.input(pin)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.writebytes(data)

    def spi_writebyte2(self, data):
        self.SPI.xfer3(data)

    def module_init(self):
        if self.Flag == 0:
            self.Flag = 1
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.CS_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.PWR_PIN, self.GPIO.OUT)
            self.GPIO.setup(self.BUSY_PIN, self.GPIO.IN)
            self.GPIO.output(self.PWR_PIN, 1)
            self.SPI.open(2, 0)
            self.SPI.max_speed_hz = 4000000
            self.SPI.mode = 0b00
            return 0
        else:
            return 0

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.close()
        logger.debug("close 5V, Module enters 0 power consumption ...")
        self.Flag = 0
        self.GPIO.output(self.RST_PIN, 0)
        self.GPIO.output(self.DC_PIN, 0)
        self.GPIO.output(self.PWR_PIN, 0)
        self.GPIO.cleanup([self.RST_PIN, self.DC_PIN, self.CS_PIN, self.BUSY_PIN], self.PWR_PIN)


# ----------------------------------------------------------------------
# Platform selection
# ----------------------------------------------------------------------
if sys.version_info[0] == 2:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", shell=True, stdout=subprocess.PIPE)
else:
    process = subprocess.Popen("cat /proc/cpuinfo | grep Raspberry", shell=True, stdout=subprocess.PIPE, text=True)
output, _ = process.communicate()
if sys.version_info[0] == 2:
    output = output.decode(sys.stdout.encoding)

if "Raspberry" in output:
    implementation = RaspberryPi()
elif os.path.exists('/sys/bus/platform/drivers/gpio-x3'):
    implementation = SunriseX3()
else:
    implementation = JetsonNano()

for func in [x for x in dir(implementation) if not x.startswith('_')]:
    setattr(sys.modules[__name__], func, getattr(implementation, func))

### END OF FILE ###
