#!/usr/bin/env python3
import argparse
import logging
import os
import pathlib
import sys
import zlib
assert sys.version_info.major >= 3, 'Python 3 required'

DEFAULT_CHUNK_SIZE = 1024**2
DESCRIPTION = """Check the differences between the contents of two directories."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('dir1', type=pathlib.Path)
  parser.add_argument('dir2', type=pathlib.Path)
  parser.add_argument('-t', '--date-tolerance', default=0, type=parse_tolerance,
    help='Amount of allowed discrepancy between modified dates. Can be given with units of seconds '
      '(s), minutes (m), hours (h), or days (d), e.g. "15m". Times without units are assumed to be '
      'seconds.')
  parser.add_argument('-d', '--ignore-dates', dest='date_tolerance', action='store_const',
    const=60*60*24*365*1000,  # 1000 years
    help='Ignore discrepancies between dates modified.')
  parser.add_argument('-c', '--no-checksum', dest='crc', default='last',
    action='store_const', const='none',
    help='Do not perform a checksum (CRC-32 currently), saving time on large files. The size in '
      'bytes will still be checked, which will catch most changes in contents.')
  parser.add_argument('-C', '--checksum-if-date-diff', dest='crc', action='store_const', const='date',
    help='Compare the checksums even if the date modifieds are different.')
  parser.add_argument('-1', '-a', '--ignore-dir1', action='store_true',
    help='Ignore files and directories missing from the first directory. When items are found to '
      'be missing from the first directory (according to the order in the arguments), do not '
      'print any message. Other discrepancies will still be reported.')
  parser.add_argument('-2', '-b', '--ignore-dir2', action='store_true',
    help='Ignore files and directories missing from the second directory. When items are found to '
      'be missing from the second directory (according to the order in the arguments), do not '
      'print any message. Other discrepancies will still be reported.')
  parser.add_argument('-f', '--follow-links', action='store_true',
    help='Follow symbolic links while traversing the filesystem. This will not affect how links '
      'are treated when comparing paths. They will always be considered on their own, as a special'
      'file type, without reference to their targets.')
  parser.add_argument('-X', '--die-on-error', action='store_true',
    help="Don't ignore errors that prevent obtaining an accurate result. Normally, if there's an "
      "issue accessing a path (permission issue, misc I/O issue), a warning will be logged and it "
      'will move on. If this option is set, that will be treated as a fatal error and the program '
      'will die.')
  #TODO:
  # parser.add_argument('-p', '--print-all', action='store_true', default=False,
  #   help='Print all the files in the directory to stdout, including the full path, size, date '
  #        'modified, and CRC-32. This output can be saved to a file, and compared to the output for '
  #        'another directory using sort and diff.')
  # parser.add_argument('-u', '--unix-time', action='store_true',
  #   help='When in print-all mode, print the unix timestamp (in seconds) instead of a human-'
  #        'readable date modified.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  check_dir_arg(args.dir1)
  check_dir_arg(args.dir2)

  total_diffs = 0
  for diff_type, path_type, diff1, diff2 in compare(
      args.dir1, args.dir2, args.ignore_dir1, args.ignore_dir2, crc=args.crc,
      date_tolerance=args.date_tolerance, follow_links=args.follow_links,
      die_on_error=args.die_on_error
    ):
    total_diffs += 1
    print(format_human(diff_type, path_type, diff1, diff2))

  if total_diffs == 0:
    print('They\'re equal!')


def check_dir_arg(path):
  if not path.exists():
    fail('Error: Argument not an existing directory: {!r}'.format(str(path)))
  elif not path.is_dir():
    fail('Error: Argument not a directory: {!r}'.format(str(path)))


def compare(root1, root2, ignore1, ignore2, crc='last', date_tolerance=0, follow_links=False,
            die_on_error=False):
  walker1 = os.walk(root1, followlinks=follow_links)
  walker2 = os.walk(root2, followlinks=follow_links)
  first_loop = True
  while True:
    # Iterate the walkers.
    #TODO: Handle issue where a walker can't access a directory to go into it.
    #      In that case, it skips the directory and goes to the next one, getting the walkers out of
    #      sync. You can give a handler to the `onerror` argument, and see the exception that way.
    #      Maybe use that to detect when an error occurs, then advance the other walker as many times
    #      as you saw exceptions.
    try:
      walker_paths1, walker_paths2 = step_walkers(walker1, walker2, first_loop)
    except StopIteration:
      break
    first_loop = False
    # Extract and transform the path data from the walkers.
    # Note: `sync_up_walker_paths()` alters its arguments, editing the dirnames lists returned by
    # the walkers so they're equal. This affects the walkers' traversal to keep them in sync.
    dir1 = walker_paths1[0]
    dir2 = walker_paths2[0]
    paths1, paths2, missing1, missing2 = sync_up_walker_paths(walker_paths1, walker_paths2)
    # Check for missing files/directories.
    for diff in get_missings(missing1, missing2, ignore1, ignore2):
      yield diff
    # Compare each path.
    for path1, path2 in zip(paths1, paths2):
      try:
        result = compare_paths(dir1/path1, dir2/path2, date_tolerance=date_tolerance, crc=crc)
        if result[0] != 'equal':
          yield result
      except IOError as error:
        if die_on_error:
          raise
        else:
          logging.error('Error: {}'.format(error))


def step_walkers(walker1, walker2, first_loop):
  try:
    dir1, dirnames1, filenames1 = pathize(next(walker1))
    done1 = False
  except StopIteration:
    done1 = True
  try:
    dir2, dirnames2, filenames2 = pathize(next(walker2))
    done2 = False
  except StopIteration:
    done2 = True
  if done1 and done2:
    raise StopIteration('Both walkers finished.')
  elif done1:
    raise SyncError('Walker for dir1 finished before walker for dir2.')
  elif done2:
    raise SyncError('Walker for dir2 finished before walker for dir1.')
  # Check if the walkers have gotten out of sync.
  #TODO: This only checks the last element of the paths, so it can false negative if there are
  #      directories with the same name in different parent directories.
  if dir1.name != dir2.name and not first_loop:
    raise SyncError('Comparison got unsynced. Directories are different:\n  {!r}\n  {!r}.'
                    .format(str(dir1), str(dir2)))
  return (dir1, dirnames1, filenames1), (dir2, dirnames2, filenames2)


def sync_up_walker_paths(walker_paths1, walker_paths2):
  dir1, dirnames1, filenames1 = walker_paths1
  dir2, dirnames2, filenames2 = walker_paths2
  dirnames1.sort()
  dirnames2.sort()
  missing_dirs1, missing_dirs2 = matchup(dirnames1, dirnames2)
  filenames1.sort()
  filenames2.sort()
  missing_files1, missing_files2 = matchup(filenames1, filenames2)
  missing1 = [dir1/missing for missing in missing_dirs1 + missing_files1]
  missing2 = [dir2/missing for missing in missing_dirs2 + missing_files2]
  paths1 = dirnames1 + filenames1
  paths2 = dirnames2 + filenames2
  return paths1, paths2, missing1, missing2


def pathize(args):
  """Convert the string output of `os.walk()` to  `pathlib.Path`s.
  This alters the list arguments."""
  dirstr, dirnames, filenames = args
  dirpath = pathlib.Path(dirstr)
  for i, dirname in enumerate(dirnames):
    dirnames[i] = pathlib.Path(dirname)
  for i, filename in enumerate(filenames):
    filenames[i] = pathlib.Path(filename)
  return dirpath, dirnames, filenames


def get_missings(missing1, missing2, ignore1, ignore2):
  if not ignore2:
    for missing in missing1:
      yield 'missing', get_path_type(missing), {'path':missing}, {'path':None}
  if not ignore1:
    for missing in missing2:
      yield 'missing', get_path_type(missing), {'path':None}, {'path':missing}


def compare_paths(path1, path2, date_tolerance=0, crc='last'):
  # Start creating the diff data to pass back.
  diff1 = {'path':path1}
  diff2 = {'path':path2}
  # Are they both files/directories/links?
  path_type1 = get_path_type(path1)
  path_type2 = get_path_type(path2)
  diff1['type'] = path_type1
  diff2['type'] = path_type2
  if path_type1 != path_type2:
    return 'type', 'mixed', diff1, diff2
  if path_type1 == 'link':
    # If they're links, check that they point to the same thing.
    target1 = os.readlink(path1)
    target2 = os.readlink(path2)
    diff1['target'] = target1
    diff2['target'] = target2
    if target1 == target2:
      return 'equal', path_type1, diff1, diff2
    else:
      return 'target', path_type1, diff1, diff2
  elif path_type1 != 'file':
    # If it's not a file, there's no more checks that are implemented for the other types.
    # Consider them equal.
    return 'equal', path_type1, diff1, diff2
  # Now, check that the files are equal.
  # We always want to get the size and date modified.
  diff1['size'] = os.path.getsize(path1)
  diff2['size'] = os.path.getsize(path2)
  diff1['modified'] = int(os.path.getmtime(path1))
  diff2['modified'] = int(os.path.getmtime(path2))
  # Different sizes?
  if diff1['size'] != diff2['size']:
    return 'size', path_type1, diff1, diff2
  if crc == 'date':
    diff1['crc'] = get_crc32(path1)
    diff2['crc'] = get_crc32(path2)
  # Different dates modified?
  if abs(diff1['modified'] - diff2['modified']) > date_tolerance:
    return 'modified', path_type1, diff1, diff2
  # Different checksums?
  if crc != 'none':
    if 'crc' not in diff1 or 'crc' not in diff2:
      diff1['crc'] = get_crc32(path1)
      diff2['crc'] = get_crc32(path2)
    if diff1['crc'] != diff2['crc']:
      return 'crc', path_type1, diff1, diff2
  return 'equal', path_type1, diff1, diff2


def get_crc32(path, chunk_size=DEFAULT_CHUNK_SIZE):
  """Read a file and compute its CRC-32. Only reads chunk_size bytes into memory at a time.
  This may raise an IOError if there's a problem reading the file."""
  crc = 0
  with open(path, 'rb') as file:
    chunk = file.read(chunk_size)
    while chunk:
      # Note: A change in Python 3.0 means the crc returned by this is incompatible with those from
      # earlier versions.
      crc = zlib.crc32(chunk, crc)
      chunk = file.read(chunk_size)
  return crc


