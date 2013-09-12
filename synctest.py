#!/usr/bin/env python
# TODO:
#   Print all the stats for files that don't match, not just the stat that
#     doesn't match.
#   Handle symlinks
#   Add option to not recurse (only examine files in root dir)

import os
import sys
import time
import math
import zlib
import random
from optparse import OptionParser

DEFAULT_CHUNK_SIZE = 1024**2
OPT_DEFAULTS = {'tolerance':0, 'ignore_dates':False}
USAGE = """Usage: %prog directory1 directory2
         %prog -p directory1 > directory1.txt"""
DESCRIPTION = """"""

def get_options(defaults, usage, description='', epilog=''):
  """Get options, print usage text."""

  parser = OptionParser(usage=usage, description=description, epilog=epilog)

  parser.add_option('-t', '--date-tolerance', dest='tolerance',
    default=defaults.get('tolerance'),
    help='Amount of allowed discrepancy between modified dates. Can be given '
    +'with units of seconds (s), minutes (m), hours (h), or days (d), e.g. '
    +'"15m". Times without units are assumed to be seconds.')
  parser.add_option('-d', '--ignore-dates', dest='ignore_dates',
    action='store_const', const=not(defaults.get('ignore_dates')),
    default=defaults.get('ignore_dates'),
    help='Ignore discrepancies between modified dates.')
  parser.add_option('-c', '--no-checksum', dest='crc', action='store_false',
    default=True,
    help='Do not perform a checksum (CRC-32 currently), saving time on large '
    +'files. The size in bytes will still be checked, which will catch most '
    +'changes in contents.')
  parser.add_option('-p', '--print', dest='print_all', action='store_true',
    default=False,
    help='Print all the files in the directory to stdout, including the full '
    +'path, size, date modified, and CRC-32. This output can be saved to a '
    +'file, and compared to the output for another directory using sort and '
    +'diff.')
  parser.add_option('-u', '--unix-time', dest='unix_time', action='store_true',
    default=False,
    help='When in print-all mode, print the unix timestamp (in seconds) '
    +'instead of a human-readable date modified.')
  parser.add_option('-a', '--ignore-dir1', dest='ignore1', action='store_true',
    default=False,
    help='Ignore files and directories missing from the first directory. When '
    +'items are found to be missing from the first directory (according to the '
    +'order in the arguments), do not print any message. Other discrepancies '
    +'will still be reported.')
  parser.add_option('-b', '--ignore-dir2', dest='ignore2', action='store_true',
    default=False,
    help='Ignore files and directories missing from the second directory. When '
    +'items are found to be missing from the second directory (according to '
    +'the order in the arguments), do not print any message. Other '
    +'discrepancies will still be reported.')

  (options, arg_list) = parser.parse_args()

  # read in positional arguments
  arg_dict = {}
  if len(arg_list) >= 1:
    arg_dict['rootdir1'] = arg_list[0]
  if len(arg_list) >= 2:
    arg_dict['rootdir2'] = arg_list[1]

  return (options, arg_dict)


