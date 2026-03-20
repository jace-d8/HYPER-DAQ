import serial
import time

PORT = '/dev/tty.usbserial-FTDZA5QJ' # port location

ser = serial.Serial( # 218 settings
    PORT, # specified above
    baudrate=9600, # Lakeshore buad rate
    bytesize=serial.SEVENBITS,
    parity=serial.PARITY_ODD,
    stopbits=serial.STOPBITS_ONE,
    timeout=1
)

def query(cmd):
    ser.write((cmd + '\r\n').encode('ascii')) # read req, append newline, convert str to bytes
    time.sleep(0.1)
    return ser.readline().decode('ascii', errors='ignore').strip()
    # read bytes until newline (/n
    # convert bytes into str
    # ignore errors (testing)
    # remove newline

print("ID:", query("*IDN?")) # cmd for model info
while True:
    print("Temp 1:", query("KRDG? 1")) # read kelvin

ser.close() # close port