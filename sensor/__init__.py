"""
The package 'sensor' is responsible for handling sensor input i.e. reading the
FSR and calculating the number of coffee cups based on the calibration defined
in the configuration files.

Needs to be run as root to access the GPIO pins.
"""


import time, os, sys, syslog
#from math import sqrt
from statistics import stdev, mean, median
try:
  import config
except ImportError:
  print("Could not import config, try adding the kiltiskahvi folder to your PYTHONPATH. Exiting.")
  sys.exit(1)

# fall back to dummy driver if GPIO is not available
try:
  from sensor.drivers import hx711 as driver
  DUMMY_DRIVER = False
except ImportError as e:
  if e.name != "RPi":
    # importing of some other module than RPi (which contains GPIO) failed
    raise

  syslog.syslog(syslog.LOG_WARNING, "sensor: WARNING: no RPi module available, falling back to dummy GPIO.")

  # GPIO is not available, use dummy ADC function
  from sensor.drivers import dummy as driver
  DUMMY_DRIVER = True

REQUIRED_FUNCTIONS = ["read_adc", "cleanup"]
for fn in REQUIRED_FUNCTIONS:
  assert hasattr(driver, fn), "Driver {} doesn't implement {}().".format(driver.__name__, fn)

class Sensor():
  # set up SPI interface pins and read configuration
  def __init__(self, cfg_dict = None):

    if cfg_dict is None:
      # use default configuration
      cfg_dict = config.get_config_dict()

    self.calibration = cfg_dict["calibration"]

    self.averaging_time = float(cfg_dict["general"]["averaging_time"])

    # this attribute can be used to check if the GPIO module is working
    self.is_dummy = DUMMY_DRIVER

  """
  The function that returns the sensor value after averaging,
  this is supposed to be called externally.
  Returns: a dictionary containing the averaged raw sensor value and the
  current no. of cups we have determined to be in the coffee machine.
  """
  def poll(self, averaging_time = None, avg_interval = 0.01):
    if not averaging_time:
      averaging_time = self.averaging_time

    start = time.time()

    datapoints = []

    while time.time() - start < averaging_time:
      adc_result = driver.read_adc()
      datapoints.append(adc_result)

      time.sleep(avg_interval)


    #s = sum(datapoints)
    n = len(datapoints)
    #raw_value = s / n

    # apply median filtering (NOTE: doesn't work if the erroneous result is at the edge...
    datapoints.insert(0, datapoints[0])
    datapoints.append(datapoints[-1])
    datapoints = [median(datapoints[i:i+3]) for i in range(len(datapoints) - 2)]

    raw_value = mean(datapoints)

    # standard deviation
    #std = sqrt(sum([(x - raw_value) ** 2 for x in datapoints]) / (n - 1))
    std = stdev(datapoints, raw_value)

    nCups = self.compute_nCups(raw_value)

    result = {}

    #TODO: CLEAR UP THIS HACKY MESS

    # is there coffee?
    # NOTE: works even if nCups is None... (None > 0 == False)
    isCoffee = False
    if nCups is not None:
      isCoffee = nCups > 0.

    # TODO: rename this to decanterMissing or sth more descriptive...
    # is the tray empty?
    trayEmpty = nCups is None

    # insert zero instead of null...
    if nCups is None:
      nCups = 0.

    coffeeComing = False
    max_nCups = float(self.calibration["max_ncups"])
    if nCups / max_nCups > 1.2: #TODO: make this magic number configurable?
      # Simple method of detecting whether coffee is being made.
      # Assuming that the scale is at the back of the coffee maker, which means
      # that coffee is coming if the computed no. of cups exceeds the maximum.
      coffeeComing = True

    nCups = max(min(nCups, max_nCups), 0)

    relative_std = std / abs(raw_value)
    if relative_std > 0.5:
      syslog.syslog(syslog.LOG_WARNING,
          "sensor: unusually high std. raw_value: {raw_value}, n: {n}, std: {std} (relative: {relative_std:.2f})".format(**locals()))
      result["datapoints"] = datapoints[:] # store datapoints to investigate high stds...


    result["rawValue"] = raw_value
    result["nMeasurements"] = n
    result["std"] = std
    result["nCups"] = nCups
    result["isCoffee"] = isCoffee
    result["coffeeComing"] = coffeeComing
    result["trayEmpty"] = trayEmpty

    return result

  """
  Compute the number of cups a given raw sensor value corresponds to, using the
  calibration parameters.

  Returns: nCups: None if the decanter is missing, otherwise no. of coffee cups as a float.
  """
  # TODO: should the case of the missing decanter be handled elsewhere?
  # TODO: save definition of compute_ncups to database, use e.g. inspect.getsource
  #   (see: https://stackoverflow.com/questions/1562759/can-python-print-a-function-definition)
  def compute_nCups(self, raw_value):

    cal = self.calibration
    #tol = float(cal["sensor_error_tol"]) * 0.01
    #lims = ((1-tol) * raw_value, (1+tol) * raw_value)

    ##TODO: these first two ifs might be wrong
    #if lims[1] < float(cal["coffee_no_decanter_value"]):
    #  return None #TODO: consider -1 or something...

    #if lims[0] < float(cal["coffee_empty_decanter_value"]) < lims[1]:
    #  return 0.

    # TODO
    if True:
      empty_val = float(cal["coffee_empty_decanter_value"])
      full_val = float(cal["coffee_full_value"])
      max_nCups = float(cal["max_ncups"])
      nCups = (raw_value - empty_val) / (full_val - empty_val) * max_nCups

      ##TODO: make this magic number configurable???
      #if nCups / max_nCups >= 1.2:
      #  pass

      #nCups = max(min(max_nCups, nCups), 0.)

      return nCups

if __name__ == "__main__":

  cfg = config.get_config_dict()

  s = Sensor(cfg)

  try:

    # threshold value for debouncing
    epsilon = 2

    nCups = 0.
    rawValue = 0

    while True:
      res = s.poll(averaging_time = 0.01, avg_interval = 0.001)
      rawValue_new = int(res["rawValue"])
      nCups_new = res["nCups"]
      if abs(rawValue_new - rawValue) > epsilon:
        rawValue = rawValue_new
        nCups = nCups_new

      fmt = "{:0=10} {:>7.1f} {:>12.1f}"
      sys.stdout.write(fmt.format(rawValue, nCups, time.time()) + "\r")
      sys.stdout.flush()
      time.sleep(0.05)

  except Exception:
    driver.cleanup()
    raise
