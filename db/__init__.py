"""
This module handles inserting to and reading from a mongodb database.

For each measurement, we store the raw value of the sensor, a timestamp, the
number of cups the sensor value corresponds to and possible additional
information (standard deviation? something else?). The no. of cups as a
function of raw sensor value may change depending on the sensor and calibration
parameters. 

The calibration parameters are stored separately, and a new entry is added only
when the parameters change. This should make earlier raw sensor values
compatible with newer measurements (in theory), as long as the method for
calculating them is known. 
A user need not worry about this, as the no. of cups is assumed to be correct
for each calibration.

Possibly in the future, different collections (~tables, see mongodb docs) may 
be used corresponding to different levels of aggregation. In this case the db 
manager handles aggregation and querying the appropriate database if the query 
is a range.

NOTE: The mongodb database is located in /var/lib/mongodb (default for debian
(I think)). All db paths are handled automagically by mongodb, so we try not to
fiddle with those at all.
"""
from pymongo import MongoClient
import sys
import os

#TODO: does the connection need to be closd manually w/ mongodb?
"""
A class to handle database queries. 
"""
class DatabaseManager(object):

  def __init__(self, config):
    #TODO
    
    # override query function with dummy function
    # note: this if-else structure is pretty stupid...
    if config == "dummy":
      self.query_range = self.query_dummy_range
      self.query = self.query_dummy

    else:

      client = MongoClient("localhost", 27017) # hard-coded local db.

      # database and collection (~table) names are hardcoded... (good idea?)
      db = client["kahvidb"]
      datacollection = db["data"]

      self.client = client
      self.db = db
      self.datacollection = datacollection

      """
      A collection holding a single entry: the latest calibration parameters
      in dictionary form. Another collection keeps track of the history of
      calibration parameters. These are updated only when the calibration
      values change.
      """
      #TODO: this whole thing
      #TODO: check for changed parameters
      #self.calibrationParams = db["calibration-last"]
      # this contains a history of calibration dictionaries.
      #self.calibrationDicts = db["calibration-history"]


  #############
  # INSERTING #
  #############

  """
  Insert a data point into the database.
  Perform simple verification that the given data dictionary contains some
  required fields.

  Might add support for inserting multiple data points in the future.
  """
  #TODO: inserting multiple data points?
  def insert_data(self, data_dict):

    if type(data_dict) != dict:
      raise NotImplementedError("Insert_data can only handle single data point dictionaries as of now.")

    # simple (and dirty) data validation, raises a KeyError if a required field is missing
    # TODO: is there a better place for defining the required fields??
    required_fields = ["timestamp", "rawValue", "nCups"]
    [data_dict[field] for field in required_fields]

    # handle multiple datapoints #TODO (this check isn't good if we're using a dict)
    #if hasattr(timestamp, "__iter__"): 
    #  #TODO
    #  pass

    self.datacollection.insert_one(data_dict)

  #TODO: calibration parameters
  #def update_calibration(self, calibrationDict):

    #self.db["calibration-last"].update_one(
    #  {"_id": 0},  # this ensures that calibrationParams will only have one value.
    #  {"calibrationDict" : calibrationDict},
    #  upsert = True
    #)
    #self.db["calibrationDicts"].insert_one({"timestamp" : time.time(), "calibrationDict": calibrationDict})


  ############
  # QUERYING #
  ############

  """
  Query all datapoints within the given tuple range.
  """
  def query_range(self, r):
    try:
      (start, end) = r
      c = self._conn.cursor()
      c.execute("SELECT * FROM ???")
      query_result = c.fetchall()
      return query_result
    except (ValueError, TypeError) as e:
      #TODO: do this properly...
      raise DBException("Invalid database range: {}.".format(e))

  def query_dummy_range(self, r):
    import random
    max_num_points = 100
    lo, hi = r
    num_points = min(max(hi - lo, 0), max_num_points)
    y = random.sample(range(1024), num_points)
    x = [int(lo + 1.0 * x * (hi - lo) / num_points) for x in range(num_points)]
    return zip(x, y)

  def query_dummy(self):
    import random
    return random.randint(0, 1024)

  #TODO
  # this function queries the latest calibration parameters from the appropriate table 
  # should be used only on startup 
  def query_latest_calibration(self):
    # see https://stackoverflow.com/questions/22200587/get-records-for-the-latest-timestamp-in-sqlite
    c = self._conn.cursor()
    c.execute("SELECT * FROM ??? ORDER BY timestamp DESC LIMIT 1")
    query_result = c.fetchall()
    return query_result

  # TODO
  # store updated calibration settings in to the appropriate table
  def update_calibration(self, timestamp, calibration_dict):
    c = self._conn.cursor()
    c.execute("INSERT (?, ?) INTO TABLE ... ??? ", timestamp, calibration_dict)
    c.commit()

