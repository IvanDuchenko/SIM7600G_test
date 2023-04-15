#!/usr/bin/python3
import datetime as dt
import time
import typing as t

import serial
import serial.tools.list_ports


DEFAULT_TTY_GPS = '/dev/ttyUSB2'
TTY_SPEED = 115200

GPS_STANDALONE = b'AT+CGPS=1,1'
GPS_UE_BASED = b'AT+CGPS=1,2'
GPS_UE_ASSISTED = b'AT+CGPS=1,3'
GPS_STOP = b'AT+CGPS=0'
GPS_STATUS = b'AT+CGPS?'

GPS_INFO = b'AT+CGPSINFO'


class GPSInfo(t.NamedTuple):
    lat: float
    lng: float
    timestamp: float
    alt: float
    speed: float


def parse_gpsinfo(gpsinfo: bytes) -> GPSInfo:
    # response format:
    # b"+CGPSINFO: [lat],[N/S],[lng],[E/W],[date],[UTC time],[alt],[speed],[course]"
    lines = gpsinfo.splitlines()
    if not lines or lines[0] != b'AT+CGPSINFO' or lines[-1] != b'OK':
        raise ValueError('Wrong format, no AT+CGPSINFO or no OK line.')
    for line in lines:
        if line.startswith(b'+CGPSINFO: '):
            return parse_gpsinfo_line(line[len(b'+CGPSINFO: '):])
    raise ValueError('No line that starts with "+CGPSINFO: "')


def parse_gpsinfo_line(line: bytes):
    lat, ns, lng, ew, date, utctime, alt, speed, course = line.split(b',')
    # lat is in format DDMM.MMMMMM, lng is in format DDDMM.MMMMMM
    latfloat = float(lat[:2]) + float(lat[2:]) / 60
    lngfloat = float(lng[:3]) + float(lng[3:]) / 60
    if ns == 'S':
        latfloat = -latfloat
    if ew == 'W':
        lngfloat = -lngfloat
    datestring = f'{date.decode()} {utctime.decode()}'
    timestamp = dt.datetime.strptime(datestring, '%d%m%y %H%M%S.%f').timestamp()
    return GPSInfo(
        lat=latfloat,
        lng=lngfloat,
        timestamp=timestamp,
        alt=float(alt),
        speed=float(speed),
    )


def send_cmd(comm: serial.Serial, command: bytes, timeout=0.01) -> bytes:
    comm.write(command + b'\r\n')
    time.sleep(timeout)
    return comm.read(comm.inWaiting())


def send_at_complex(comm: serial.Serial, command: bytes, back: bytes, timeout: float) -> bytes:
    serial_answer = b''
    comm.write(command + b'\r\n')
    time.sleep(timeout)
    if comm.inWaiting():
        time.sleep(0.01)
        if serial_answer := comm.read(comm.inWaiting()):
            if back not in serial_answer:
                print(command, ' ERROR')
                print(command, ' back:\t', serial_answer)
                return 0, serial_answer
            else:
                print(serial_answer)
                return 1, serial_answer
    else:
        # TODO: why it's not ready? what do we do then?
        print('GPS is not ready, maybe wrong tty')
        return 0, serial_answer


def get_gps_position(comm: serial.Serial):
    rec_null = True
    print('Start GPS session...')
    send_at_complex(comm, GPS_STANDALONE, b'OK', 1)
    time.sleep(2)
    while rec_null:
        status, serial_answer = send_at_complex(comm, GPS_INFO, b'+CGPSINFO: ', 1)
        if status:
            if b',,,,,,' in serial_answer:
                print('GPS is not ready, maybe wrong mode (standalone works)')
                rec_null = False
                time.sleep(1)
            else:
                return parse_gpsinfo(serial_answer)
        else:
            print('error', serial_answer)
            send_at_complex(comm, GPS_STOP, b'OK', 1)
            return None
        time.sleep(1.5)


def find_tty_gps(default=DEFAULT_TTY_GPS) -> str:
    if default and is_tty_gps(default):
        return default
    ports = serial.tools.list_ports.comports()
    for port in reversed(ports):
        if port.device != default and is_tty_gps(port.device):
            return port.device
    return None


def is_tty_gps(tty):
    print(f'Trying {tty} for GPS')
    try:
        with serial.Serial(tty, TTY_SPEED, write_timeout=2, timeout=2) as comm:
            comm.flushInput()
            response = send_cmd(comm, GPS_STATUS)
            # print(f'response: {response!r}')
    except Exception:
        return False
    return bool(response) and response.splitlines()[-1] == b'OK'


def main_gps(tty=None, speed=TTY_SPEED):
    tty = find_tty_gps()
    with serial.Serial(tty, speed) as comm:
        comm.flushInput()
        print(get_gps_position(comm))
    print('Serial closed')


if __name__ == '__main__':
    main_gps()
