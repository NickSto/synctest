#!/usr/bin/env python3
import argparse
import collections
import gzip
import logging
import os
import pathlib
import sys
import zlib
import utillib.simplewrap
assert sys.version_info.major >= 3, 'Python 3 required'

NULL_STR = '.'
DEFAULT_CHUNK_SIZE = 1024**2
DESCRIPTION = """Check the differences between the contents of two directories."""


def make_argparser():
  wrapper = utillib.simplewrap.Wrapper(width_mod=-24)
  wrap = wrapper.wrap
  parser = argparse.ArgumentParser(description=DESCRIPTION,
                                   formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('path1', type=pathlib.Path,
    help='The first directory to compare. You can also give the path to a file of metadata '
      'produced by file-metadata.py, run on a directory or set of directories. In this case, '
      'though, the startpath has to be the same in both cases.')
  parser.add_argument('path2', type=pathlib.Path,
    help='The second directory to compare.')
  parser.add_argument('-t', '--tsv', dest='format', action='store_const', const='tsv', default='human',
    help=wrap('Print in computer-readable tab-delimited format instead of human readable text. The '
         'output is one line per difference. The columns are:')+'\n'+
         wrap(
         '1.  Relative path of the file that\'s different (path starting at dir1/dir2 args).\n'
         '2.  Difference type:', lspace=4, indent=-4)+'\n'+
         wrap(
         '    "missing1": path not found in dir1.\n'
         '    "missing2": path not found in dir2.\n'
         '    "type":     path is a different type (file/directory/link/etc) in dir1 and dir2.\n'
         '    "target":   path is a link, but has different targets in dir1 and dir2.\n'
         '    "size":     path is a file with different sizes.\n'
         '    "modified": path has a different date modified in dir1 and dir2.\n'
         '    "crc":      path has a different crc32 in dir1 and dir2.', lspace=16, indent=-16)+'\n'+
         wrap(
         '3.  Type of path in dir1 ("file", "dir", "link", "block", "char", "socket", "fifo", or '
              '"special").\n'
         '4.  Same for dir2.\n'
         '5.  File size of path in dir1.\n'
         '6.  Same for dir2.\n'
         '7.  Date modified of path in dir1 (unix timestamp).\n'
         '8.  Same for dir2.\n'
         '9.  crc32 of path in dir1.\n'
         '10. Same for dir2.\n'
         '11. Target of link in dir1.\n'
         '12. Same for dir2.', lspace=4, indent=-4)+'\n'+
         wrap('For all columns, "?" means the value was not measured or is not applicable.'))
  parser.add_argument('-d', '--ignore-dates', dest='date_tolerance', action='store_const',
    default=0, const=60*60*24*365*1000,  # 1000 years
    help=wrap('Ignore discrepancies between dates modified.'))
  parser.add_argument('-D', '--date-tolerance', default=0, type=parse_tolerance,
    help=wrap('Amount of allowed discrepancy between modified dates. Can be given with units of '
      'seconds (s), minutes (m), hours (h), or days (d), e.g. "15m". Times without units are '
      'assumed to be seconds.'))
  parser.add_argument('-c', '--no-checksum', dest='crc', default='last',
    action='store_const', const='none',
    help=wrap('Do not perform a checksum (CRC-32 currently), saving time on large files. The size '
      'in bytes will still be checked, which will catch most changes in contents.'))
  parser.add_argument('-C', '--checksum-if-date-diff', dest='crc', action='store_const', const='date',
    help=wrap('Compare the checksums even if the date modifieds are different.'))
  parser.add_argument('-1', '-a', '--ignore-dir1', action='store_true',
    help=wrap('Ignore files and directories missing from the first directory. When items are '
      'found to be missing from the first directory (according to the order in the arguments), do '
      'not print any message. Other discrepancies will still be reported.'))
  parser.add_argument('-2', '-b', '--ignore-dir2', action='store_true',
    help=wrap('Ignore files and directories missing from the second directory. When items are '
      'found to be missing from the second directory (according to the order in the arguments), do '
      'not print any message. Other discrepancies will still be reported.'))
  parser.add_argument('-f', '--follow-links', action='store_true',
    help=wrap('Follow symbolic links while traversing the filesystem. This will not affect how '
      'links are treated when comparing paths. They will always be considered on their own, as a '
      'special file type, without reference to their targets.'))
  parser.add_argument('-X', '--die-on-error', action='store_true',
    help=wrap("Don't ignore errors that prevent obtaining an accurate result. Normally, if there's "
      "an issue accessing a path (permission issue, misc I/O issue), a warning will be logged and "
      'it will move on. If this option is set, that will be treated as a fatal error and the '
      'program will die.'))
  #TODO:
  # parser.add_argument('-p', '--print-all', action='store_true', default=False,
  #   help='Print all the files in the directory to stdout, including the full path, size, date '
  #        'modified, and CRC-32. This output can be saved to a file, and compared to the output for '
  #        'another directory using sort and diff.')
  # parser.add_argument('-u', '--unix-time', action='store_true',
  #   help='When in print-all mode, print the unix timestamp (in seconds) instead of a human-'
  #        'readable date modified.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help=wrap('Print log messages to this file instead of to stderr. Warning: Will overwrite the '
      'file.'))
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  path_type = check_path_args(args.path1, args.path2)

  if path_type == 'file':
    survey1, meta1 = read_survey(args.path1)
    diff_generator = compare_surveys(survey1, args.path2, meta1)
    root1 = root2 = meta1['startpath']
  elif path_type == 'dir':
    diff_generator = recursive_compare(
      args.path1, args.path2, args.ignore_dir1, args.ignore_dir2, crc=args.crc,
      date_tolerance=args.date_tolerance, follow_links=args.follow_links,
      die_on_error=args.die_on_error
    )
    root1 = args.path1
    root2 = args.path2

  total_diffs = 0
  for diff_type, path_type, diff1, diff2 in diff_generator:
    total_diffs += 1
    if args.format == 'tsv':
      print(format_tsv(root1, root2, diff_type, path_type, diff1, diff2))
    elif args.format == 'human':
      print(format_human(diff_type, path_type, diff1, diff2))

  if args.format == 'human' and total_diffs == 0:
    print('They\'re equal!')