def main():

  (options, arguments) = get_options(OPT_DEFAULTS, USAGE, DESCRIPTION)

  crc = options.crc
  unix_time = options.unix_time
  ignore1 = options.ignore1
  ignore2 = options.ignore2
  tolerance = parse_tolerance(options.tolerance, options.ignore_dates)

  # Print all the files and their attributes, then exit
  if options.print_all:
    rootdir = arguments.get('rootdir1', None)
    if rootdir is None:
      sys.stderr.write("Error: Must specify a starting directory to print.\n")
      sys.exit(1)
    print_all(rootdir, unix_time, crc)
    sys.exit(0)

  allequal = True

  rootdir1 = arguments.get('rootdir1', None)
  rootdir2 = arguments.get('rootdir2', None)
  if rootdir1 is None or rootdir2 is None:
    sys.stderr.write("Error: Must specify two directories to compare.\n")
    sys.exit(1)
  if not os.path.exists(rootdir1):
    sys.stderr.write("Error: Directory not accessible: "+rootdir1+"\n")
    sys.exit(1)
  if not os.path.exists(rootdir2):
    sys.stderr.write("Error: Directory not accessible: "+rootdir1+"\n")
    sys.exit(1)

  walker1 = os.walk(rootdir1)
  walker2 = os.walk(rootdir2)
  done1 = False
  done2 = False
  (dir1, dirnames1, filenames1) = walker1.next()
  (dir2, dirnames2, filenames2) = walker2.next()
  while not done1 and not done2:

    # check that the subdirectories are the same

    (missing1, missing2) = matchup(dirnames1, dirnames2)

    if len(missing1) > 0:
      allequal = False
      if not ignore2:
        print "\tDirectories missing from "+dir2+":"
        for dirname in missing1:
          print dirname
    if len(missing2) > 0:
      allequal = False
      if not ignore1:
        print "\tDirectories missing from "+dir1+":"
        for dirname in missing2:
          print dirname


    # check that the files are the same

    (missing1, missing2) = matchup(filenames1, filenames2)

    # print notice about missing files
    if len(missing1) > 0:
      allequal = False
      if not ignore2:
        print "\tFiles missing from "+dir2+":"
        for filename in missing1:
          print filename
    if len(missing2) > 0:
      allequal = False
      if not ignore1:
        print "\tFiles missing from "+dir1+":"
        for filename in missing2:
          print filename

    # the meat: compare files on size, date modified, CRC32.
    for pair in zip(filenames1, filenames2):
      filepath1 = os.path.join(dir1, pair[0])
      filepath2 = os.path.join(dir2, pair[1])
      (equal, messages) = equalfiles(filepath1, filepath2, tolerance, crc)
      if not equal:
        sys.stdout.write(messages)
        allequal = False

    try:
      (dir1,dirnames1,filenames1) = walker1.next()
    except StopIteration, si:
      done1 = True
    try:
      (dir2,dirnames2,filenames2) = walker2.next()
    except StopIteration, si:
      done2 = True

    # if one finishes before the other, they're unsynced.
    # call walker.next() repeatedly and print the extra directories.
    if done1 and not done2:
      sys.stderr.write("Error: walker for "+rootdir1+" finished before the "
        +"one for "+rootdir2+"\n")
      sys.exit(1)
    elif done2 and not done1:
      sys.stderr.write("Error: walker for "+rootdir2+" finished before the "
        +"one for "+rootdir1+"\n")
      sys.exit(1)

  if allequal:
    print "They're equal!"


##### FUNCTIONS #####

def parse_tolerance(tolerance, ignore_dates):
  """Returns tolerance converted to seconds, or False if problem with input"""
  if ignore_dates:
    return 2**31  # maximum 32-bit unix timestamp
  try:
    return int(tolerance)
  except ValueError, e:
    unit = tolerance[-1].lower()
    try:
      tolerance = int(tolerance[:-1])
    except ValueError, e:
      return False
    if unit == 's':
      return tolerance
    elif unit == 'm':
      return tolerance * 60
    elif unit == 'h':
      return tolerance * 60 * 60
    elif unit == 'd':
      return tolerance * 60 * 60 * 24
    elif unit == 'y':
      return tolerance * 60 * 60 * 24 * 365
    else:
      return False


def equalfiles(file1, file2, tolerance, crc):
  """Compare two files by date modified, size, and CRC-32. If the
  files are the same, this returns True and an empty string. If they are not
  equal, this returns False and a string ready to print to the screen about how
  they differ."""
  equal = True
  message = ""

  # they both exist?
  if not (os.path.exists(file1) and os.path.exists(file2)):
    if not os.path.exists(file1):
      message += ("Internal error: "+file1+" returned by os.walk() but not "
        +"reported as existing by os.path.exists().\n")
    if not os.path.exists(file2):
      message += ("Internal error: "+file2+" returned by os.walk() but not "
        +"reported as existing by os.path.exists().\n")
    equal = False
    return (equal, message)

  # gather statistics
  size1 = os.path.getsize(file1)
  size2 = os.path.getsize(file2)
  date1 = int(os.path.getmtime(file1))
  date2 = int(os.path.getmtime(file2))
  if crc:
    crc1 = crc32(file1)
    crc2 = crc32(file2)

  # they are the same size?
  if size1 != size2:
    message += ("\tDifferent file sizes:\n"
      # todo: convert to human-readable file size
      +file1+":\n"+str(size1)+" bytes ("+time.ctime(date1)+")\n"
      +file2+":\n"+str(size2)+" bytes ("+time.ctime(date2)+")\n")
    equal = False
    return (equal, message)

  # they have the same date modified?
  if abs(date1 - date2) > tolerance:
    message += "\tDifferent date modified"
    if crc:
      if crc1 == crc2:
        message += " but equal CRC-32's"
      else:
        message += " and different CRC-32's"
    message += ":\n"+file1+":\n"+time.ctime(date1)
    if crc:
      message += " (CRC32 "+str(crc1)+")"
    message += "\n"+file2+":\n"+time.ctime(date2)
    if crc:
      message += " (CRC32 "+str(crc2)+")"
    message += "\n"
    equal = False
    return (equal, message)

  # they have the same CRC?
  if crc and crc1 != crc2:
    message += ("\tSame size and date modified, but different CRC-32's:\n"
      +file1+" ("+str(size1)+" bytes)\n"
      +file2+" ("+str(size2)+" bytes)\n")
    equal = False
    return (equal, message)

  return (equal, message)