def get_path_type(path):
  """Check what type the file is and return a string of the type.
  If the file doesn't exist, this returns 'nonexistent'.
  If there's an error accessing the path, this may raise an IOError."""
  try:
    if path.is_symlink():
      return 'link'
    elif path.is_file():
      return 'file'
    elif path.is_dir():
      return 'dir'
    elif not path.exists():
      return 'nonexistent'
    elif path.is_socket():
      return 'socket'
    elif path.is_fifo():
      return 'fifo'
    elif path.is_block_device():
      return 'block'
    elif path.is_char_device():
      return 'char'
    else:
      return 'special'
  except FileNotFoundError:
    return 'nonexistent'


def parse_tolerance(tolerance_str):
  """Returns tolerance converted to seconds."""
  try:
    return int(tolerance_str)
  except ValueError:
    unit = tolerance_str[-1].lower()
    try:
      tolerance = int(tolerance_str[:-1])
    except ValueError:
      fail('Error: --date-tolerance string {!r} invalid.'.format(tolerance_str))
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
      fail('Error: --date-tolerance string {!r} invalid.'.format(tolerance_str))


def format_human(diff_type, path_type, diff1, diff2):
  output = 'Difference: '+diff_type+'\n'
  output += 'path1: {}\n'.format(diff1['path'])
  output += 'path2: {}\n'.format(diff2['path'])
  return output


def matchup(files1, files2):
  """Compare two lists, removing any elements that don't have a match in the other.
  Warning: This alters the input lists. They should be equal afterward.
  This also returns two list of strings that were removed, one for each input list.
  Example:
    arr1 = ['a', 'c', 'd']
    arr2 = ['a', 'b', 'c', 'd']
    missing1, missing2 = matchup(arr1, arr2)
    missing1 == []
    missing2 == ['b']"""
  # This is basically the unaltered code I originally wrote for synctest.
  missing1 = []
  missing2 = []

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

  return missing1, missing2


class SyncError(Exception):
  def __init__(self, message):
    self.message = message
    self.args = (message,)
  def __str__(self):
    return '{}: {}'.format(type(self).__name__, self.message)


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