def check_path_args(*paths):
  failed = False
  path_types = [get_path_type(path) for path in paths]
  for path, path_type in zip(paths, path_types):
    if path_type == 'nonexistent':
      logging.critical('Error: Argument not an existing file or directory: {!r}'.format(str(path)))
      failed = True
    elif path_type not in ('dir', 'file'):
      logging.critical('Error: Argument not a file or directory: {!r}'.format(str(path)))
      failed = True
  if failed:
    fail()
  if path_types[0] != path_types[1]:
    fail('Error: Both arguments must be directories, or both must be files.\n'
         'Found a {} and {} instead.'.format(path_types[0], path_types[1]))
  return path_types[0]


def recursive_compare(root1, root2, ignore1, ignore2, crc='last', date_tolerance=0,
                      follow_links=False, die_on_error=False):
  walker1 = os.walk(root1, followlinks=follow_links, onerror=log_error)
  walker2 = os.walk(root2, followlinks=follow_links, onerror=log_error)
  first_loop = True
  while True:
    # Iterate the walkers.
    #TODO: Handle issues where one walker will go into a directory that the other can't.
    #      In this case, the one that can't will silently proceed to the next one, de-syncing them.
    #      Situations that can cause this:
    #      1. Permissions or some other I/O error prevents access to one of the directories.
    #      2. One path is a directory and the other is a link (and followlinks is False).
    #      You can give a handler to the `onerror` argument, and in the first situation the handler
    #      will be called, with the exception as its argument. Use the handler to detect this
    #      event, then advance the other walker as many times as you saw exceptions.
    #      But the second situation won't be caught this way. And what happens if you get a series
    #      of these in a row, mixing the two cases?
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
      yield 'missing2', get_path_type(missing), {'path':missing}, {'path':None}
  if not ignore1:
    for missing in missing2:
      yield 'missing1', get_path_type(missing), {'path':None}, {'path':missing}


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
  try:
    with path.open('rb') as file:
      chunk = file.read(chunk_size)
      while chunk:
        # Note: A change in Python 3.0 means the crc returned by this is incompatible with those from
        # earlier versions.
        crc = zlib.crc32(chunk, crc)
        chunk = file.read(chunk_size)
  except KeyboardInterrupt:
    logging.warning('Interrupted while getting crc32 of {}'.format(path))
    raise
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


def format_tsv(root1, root2, diff_type, path_type, diff1, diff2):
  rel_path1 = remove_root(root1, diff1['path'])
  rel_path2 = remove_root(root2, diff2['path'])
  if rel_path1 is None:
    rel_path = rel_path2
  elif rel_path2 is None:
    rel_path = rel_path1
  else:
    assert rel_path1 == rel_path2, (rel_path1, rel_path2)
    rel_path = rel_path1
  fields = [rel_path, diff_type]
  field_names = ('type', 'size', 'modified', 'crc', 'target')
  for field_name in field_names:
    fields.append(str(diff1.get(field_name, '?')))
    fields.append(str(diff2.get(field_name, '?')))
  return '\t'.join(fields)


