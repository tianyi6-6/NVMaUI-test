from smbus2 import SMBus
import time
import datetime
import os

def time_stamp_to_date(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

class DS1307:
    DS1307_ADDRESS = 0x68

    def __init__(self, i2c_bus=1):
        """
        初始化 DS1307 模块
        :param i2c_bus: 树莓派的 I2C 总线编号，默认是 1
        """
        self.bus = SMBus(i2c_bus)

    @staticmethod
    def _dec_to_bcd(val):
        """ 将十进制数转换为 BCD 码 """
        return (val // 10 * 16) + (val % 10)

    @staticmethod
    def _bcd_to_dec(val):
        """ 将 BCD 码转换为十进制数 """
        return (val // 16 * 10) + (val % 16)

    def read_time(self):
        """
        从 DS1307 读取当前时间
        :return: datetime 对象表示当前时间
        """
        data = self.bus.read_i2c_block_data(self.DS1307_ADDRESS, 0x00, 7)
        seconds = self._bcd_to_dec(data[0] & 0x7F)
        minutes = self._bcd_to_dec(data[1])
        hours = self._bcd_to_dec(data[2] & 0x3F)
        day = self._bcd_to_dec(data[3])
        date = self._bcd_to_dec(data[4])
        month = self._bcd_to_dec(data[5])
        year = self._bcd_to_dec(data[6]) + 2000
        return datetime.datetime(year, month, date, hours, minutes, seconds)

    def set_time(self, datetime_str):
        """
        设置 DS1307 的时间
        :param datetime_str: 时间字符串，格式为 "YYYY-MM-DD HH:MM:SS"
        """
        try:
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("时间格式不正确，应为 'YYYY-MM-DD HH:MM:SS'")

        year, month, date = dt.year, dt.month, dt.day
        hours, minutes, seconds = dt.hour, dt.minute, dt.second
        day_of_week = dt.isoweekday()

        if not (2000 <= year <= 2099):
            raise ValueError("Year must be between 2000 and 2099")

        self.bus.write_i2c_block_data(self.DS1307_ADDRESS, 0x00, [
            self._dec_to_bcd(seconds),
            self._dec_to_bcd(minutes),
            self._dec_to_bcd(hours),
            self._dec_to_bcd(day_of_week),
            self._dec_to_bcd(date),
            self._dec_to_bcd(month),
            self._dec_to_bcd(year % 100)
        ])
        print(f"时间已设置为: {datetime_str}")

    def sync_to_system(self):
        """
        从 DS1307 将时间同步到系统
        """
        current_time = self.read_time()
        formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"同步到系统时间: {formatted_time}")
        time_cmd = f"sudo date -s '{formatted_time}'"
        os.system(time_cmd)

    def sync_from_system(self):
        """
        从系统时间同步到 DS1307
        """
        now = datetime.datetime.now()
        formatted_time = now.strftime('%Y-%m-%d %H:%M:%S')
        self.set_time(formatted_time)
        print(f"系统时间同步到 DS1307 成功: {formatted_time}")

    def close(self):
        """ 释放 I2C 资源 """
        self.bus.close()
        print("I2C 连接已关闭")

if __name__ == '__main__':
    # 初始化 DS1307
    import argparse

    parser = argparse.ArgumentParser(description="DS1307 RTC Clock Controller")
    parser.add_argument('-t', '--time', type=str,
                        help="设置DS1307当前时间，格式为 'YYYY-MM-DD HH:MM:SS'")
    parser.add_argument('-r', '--read', action='store_true',
                        help="读取DS1307当前时间")
    parser.add_argument('-s', '--sync', action='store_true',
                        help="将DS1307时间同步到系统")

    args = parser.parse_args()

    # 初始化 DS1307
    rtc = DS1307()

    if args.read:
        # 读取时间
        current_time = rtc.read_time()
        print(f"DS1307 当前时间：{current_time}")

    elif args.time:
        # 设置时间
        rtc.set_time(args.time)

    elif args.sync:
        # 从 DS1307 同步时间到系统
        start_time = time.time()
        rtc.sync_to_system()
        new_time = time.time()
        print(
            f"时间已同步：{datetime.datetime.fromtimestamp(start_time)} -> {datetime.datetime.fromtimestamp(new_time)}")

    else:
        parser.print_help()

    # 关闭连接
    rtc.close()