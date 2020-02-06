import time
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
import displayio
import adafruit_imageload
from adafruit_ble_cycling_speed_and_cadence import CyclingSpeedAndCadenceService
from adafruit_ble_heart_rate import HeartRateService
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect
from adafruit_display_text import label


class Pyloton:

    _previous_wheel = 0
    _previous_crank = 0

    _previous_revolutions = 0
    _previous_crank_rev = 0

    _previous_speed = 0
    _previous_cadence = 0

    _previous_heart = 0

    splash = displayio.Group()
  
    setup = False

    def __init__(self, ble, display, heart=True, speed=True, cadence=True, ams=True, debug=False):
        self.debug = debug

        self.ble = ble
        self.hr_connection = None

        self.heart_enabled = heart
        self.speed_enabled = speed
        self.cadence_enabled = cadence
        self.ams_enabled = ams

        self.display = display

        self.sprite_sheet, self.palette = adafruit_imageload.load("/sprite_sheet.bmp",
                                                                  palette=displayio.Palette)
        self._load_fonts()

    def show_splash(self):
        """
        Shows the loading screen
        """
        if self.debug:
            return
        with open('biketrace.bmp', 'rb') as bitmap_file:
            bitmap = displayio.OnDiskBitmap(bitmap_file)

            tile_grid = displayio.TileGrid(bitmap, pixel_shader=displayio.ColorConverter())

            self.splash_group = displayio.Group()
            self.splash_group.append(tile_grid)

            self.display.show(self.splash_group)
            time.sleep(.05)


    def _load_fonts(self):
        """
        Loads fonts
        """
        self.arial12 = bitmap_font.load_font("/fonts/Arial-12.bdf")
        self.arial16 = bitmap_font.load_font("/fonts/Arial-16.bdf")
        self.arial24 = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")


    def _status_update(self, message):
        """
        Displays status updates
        """
        if self.debug:
            print(message)
            return
        YELLOW = 0xFCFF00
        PURPLE = 0x64337E
        text_group = displayio.Group()
        if len(message) > 25:
            status = label.Label(font=self.arial12, x=10, y=200, text=message[:25], color=YELLOW)
            status1 = label.Label(font=self.arial12, x=10, y=220, text=message[25:], color=YELLOW)
            text_group.append(status)
            text_group.append(status1)
        else:
            status = label.Label(font=self.arial12, x=10, y=200, text=message, color=YELLOW)
            text_group.append(status)


        if len(self.splash_group) == 1:
            status_heading = label.Label(font=self.arial16, x=80, y=175, text="Status", color=YELLOW)
            rect = Rect(0, 165, 240, 75, fill=PURPLE)
            self.splash_group.append(rect)
            self.splash_group.append(status_heading)
            self.splash_group.append(text_group)
        else:
            self.splash_group[3] = text_group
        self.display.show(self.splash_group)
        time.sleep(0.01)

    def timeout(self):
        """
        Displays Timeout on screen when pyloton has been searching for a sensor for too long
        """
        self._status_update("Timeout")
        time.sleep(3)

    def heart_connect(self):
        """
        Connects to heart rate sensor
        """
        self._status_update("Scanning...")
        for adv in self.ble.start_scan(ProvideServicesAdvertisement, timeout=5):
            if HeartRateService in adv.services:
                self._status_update("Found a HeartRateService advertisement")
                self.hr_connection = self.ble.connect(adv)
                self._status_update("Connected")
                break
        return self.hr_connection

    def s_and_c_connect(self):
        """
        Connects to speed and cadence sensor
        """
        print("Scanning...")
        # Save advertisements, indexed by address
        advs = {}
        for adv in self.ble.start_scan(ProvideServicesAdvertisement, timeout=5):
            if CyclingSpeedAndCadenceService in adv.services:
                print("found a CyclingSpeedAndCadenceService advertisement")
                # Save advertisement. Overwrite duplicates from same address (device).
                advs[adv.address] = adv

        self.ble.stop_scan()
        print("Stopped scanning")
        if not advs:
            # Nothing found. Go back and keep looking.
            return []

        # Connect to all available CSC sensors.
        self.cyc_connections = []
        for adv in advs.values():
            self.cyc_connections.append(self.ble.connect(adv))
            print("Connected", len(self.cyc_connections))


        self.cyc_services = []
        for conn in self.cyc_connections:

            self.cyc_services.append(conn[CyclingSpeedAndCadenceService])
        print("Done")
        return self.cyc_connections

    def read_s_and_c(self):
        """
        Reads the speed and cadence sensor
        """
        speed = self._previous_speed
        cadence = self._previous_cadence
        for conn, svc in zip(self.cyc_connections, self.cyc_services):
            if conn.connected:
                values = svc.measurement_values
                if values is not None:
                    if values.last_wheel_event_time:
                        wheel_diff = values.last_wheel_event_time - self._previous_wheel
                        rev_diff = values.cumulative_wheel_revolutions - self._previous_revolutions

                        if wheel_diff:
                            #Rotations per minute is 60 times the amount of revolutions since
                            #the last update over the time since the last update
                            rpm = 60*(rev_diff/(wheel_diff/1024))
                            # We then mutiply it by the wheel's circumference and convert it to mph
                            speed = round((rpm * 84.229) * (60/63360), 1)
                            self._previous_speed = speed
                            self._previous_revolutions = values.cumulative_wheel_revolutions
                        self._previous_wheel = values.last_wheel_event_time

                    if values.last_crank_event_time:
                        crank_diff = values.last_crank_event_time - self._previous_crank
                        crank_rev_diff = values.cumulative_crank_revolutions - self._previous_crank_rev

                        if crank_rev_diff:
                            #Rotations per minute is 60 times the amount of revolutions since the
                            #last update over the time since the last update
                            cadence = round(60*(crank_rev_diff/(crank_diff/1024)), 1)
                            self._previous_cadence = cadence
                            self._previous_crank_rev = values.cumulative_crank_revolutions

                        self._previous_crank = values.last_crank_event_time
                return speed, cadence

    def read_heart(self, hr_service):
        """
        Reads the heart rate sensor 
        """
        measurement = hr_service.measurement_values
        if measurement is None:
            heart = self._previous_heart
        else:
            heart = measurement.heart_rate
            self._previous_heart = measurement.heart_rate
        return heart

    def _icon_maker(self, n, icon_x, icon_y):
        """
        Generates sprites
        """
        sprite = displayio.TileGrid(self.sprite_sheet, pixel_shader=self.palette,
                                    width=1,
                                    height=1,
                                    tile_width=40,
                                    tile_height=40,
                                    default_tile=n,
                                    x=icon_x, y=icon_y)
        return sprite

    def _setup_display(self):
        sprites = displayio.Group()

        rect = Rect(0, 0, 240, 50, fill=0x64338e)
        self.splash.append(rect)

        heading = label.Label(font=self.arial24, x=55, y=25, text="PyLoton", color=0xFCFF00)
        self.splash.append(heading)

        if self.heart_enabled:
            heart_sprite = self._icon_maker(0, 2, 55)
            sprites.append(heart_sprite)

        if self.speed_enabled:
            speed_sprite = self._icon_maker(1, 2, 100)
            sprites.append(speed_sprite)

        if self.cadence_enabled:
            cadence_sprite = self._icon_maker(2, 2, 145)
            sprites.append(cadence_sprite)

        if self.ams_enabled:
            ams_sprite = self._icon_maker(3, 2, 190)
            sprites.append(ams_sprite)

        self.splash.append(sprites)

    def update_display(self, hr_service):
        heart = self.read_heart(hr_service)
        speed, cadence = self.read_s_and_c()

        if len(self.splash) == 0:
            self._setup_display()

        if self.heart_enabled:
            hr_str = '{} bpm'.format(heart)
            hr_label = label.Label(font=self.arial24, x=50, y=75, text=hr_str, color=0xFFFFFF)
            if not self.setup:
                self.splash.append(hr_label)
            else:
                self.splash[3] = hr_label

        if self.speed_enabled:
            sp_str = '{} mph'.format(speed)
            sp_label = label.Label(font=self.arial24, x=50, y=120, text=sp_str, color=0xFFFFFF)
            if not self.setup:
                self.splash.append(sp_label)
            else:
                self.splash[4] = sp_label

        if self.cadence_enabled:
            cad_str = '{} rpm'.format(cadence)
            cad_label = label.Label(font=self.arial24, x=50, y=165, text=cad_str, color=0xFFFFFF)
            if not self.setup:
                self.splash.append(cad_label)
            else:
                self.splash[5] = cad_label

        if self.ams_enabled:
            np_str = 'None'
            now_playing = label.Label(font=self.arial24, x=50, y=210, text=np_str, color=0xFFFFFF)
            if not self.setup:
                self.splash.append(now_playing)
            else:
                self.splash[6] = now_playing

        self.setup=True
        time.sleep(0.2)

        self.display.show(self.splash)
