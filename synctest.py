#!/usr/bin/env python

import os
import sys

def main():
  rootdir1 = ''
  rootdir2 = ''
  if len(sys.argv) > 2:
    rootdir1 = sys.argv[1]
    rootdir2 = sys.argv[2]

  (size1, files1, dirs1) = totalsize(rootdir1)
  (size2, files2, dirs2) = totalsize(rootdir2)
  if size1 == size2 and files1 == files2 and dirs1 == dirs2:
    print (rootdir1+" is the same size as "+rootdir2+" and has the same number "
      +"of files and directories.")
    sys.exit(0)
  else:
    print (rootdir1+": "+str(size1)+" bytes, "+str(files1)+" files, "+str(dirs1)
      +" directories")
    print (rootdir2+": "+str(size2)+" bytes, "+str(files2)+" files, "+str(dirs2)
      +" directories")
    # sys.exit(0)

  walker1 = os.walk(rootdir1)
  walker2 = os.walk(rootdir2)
  done1 = done2 = False
  todo1 = todo2 = []
  (dir1, dirnames1, filenames1) = walker1.next()
  (dir2, dirnames2, filenames2) = walker2.next()
  while not done1 and not done2:
    # make sure walker visits the directories in the same order
    # the order of the directories in dirnames will be the order the walker
    # visits them.

    # TODO: double-check that functions pass by reference.
    (missing1, missing2) = matchup(dirnames1, dirnames2)

    # <s>sync up the lists</s>
    # scratch that. detecting different CONTENTS isn't done by comparing dir1
    # and dir2. it's by comparing dirnames and filenames. so to prevent
    # dir1 != dir2, just compare dirnames1 and dirnames2 each time. sync THOSE
    # lists, and del() any dirnames without a counterpart.

    print dir1+"\t"+dir2
    try:
      (dir1,dirnames1,filenames1) = walker1.next()
    except StopIteration, si:
      done1 = True
    try:
      (dir2,dirnames2,filenames2) = walker2.next()
    except StopIteration, si:
      done2 = True

# sort and compare the two lists of filenames, note any that don't have a match
# in the other list, and delete them.
def matchup(files1, files2):
  missing1 = missing2 = []

  files1.sort()
  files2.sort()
  len1 = len(files1)
  len2 = len(files2)
  i = j = 0
  while i < len1 and j < len2:
    if files1[i] == files2[j]:
      i+=1
      j+=1
      continue
    else:
      a = i
      b = j
      skipped1 = { files1[a]:a }
      skipped2 = { files2[b]:b }
      # find the first file on either side that matches, load up the dict's
      while a < len1 and b < len2:
        skipped1[files1[a]] = a
        if files1[a] in skipped2:
          break
        else:
          a+=1
        skipped2[files2[b]] = b
        if files2[b] in skipped1:
          break
        else:
          b+=1
      # TODO handle case where the matches aren't found
      # then start again at i and j, and add each file to missing until you
      # hit the first one that's present in the other's skipped
      x = i
      while x <= a and files1[x] not in skipped2:
        missing.append(files1[x])
        del(files1[x])
        x+=1
      y = j
      while y <= b files2[y] not in skipped1:
        missing.append(files2[y])
        del(files2[y])
        y+=1
      



def totalsize(root_dir):
  size = 0
  files = 0
  dirs = 0
  for dirpath, dirnames, filenames in os.walk(root_dir):
    files += len(filenames)
    dirs += len(dirnames)
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      size += os.path.getsize(filepath)
  return (size, files, dirs)

if __name__ == "__main__":
  main()