# necessary?
class DBException(Exception):
  #TODO
  pass


"""
Return a suitable folder name for dumping database contents by using a 
timestamp. Don't create the folder, that must be done elsewhere.
"""
def get_default_dump_path():
  import time
  folderBaseName = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 
      "dump",
      "dump-" + time.strftime("%Y-%m-%d-%H%M", time.localtime())
      )

  folderName = folderBaseName

  i = 1
  while os.path.exists(folderName):
    folderName = folderBaseName + "-" + str(i)
    i += 1

  return folderName

"""
Dump database contents using mongoexport and drop collections if specified. 
"""
def dump_database(dump_path, config_dict, purge = False):

  dbm = DatabaseManager(config_dict)
  db = dbm.db

  # filter out system collections
  collectionNames = list(filter(
      lambda x: not x.startswith("system."),
      db.collection_names()
      ))
  
  # doing this check here prevents from creating folders if it's not necessary.
  if not collectionNames:
    print("Database {} appears to be empty. Exiting.".format(db.name))
    sys.exit(0)


  if not os.path.exists(dump_path):
    # TODO: create folder as necessary
    os.makedirs(dump_path)

  else:

    if not os.path.isdir(dump_path):
      print("Error: {} is not a directory. Aborting.".format(dump_path))
      sys.exit(1)

    ans = input(
        "WARNING: the folder {} already exists. Do you want to overwrite its contents? (y/n) ".format(dump_path)
        ).lower()

    if not ans in ["y", "yes"]:
      print("Aborting.")
      sys.exit(1)
    

  os.chdir(dump_path)

  print("Dumping database content to {}.".format(os.getcwd()))

  for collName in collectionNames:

    fname = collName + ".json"

    command = "mongoexport --db {} --collection {} --out {}".format(
        db.name, collName, fname
        )

    print("executing {}".format(command))
    retval = os.system(command)

    if retval != 0:
      raise Exception("Shell exited with error (return value {}).".format(retval))

    if purge:
      print("Dropping collection {}.".format(collName))
      db.drop_collection(collName)



"""
Main function for testing and manual database management
"""
if __name__ == "__main__":
  import argparse

  try:
    import config
  except ImportError:
    print("Could not import config, try adding the kiltiskahvi folder to your PYTHONPATH. Exiting.")
    sys.exit(1)


  ap = argparse.ArgumentParser(description = "Dump or delete database contents or run whatever is in the main function.")

  ap.add_argument("-c", "--config",
      dest = "config_file",
      help = "use CONFIG_FILE as the configuration file instead of the default")

  ap.add_argument("--dump",
      dest = "dump_path",
      nargs = "?",
      const = get_default_dump_path(),
      default = None,
      help = "Dump entire kiltiskahvi database contents in JSON format using mongoexport. Data is dumped to the specified folder or to kiltiskahvi/db/dump/ by default."
      )

  ap.add_argument("--purge",
      dest = "purge_dump_path",
      nargs = "?",
      const = get_default_dump_path(),
      default = None,
      help = "Same as --dump but also delete database contents. Use at your own risk."
      )


  args = ap.parse_args()

  # TODO: is config even necessary for the DB manager?
  cfg = config.get_config_dict(args.config_file)

  if args.purge_dump_path:
    dump_database(args.purge_dump_path, cfg, purge = True)
    sys.exit(0)

  elif args.dump_path:
    dump_database(args.dump_path, cfg)
    sys.exit(0)



  dbm = DatabaseManager(cfg)


  #TODO: tests...
  #dbm.query_range((0, 100))
  #dbm.query_range((50, 0)) # should raise an exception
  #...