def remove_root(root_path, full_path):
  if full_path is None:
    return None
  root = str(root_path)
  full = str(full_path)
  assert full[:len(root)] == root, (root, full)
  if root.endswith('/'):
    return full[len(root):]
  else:
    return full[len(root)+1:]


def log_error(error):
  logging.error('Error: {} on {!r}.'.format(type(error).__name__, error.filename))


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


########## "Static analysis" ##########

Metadata = collections.namedtuple('Metadata', ('modified', 'size', 'crc', 'type', 'error'))

def read_survey(survey_path):
  survey_metadata = {}
  survey = {}
  with open_path(survey_path) as survey_file:
    for line_raw in survey_file:
      if line_raw.startswith('#'):
        if line_raw.startswith('##'):
          parse_survey_metaline(line_raw, survey_metadata)
      else:
        path_str, metadata = parse_survey_line(line_raw)
        survey[path_str] = metadata
  return survey, survey_metadata


def parse_survey_metaline(line_raw, metadata):
  fields = line_raw[2:].rstrip('\r\n').split('=')
  assert len(fields) >= 2, line_raw
  key = fields[0]
  value = '='.join(fields[1:])
  if key == 'root':
    try:
      metadata[key].append(value)
    except KeyError:
      metadata[key] = [value]
  else:
    metadata[key] = value


def compare_surveys(survey1, survey2_path, survey1_meta):
  # Difference from compare_paths(): this can't check if link targets are equal, since that isn't
  # recorded by file-metadata.py.
  survey2_meta = {}
  unmatched = set(survey1.keys())
  with open_path(survey2_path) as survey2_file:
    for line_raw in survey2_file:
      if line_raw.startswith('#'):
        if line_raw.startswith('##'):
          parse_survey_metaline(line_raw, survey2_meta)
          # Check that the startpaths of the two surveys are the same.
          #TODO: Allow surveys with different startpaths.
          #      Should be able to just remove the startpath from the beginning of each column 1
          #      path (if it's present) and then I think you can compare the result between surveys.
          if 'startpath' in survey1_meta and 'startpath' in survey2_meta:
            if survey1_meta['startpath'] != survey2_meta['startpath']:
              fail('Error: startpath of both surveys must be equal: {!r} != {!r}'
                   .format(survey1_meta['startpath'], survey2_meta['startpath']))
        continue
      path_str, metadata2 = parse_survey_line(line_raw)
      diffs = []
      if path_str in survey1:
        metadata1 = survey1[path_str]
        diff_type = 'equal'
        for attr in 'type', 'size', 'modified', 'crc':
          if getattr(metadata1, attr) != getattr(metadata2, attr):
            if not (attr == 'modified' and metadata1.type == metadata2.type == 'dir'):
              diff_type = attr
              break
        diff1 = metadata_to_diff(metadata1, path_str)
        diff2 = metadata_to_diff(metadata2, path_str)
        if metadata1.type == metadata2.type:
          path_type = metadata1.type
        else:
          path_type = 'mixed'
        if diff_type != 'equal':
          yield diff_type, path_type, diff1, diff2
        unmatched.remove(path_str)
      else:
        yield 'missing1', metadata2.type, {'path':None}, metadata_to_diff(metadata2, path_str)
  for path_str in unmatched:
    metadata1 = survey1[path_str]
    yield 'missing2', metadata1.type, metadata_to_diff(metadata1, path_str), {'path':None}


def parse_survey_line(line_raw):
  fields = line_raw.rstrip('\r\n').split('\t')
  path, human_time, modified_str, size_str, crc_str, file_type, error = fields
  modified = size = crc = None
  if modified_str != NULL_STR:
    modified = int(modified_str)
  if size_str != NULL_STR:
    size = int(size_str)
  if crc_str != NULL_STR:
    crc = int(crc_str, 16)
  if file_type == NULL_STR:
    file_type = None
  if error == NULL_STR:
    error = None
  return fields[0], Metadata(modified, size, crc, file_type, error)


def metadata_to_diff(metadata, path):
  return {
    'path':pathlib.Path(path),
    'type':metadata.type,
    'size':metadata.size,
    'modified':metadata.modified,
    'crc':metadata.crc,
  }


def open_path(path):
  if path.name.endswith('.gz'):
    return gzip.open(path, mode='rt')
  else:
    return path.open('rt')


def fail(message=None):
  if message is not None:
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