def crc32(filename, chunk_size=DEFAULT_CHUNK_SIZE):
  """Read a file and compute its CRC-32. Only reads chunk_size bytes into memory
  at a time."""
  crc = 0
  with open(filename, 'r') as filehandle:
    chunk = filehandle.read(chunk_size)
    while chunk != "":
      crc = zlib.crc32(chunk, crc)
      chunk = filehandle.read(chunk_size)
  return crc


def print_all(rootdir, unix_time, crc):
  """Walk all subdirectories and print stats on every file: the full path, the
  file size, last modified date, and CRC-32."""

  rootparent = os.path.dirname(rootdir)

  for (dirpath, dirnames, filenames) in os.walk(rootdir):
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      if rootparent == '':
        relfilepath = filepath
      else:
        relfilepath = filepath[len(rootparent)+1:]
      size = str(os.path.getsize(filepath))
      mtime = os.path.getmtime(filepath)
      if unix_time:
        datetime = str(int(mtime))
      else:
        datetime = time.ctime(mtime)
        datetime = datetime[20:24]+datetime[3:19]#+mtime_dec[1:4]
      sys.stdout.write(relfilepath+"\t"+size+"\t"+datetime+"\t")
      if crc:
        sys.stdout.write(str(crc32(filepath)))
      print ''


# sort and compare the two lists of filenames, note any that don't have a match
# in the other list, and delete them.
  # arr1 = ['a', 'c', 'd']
  # arr2 = ['a', 'b', 'c', 'd']
def matchup(files1, files2):
  missing1 = []
  missing2 = []

  files1.sort()
  files2.sort()
  len1 = len(files1)
  len2 = len(files2)
  i = j = 0
  while i < len1 and j < len2:
    if files1[i] == files2[j]:
      # print (str(i)+":"+files1[i]+" "+str(j)+":"+files2[j]+" - matched up")
      i+=1
      j+=1
      continue
    else:
      # print "mismatch:"
      a = i
      b = j
      i_end = i
      j_end = j
      skipped1 = { files1[a]:a }
      skipped2 = { files2[b]:b }
      found_it = False;
      # find the first file on either side that matches, load up the dict's
      while not found_it and not (a >= len1 and b >= len2):

        if a < len1:
          skipped1[files1[a]] = a
          if files1[a] in skipped2:
            found_it = True
            # print "found "+files1[a]+" in arr2, index "+str(a)+" in arr1"
            i_end = a
            j_end = skipped2[files1[a]]
          elif a < len1:
            # i_end = a   # I thought something like this would help
            a+=1

        if b < len2:
          skipped2[files2[b]] = b
          if files2[b] in skipped1:
            found_it = True
            # print "found "+files2[b]+" in arr1, index "+str(b)+" in arr2"
            j_end = b
            i_end = skipped1[files2[b]]
          elif b < len2:
            # j_end = b
            b+=1

        if not found_it and a >= len1 and b >= len2:
          # print "entering mismatch-tail mode"
          i_end = len1
          j_end = len2

      # then start again at i and j, and add each file to missing until you
      # hit the first one that's present in the other's skipped
      i_tmp = i
      j_tmp = j
      while i_tmp < i_end:
        # print "adding "+str(i)+":"+files1[i]+" from files1 to missing1"
        missing1.append(files1[i])
        del(files1[i])
        len1 = len(files1)
        i_tmp+=1
      while j_tmp < j_end:
        # print "adding "+str(j)+":"+files2[j]+" from files2 to missing2"
        missing2.append(files2[j])
        del(files2[j])
        len2 = len(files2)
        j_tmp+=1

  # Check for extra files at the end of one list that aren't present in the
  # other. The above algorithm needs missing files to be flanked by matching
  # ones. If there's a run of missing files at the end with no matching one
  # following the run, they won't be caught above.
  if len1 < len2:
    j_tmp = len1
    j_end = len2
    while j_tmp < j_end:
      missing2.append(files2[len1])
      del(files2[len1])
      j_tmp+=1
    len2 = len(files2)
  elif len2 < len1:
    i_tmp = len2
    i_end = len1
    while i_tmp < i_end:
      missing1.append(files1[len2])
      del(files1[len2])
      i_tmp+=1
    len1 = len(files1)

  return (missing1, missing2)

if __name__ == "__main__":
  main()